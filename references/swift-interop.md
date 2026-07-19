# Swift 混编

当任务涉及 Swift/Objective-C 混合 target、bridging header、module import、生成的 `-Swift.h` 头文件，或改善 Objective-C API 的 Swift 导入效果时读取本文件。

## 导入方向

Objective-C 暴露给 Swift：

- app target 使用 `SWIFT_OBJC_BRIDGING_HEADER` 配置的 bridging header。
- framework target 应通过 public header、umbrella header 和 module 暴露 Objective-C。

Swift 暴露给 Objective-C：

- 在 `.m` 文件中 import 生成的 `ProductModuleName-Swift.h`。
- 不要在公开 `.h` 文件中 import 生成的 Swift 头。
- 头文件中尽量使用 forward declaration。

```objc
// MyController.h
@class MySwiftService;

@interface MyController : UIViewController
@property (nonatomic, strong) MySwiftService *service;
@end
```

```objc
// MyController.m
#import "MyProduct-Swift.h"
```

## 改善 Swift 导入

Objective-C 注解决定 Swift 侧看到的 API：

```objc
NS_ASSUME_NONNULL_BEGIN

@interface UserStore : NSObject
- (nullable User *)userForIdentifier:(NSString *)identifier error:(NSError * _Nullable * _Nullable)error;
- (NSArray<User *> *)allUsers;
@end

NS_ASSUME_NONNULL_END
```

使用：

- `nullable` 标记可空值。
- lightweight generics 标记集合元素类型。
- `instancetype` 标记 factory 和 initializer。
- 当导入后的 Swift 名称别扭，但 Objective-C selector 应保持稳定时，使用 `NS_SWIFT_NAME`。
- 当 Swift 侧应该使用手写 overlay 或 extension，而不是直接使用原始 Objective-C 方法时，使用 `NS_REFINED_FOR_SWIFT`。

## NS_SWIFT_NAME

使用 `NS_SWIFT_NAME` 在不改变 Objective-C 调用方的前提下改善 Swift 调用点：

```objc
- (void)fetchUserWithIdentifier:(NSString *)identifier
                     completion:(void (^)(User * _Nullable user, NSError * _Nullable error))completion
    NS_SWIFT_NAME(fetchUser(id:completion:));
```

不要过度使用。如果自然的 Objective-C selector 已能导入为清晰的 Swift API，就保持不变。

## NS_REFINED_FOR_SWIFT

当 Swift 应消费一个更安全的包装 API 时，使用 `NS_REFINED_FOR_SWIFT`：

```objc
- (BOOL)writeData:(NSData *)data error:(NSError * _Nullable * _Nullable)error NS_REFINED_FOR_SWIFT;
```

然后提供 Swift extension，把 refined Objective-C API 包装成更适合 Swift 的形状。

## 循环与可见性

常见混编失败：

- 公开 Objective-C 头文件与生成的 Swift 头之间产生 import cycle。
- Swift class 对 Objective-C 不可见，因为它没有继承 Objective-C 兼容基类，或缺少 `@objc` 暴露。
- Objective-C API 缺少 nullability，导入 Swift 后变成 implicitly unwrapped optional。
- 修改 Objective-C selector 后，Swift 名称意外变化。

修改公开头文件时，同时检查 Objective-C 调用方和 Swift 调用点。
