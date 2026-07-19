# 网络、缓存与数据刷新性能

当任务涉及 Objective-C 网络层、NSURLSession、请求取消、重复请求、缓存策略、首屏缓存、分页刷新、弱网重试或网络回调导致 UI 崩溃时读取本文件。

## 快速目录

- 请求生命周期
- 避免重复请求
- 缓存层级
- 弱网与重试
- 分页与刷新
- 回调与 UI 安全
- 审查清单

## 请求生命周期

网络请求要有明确 owner。常见 owner 是页面、view model、service 或 image loader。页面拥有的请求需要在页面退出或条件变化时取消。

```objc
@interface FeedViewController ()
@property (nonatomic, strong, nullable) NSURLSessionDataTask *feedTask;
@end

- (void)viewWillDisappear:(BOOL)animated {
    [super viewWillDisappear:animated];
    [self.feedTask cancel];
    self.feedTask = nil;
}
```

不要把请求散落在多个生命周期方法中重复发起。维护旧代码时，先确认哪些请求是首屏必需，哪些可以延后或复用缓存。

## 避免重复请求

同一个资源在短时间内被多个调用点请求时，优先合并 in-flight request，而不是同时发多次。

```objc
@interface ImageLoader ()
@property (nonatomic, strong) NSMutableDictionary<NSString *, NSMutableArray<ImageCompletion> *> *pendingCompletions;
@end

- (void)loadImageWithKey:(NSString *)key completion:(ImageCompletion)completion {
    NSMutableArray *pending = self.pendingCompletions[key];
    if (pending) {
        [pending addObject:[completion copy]];
        return;
    }

    self.pendingCompletions[key] = [NSMutableArray arrayWithObject:[completion copy]];
    [self startRequestForKey:key];
}
```

in-flight 字典是共享 mutable state，必须只在同一个串行队列或主线程访问。

## 缓存层级

缓存策略按数据类型选择：

- 内存缓存：图片、短期 model、cell 高度、富文本结果，用 `NSCache` 并设置上限。
- 磁盘缓存：可复用网络响应、缩略图、首屏 snapshot，写入后台队列。
- 系统 URL 缓存：适合 HTTP cache-control 清晰的 GET 请求。
- 业务缓存：需要版本、用户、语言、AB 实验、权限等参与 key 的数据。

缓存 key 必须包含影响结果的上下文，例如 user id、URL、参数、尺寸、scale、语言、版本、登录态。

## 弱网与重试

重试要有上限和退避，不要在失败回调里立即无限重试：

```objc
- (NSTimeInterval)retryDelayForAttempt:(NSUInteger)attempt {
    NSTimeInterval base = MIN(pow(2.0, attempt), 32.0);
    return base + ((double)arc4random_uniform(1000) / 1000.0);
}
```

只对幂等或明确可重试的请求重试。POST、支付、下单、状态变更类请求要靠业务 idempotency key 或服务端保障，不能客户端盲目重放。

## 分页与刷新

分页列表常见问题：

- 同时触发多个下一页请求。
- 下拉刷新和加载更多同时改数据源。
- 旧请求返回后覆盖新筛选条件。
- 请求失败后 loading 状态没有复位，列表无法继续加载。

建议维护明确状态：

```objc
typedef NS_ENUM(NSInteger, FeedLoadingState) {
    FeedLoadingStateIdle,
    FeedLoadingStateRefreshing,
    FeedLoadingStateLoadingMore
};
```

根据状态决定是否允许新请求。查询条件变化时增加 generation token，旧结果直接丢弃。

## 回调与 UI 安全

网络 completion 不保证在主线程。更新 UI 前检查：

- owner 是否仍存在。
- 页面是否仍是当前可更新页面。
- generation / query / model identifier 是否匹配。
- 数据源数量和 indexPath 是否仍一致。

```objc
__weak typeof(self) weakSelf = self;
self.feedTask = [self.service loadFeedWithCompletion:^(NSArray<Item *> *items, NSError *error) {
    dispatch_async(dispatch_get_main_queue(), ^{
        __strong typeof(weakSelf) self = weakSelf;
        if (!self || !self.view.window) {
            return;
        }
        self.items = items ?: @[];
        [self.tableView reloadData];
    });
}];
```

## 审查清单

- 请求 owner 是否明确，页面退出或条件变化时是否取消？
- 是否存在重复请求或 in-flight 合并缺失？
- 缓存 key 是否包含用户、参数、尺寸、版本和语言等上下文？
- 磁盘 IO 和解析是否避开主线程？
- 重试是否有上限、退避和幂等性判断？
- 分页状态是否避免刷新和加载更多互相覆盖？
- 网络回调更新 UI 前是否切回主线程并检查页面/model/generation？
