# 错误处理、异步 API 与线程

当任务涉及 `NSError **`、completion handler、URLSession 回调、GCD、NSOperation、取消逻辑，或异步后更新 UI 时读取本文件。

## 同步 NSError 模式

对可恢复的同步失败，使用 Cocoa 约定：

```objc
- (nullable Model *)parseData:(NSData *)data error:(NSError * _Nullable * _Nullable)error {
    if (data.length == 0) {
        if (error != NULL) {
            *error = [NSError errorWithDomain:ParserErrorDomain
                                         code:ParserErrorEmptyData
                                     userInfo:@{NSLocalizedDescriptionKey: @"Data is empty."}];
        }
        return nil;
    }

    return [[Model alloc] initWithData:data];
}
```

规则：

- 成功时不要写入 `*error`。
- 赋值前检查 `error != NULL`。
- 失败时返回 `nil` 或 `NO`。
- 不要用 `NSError **` 表达程序员错误；这类问题应通过 assertion、precondition 或直接修复处理。

## Completion Handler 的形状

优先使用一个 completion，并保证只调用一次：

```objc
typedef void (^ModelCompletion)(Model * _Nullable model, NSError * _Nullable error);

- (void)loadModelWithCompletion:(ModelCompletion)completion {
    NSURLSessionDataTask *task = [self.session dataTaskWithURL:self.URL
                                             completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
        if (error) {
            [self finishOnMainWithModel:nil error:error completion:completion];
            return;
        }

        NSError *parseError = nil;
        Model *model = [self.parser parseData:data error:&parseError];
        [self finishOnMainWithModel:model error:parseError completion:completion];
    }];
    [task resume];
}
```

在 API 契约中说明回调队列。面向 UI 的 API 应在调用 completion 前切回主线程；底层基础设施 API 应保持既有调用队列语义，或显式暴露 queue 参数。

## 主线程规则

UIKit 必须在主线程访问：

```objc
dispatch_async(dispatch_get_main_queue(), ^{
    self.titleLabel.text = model.title;
    [self.tableView reloadData];
});
```

URLSession completion handler 不保证在主线程。GCD、operation queue、数据库回调和图片加载回调也经常回到后台队列。

## 取消与复用

对 cell 复用、搜索、图片加载或页面 teardown，要让取消逻辑显式可见：

```objc
- (void)prepareForReuse {
    [super prepareForReuse];
    [self.imageTask cancel];
    self.imageTask = nil;
    self.thumbnailView.image = nil;
}
```

不要只依赖弱捕获。弱捕获能避免部分循环引用，但无法阻止过期回调更新已复用的 view 或旧 model。

## NSOperation 注意点

维护旧 operation 代码时：

- 异步 operation 要让 `isExecuting`、`isFinished`、`isCancelled` 保持 KVO-compliant。
- finish 只能发生一次。
- 调用 completion 前检查 cancellation。
- 如果周围代码已经使用 operation，优先用 dependency 表达顺序，不要继续嵌套 callback 金字塔。
