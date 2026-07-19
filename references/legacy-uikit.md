# 旧 UIKit 代码维护

当任务涉及 Objective-C view controller、cell、delegate/data source、Auto Layout、导航流程或 UIKit 生命周期问题时读取本文件。

## View Controller 生命周期

按生命周期方法的真实时机放置逻辑：

- `viewDidLoad`：一次性 view setup、subview 创建、约束、静态绑定。
- `viewWillAppear:`：屏幕隐藏期间可能变化的数据刷新、navigation bar 状态。
- `viewDidAppear:`：analytics、需要可见后再开始的动画。
- `viewWillDisappear:`：暂停与可见性绑定的工作。
- `viewDidLayoutSubviews`：Auto Layout 完成后的 frame 依赖布局。避免在这里反复添加约束。
- `dealloc`：失效 timer、移除 block observer、关闭其他生命周期没有处理的资源。

除非重复拉取是明确需求，不要把网络请求散落在多个生命周期方法中。

## Cell 复用

cell 配置必须是幂等的：

```objc
- (void)prepareForReuse {
    [super prepareForReuse];
    [self.imageTask cancel];
    self.imageTask = nil;
    self.titleLabel.text = nil;
    self.thumbnailView.image = nil;
    self.badgeView.hidden = YES;
}

- (void)configureWithItem:(Item *)item {
    self.titleLabel.text = item.title;
    self.badgeView.hidden = !item.hasBadge;
}
```

重置所有可能由旧 model 设置过的状态：text、image、hidden flag、alpha、transform、selected/highlighted state、constraint toggle、gesture target 和异步 callback。

## Auto Layout

代码创建 view 时：

```objc
view.translatesAutoresizingMaskIntoConstraints = NO;
[NSLayoutConstraint activateConstraints:@[
    [view.leadingAnchor constraintEqualToAnchor:self.contentView.leadingAnchor],
    [view.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor]
]];
```

规则：

- 尽量在 setup 阶段一次性 activate constraints。
- 不要在 `layoutSubviews` 或 `viewDidLayoutSubviews` 中重复创建相同约束。
- 对需要变化的约束保留引用。
- 优先修改 constraint constant，而不是移除后重新创建。
- 不要在 layout 发生前读取最终 frame。

## Delegate 与 Data Source 维护

delegate 和 data source 应使用 weak。调用 optional delegate 方法前必须 guard：

```objc
if ([self.delegate respondsToSelector:@selector(controllerDidFinish:)]) {
    [self.delegate controllerDidFinish:self];
}
```

如果一个 view controller 同时承担 delegate、data source、coordinator、network owner 和 parser，保持本次任务修改局部化；只有当抽取能直接降低当前风险时，才做针对性拆分。

## 线程与生命周期交互

从回调更新 UI 前：

- 确认 view/controller 仍然存活。
- 确认回调仍匹配当前 model 或 index path。
- 切回主队列。
- 避免为了应用过期 UI 而强行持有已经 dismiss 的 controller。
