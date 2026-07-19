# 运行时、KVC、KVO、分类与方法交换

当任务涉及动态 selector、KVC/KVO、category 方法、associated object 或 method swizzling 时读取本文件。

## KVC 边界

KVC 是基于字符串且以异常表达错误的机制。修改 KVC 代码前检查：

- key 是否符合 KVC lookup 规则，对应 accessor 或 ivar 是否存在？
- 标量属性是否可能收到 `nil`？
- key 是否来自用户输入或服务端数据？
- 是否可以改为类型化访问，从而不再需要 KVC？

保护动态 key：

```objc
if ([object respondsToSelector:NSSelectorFromString(key)]) {
    [object setValue:value forKey:key];
}
```

这个检查不能覆盖所有 KVC lookup 路径，但比盲目套用任意 key 更安全。

## 使用 Context 指针的 KVO

使用唯一的 static context 指针：

```objc
static void *PlayerStatusContext = &PlayerStatusContext;

[self.player addObserver:self
              forKeyPath:@"status"
                 options:NSKeyValueObservingOptionInitial | NSKeyValueObservingOptionNew
                 context:PlayerStatusContext];

- (void)observeValueForKeyPath:(NSString *)keyPath
                      ofObject:(id)object
                        change:(NSDictionary<NSKeyValueChangeKey, id> *)change
                       context:(void *)context {
    if (context == PlayerStatusContext) {
        [self updateForPlayerStatus];
        return;
    }

    [super observeValueForKeyPath:keyPath ofObject:object change:change context:context];
}
```

在所有 teardown 路径上确保 observation 只移除一次。避免移除从未添加过的 observer。

## 手动 KVO

只有在禁用自动通知，或 mutation 对 KVO 不可见时，才使用手动通知：

```objc
+ (BOOL)automaticallyNotifiesObserversForKey:(NSString *)key {
    if ([key isEqualToString:@"state"]) {
        return NO;
    }
    return [super automaticallyNotifiesObserversForKey:key];
}

- (void)setState:(State)state {
    if (_state == state) {
        return;
    }
    [self willChangeValueForKey:@"state"];
    _state = state;
    [self didChangeValueForKey:@"state"];
}
```

## 分类（Category）

category 方法共享目标类的全局 selector 命名空间。给方法加项目前缀以减少冲突：

```objc
@interface NSString (ACMEValidation)
- (BOOL)acme_isValidAccountIdentifier;
@end
```

category 不能添加 ivar。必要时使用 associated object，并使用 static key：

```objc
static void *ACMEStateKey = &ACMEStateKey;
objc_setAssociatedObject(self, ACMEStateKey, state, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
```

## 方法交换（Method Swizzling）

swizzling 很脆弱，因为它会改变全局 runtime 行为。只有在无法使用局部组合时才使用。

不可避免要 swizzling 时检查：

- 用 `dispatch_once` 包住交换逻辑。
- 确认两个方法都存在，且 type encoding 兼容。
- 在只会加载一次的受控位置交换实现。
- 通过 swizzled selector 调用原实现。
- 避免以影响无关页面的方式 swizzle 公共 framework 行为。

```objc
+ (void)load {
    static dispatch_once_t onceToken;
    dispatch_once(&onceToken, ^{
        Method original = class_getInstanceMethod(self, @selector(viewDidAppear:));
        Method replacement = class_getInstanceMethod(self, @selector(acme_viewDidAppear:));
        method_exchangeImplementations(original, replacement);
    });
}

- (void)acme_viewDidAppear:(BOOL)animated {
    [self acme_viewDidAppear:animated];
    [self acme_trackAppearance];
}
```
