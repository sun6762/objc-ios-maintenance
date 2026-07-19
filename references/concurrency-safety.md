# 并发、队列与线程安全

当任务涉及 GCD、NSOperation、异步回调、取消、共享 mutable state、dispatch barrier、死锁、竞态、后台处理后更新 UI 或多请求时序问题时读取本文件。

## 快速目录

- 线程安全原则
- 主队列与死锁
- 共享状态保护
- 异步结果时序
- 取消语义
- NSOperation
- 回调队列契约
- 审查清单

## 线程安全原则

`atomic` 属性不等于对象线程安全。它只保证单次 getter/setter 的原子性，不能保护“读取后修改再写回”的组合操作。

旧 Objective-C 项目里，线程问题通常来自：

- 多个回调同时改 `NSMutableArray` / `NSMutableDictionary`。
- 后台队列更新 UIKit。
- 搜索、分页、图片请求返回顺序不稳定，旧结果覆盖新结果。
- 主线程调用 `dispatch_sync(dispatch_get_main_queue(), ...)`。
- cancellation 只取消网络，不取消 completion 中的后续解析或 UI 更新。

## 主队列与死锁

切回主线程要判断当前线程：

```objc
static inline void OCMDispatchOnMain(dispatch_block_t block) {
    if (NSThread.isMainThread) {
        block();
    } else {
        dispatch_async(dispatch_get_main_queue(), block);
    }
}
```

避免：

```objc
dispatch_sync(dispatch_get_main_queue(), ^{
    [self.tableView reloadData];
});
```

这段如果从主线程调用会死锁。UI 更新通常使用 `dispatch_async`，需要同步返回值时应重新设计调用方，不要在后台强行同步取 UI 状态。

## 共享状态保护

共享 mutable collection 要么只在一个串行队列访问，要么用锁/队列保护。不要在多个 URLSession completion 里直接修改同一个 `NSMutableDictionary`。

```objc
@interface Store ()
@property (nonatomic) dispatch_queue_t stateQueue;
@property (nonatomic, strong) NSMutableDictionary<NSString *, Item *> *itemsByID;
@end

- (instancetype)init {
    self = [super init];
    if (self) {
        _stateQueue = dispatch_queue_create("com.example.store.state", DISPATCH_QUEUE_SERIAL);
        _itemsByID = [NSMutableDictionary dictionary];
    }
    return self;
}

- (void)updateItem:(Item *)item {
    dispatch_async(self.stateQueue, ^{
        self.itemsByID[item.identifier] = item;
    });
}
```

读多写少时可以使用 concurrent queue + barrier，但要保证所有读写都通过同一个队列。

## 异步结果时序

搜索、筛选、分页、图片加载等场景要防旧结果覆盖新状态。常用做法是 generation token：

```objc
@property (nonatomic, assign) NSUInteger requestGeneration;

- (void)reloadWithQuery:(NSString *)query {
    self.requestGeneration += 1;
    NSUInteger generation = self.requestGeneration;

    __weak typeof(self) weakSelf = self;
    [self.service search:query completion:^(NSArray<Item *> *items, NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            __strong typeof(weakSelf) self = weakSelf;
            if (!self || generation != self.requestGeneration) {
                return;
            }
            self.items = items;
            [self.tableView reloadData];
        });
    }];
}
```

列表 cell 图片加载则优先使用稳定 model identifier，而不是 indexPath。

## 取消语义

取消要贯穿整个链路：

- 取消网络 task。
- 后台解析前检查 cancellation。
- 回主线程前检查 owner 是否存在、generation 是否仍匹配。
- 页面销毁时取消页面拥有的任务。

```objc
- (void)cancelLoading {
    [self.dataTask cancel];
    self.dataTask = nil;
    self.requestGeneration += 1;
}
```

不要只依赖 weak self；它不能取消已经占用 CPU、网络或 IO 的工作。

## NSOperation

如果项目已经使用 `NSOperationQueue`，优先沿用：

- 用 dependency 表达任务顺序。
- 给 operation 命名，便于 Instruments 和日志定位。
- 异步 operation 必须正确维护 `isExecuting` / `isFinished` 的 KVO。
- completion 中检查 `isCancelled`。
- 避免 operation 内再无限套 GCD，导致取消和依赖失效。

## 回调队列契约

API 要明确 completion 在哪个队列调用。面向 UI 的 manager 可以保证主队列；底层 service 可以保持后台队列，但要写清楚。

```objc
typedef void (^ItemsCompletion)(NSArray<Item *> * _Nullable items, NSError * _Nullable error);

- (void)loadItemsWithCompletion:(ItemsCompletion)completion {
    [self loadItemsOnQueue:self.callbackQueue completion:completion];
}
```

不要让调用方猜 completion 队列；这会把线程 bug 扩散到每个调用点。

## 审查清单

- 是否把 `atomic` 当成线程安全方案？
- mutable collection 是否只在受控队列/锁内读写？
- UI 是否只在主线程更新，且没有主线程 `dispatch_sync`？
- 多个异步结果是否有 generation/model identifier 防旧结果覆盖？
- 取消是否覆盖网络、解析、回调和 UI 更新？
- API completion 队列是否明确且一致？
- NSOperation 的状态和取消是否 KVO-compliant？
