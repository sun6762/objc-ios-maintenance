# 内存所有权

当任务涉及 ARC 属性修饰符、delegate、block 捕获、timer、notification、associated object 或疑似 retain cycle 时读取本文件。

## 属性修饰符选择

审查 `.h` 文件时使用下面的判断表：

| 修饰符 | 适用场景 | 避免用于 |
| --- | --- | --- |
| `strong` | 当前对象拥有的 Objective-C 对象、mutable collection、service、view model | delegate、反向引用、栈 block |
| `weak` | delegate、data source、parent pointer、加载后由 superview 拥有的 UIKit view | 必须保持存活的依赖 |
| `copy` | block、string、attributed string、不可变 collection、值语义输入 | 必须保持 mutable 的大对象 |
| `assign` | 标量、enum、C struct | ARC 下的 Objective-C 对象 |

对不可变 Foundation 值类型优先使用 `copy`，因为调用方可能传入 mutable 子类：

```objc
@property (nonatomic, copy) NSString *title;
@property (nonatomic, copy) NSArray<Item *> *items;
@property (nonatomic, copy, nullable) void (^completion)(Result * _Nullable result, NSError * _Nullable error);
```

对 mutable collection 使用 `strong`，因为 `copy` 会生成不可变副本：

```objc
@property (nonatomic, strong) NSMutableArray<Item *> *mutableItems;
```

## Delegate 所有权

delegate 和 data source 几乎总是 `weak`：

```objc
@property (nonatomic, weak, nullable) id<MyControllerDelegate> delegate;
```

只有在旧部署目标或旧类无法使用 zeroing weak reference 时才考虑 `assign`。如果必须使用 `assign`，要记录生命周期假设，因为它可能留下悬垂指针。

## Block 与循环引用

被持有的 block 会持有它捕获的 Objective-C 对象。如果 `self` 拥有 block，而 block 捕获 `self`，循环为：

```text
self -> block property -> block -> self
```

对可能逃逸当前调用栈的回调使用 weak/strong dance：

```objc
__weak typeof(self) weakSelf = self;
self.completion = ^{
    __strong typeof(weakSelf) self = weakSelf;
    if (!self) {
        return;
    }
    [self finish];
};
```

不要用 `__unsafe_unretained` 规避循环引用。它只是把 leak 风险换成更容易崩溃的悬垂指针风险。

## Timer、Display Link 与 Observer 生命周期

repeating timer 和 display link 常常会持有 target。应在 teardown 时失效：

```objc
- (void)dealloc {
    [_timer invalidate];
    [[NSNotificationCenter defaultCenter] removeObserver:self];
}
```

block 形式的 notification observer 会返回 token。要保存并移除该 token。弱捕获并不会移除 observer：

```objc
self.observer = [[NSNotificationCenter defaultCenter] addObserverForName:SomeNotification
                                                                  object:nil
                                                                   queue:[NSOperationQueue mainQueue]
                                                              usingBlock:^(NSNotification *note) {
    __strong typeof(weakSelf) self = weakSelf;
    [self refresh];
}];
```

## Associated Object 所有权

associated object 可能制造隐藏所有权。association policy 要与属性语义匹配：

```objc
static void *AssociatedStateKey = &AssociatedStateKey;
objc_setAssociatedObject(self, AssociatedStateKey, state, OBJC_ASSOCIATION_RETAIN_NONATOMIC);
```

对 block 和值语义对象使用 `OBJC_ASSOCIATION_COPY_NONATOMIC`。避免 associated object 持有 owner，或持有会反过来持有 owner 的对象。
