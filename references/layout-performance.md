# Auto Layout 与布局性能

当任务涉及 Auto Layout 卡顿、约束冲突、动态高度、`layoutSubviews` 重复布局、Masonry/remakeConstraints、首屏大量 view 创建或转场布局抖动时读取本文件。

## 快速目录

- 布局性能原则
- 约束创建位置
- 更新约束
- 动态高度
- Masonry 旧代码
- Frame 与 Auto Layout 混用
- 约束冲突
- 审查清单

## 布局性能原则

布局优化优先处理热路径：

- 列表 cell 的 configure / reuse / layout。
- 首屏大量重复组件。
- 动画过程中反复布局的 view。
- 动态高度计算器。

不要为了“少一点约束”把可维护的布局全部改成 frame。先确认瓶颈确实来自布局求解。

## 约束创建位置

固定约束只创建一次：

- 代码 cell：`initWithStyle:reuseIdentifier:` 或自定义 `setupViews`。
- XIB/storyboard：在 `awakeFromNib` 做一次性补充。
- view controller：`viewDidLoad`。

```objc
- (void)setupViews {
    self.titleLabel.translatesAutoresizingMaskIntoConstraints = NO;
    [self.contentView addSubview:self.titleLabel];

    [NSLayoutConstraint activateConstraints:@[
        [self.titleLabel.leadingAnchor constraintEqualToAnchor:self.contentView.leadingAnchor constant:16.0],
        [self.titleLabel.trailingAnchor constraintEqualToAnchor:self.contentView.trailingAnchor constant:-16.0],
        [self.titleLabel.topAnchor constraintEqualToAnchor:self.contentView.topAnchor constant:12.0]
    ]];
}
```

避免在 `layoutSubviews`、`viewDidLayoutSubviews`、`cellForRow`、`configureWithItem:` 中重复创建相同约束。

## 更新约束

变化的布局保留约束引用，只改 `constant` 或 `active`。

```objc
@property (nonatomic, strong) NSLayoutConstraint *subtitleTopConstraint;

- (void)configureWithItem:(Item *)item {
    self.subtitleLabel.hidden = item.subtitle.length == 0;
    self.subtitleTopConstraint.constant = item.subtitle.length > 0 ? 6.0 : 0.0;
}
```

批量更新 constraint 后，不要立刻多次 `layoutIfNeeded`。动画场景可在动画 block 中调用一次。

## 动态高度

动态高度 cell 的重点是稳定宽度和缓存结果：

- 高度计算时传入确定 content width。
- 缓存 key 包含 model id、内容版本、宽度、字体环境。
- cell 内容变化后精确失效对应 key。
- 不要在滚动过程中同步计算复杂富文本高度。

如果使用 self-sizing cell，确保 vertical constraints 从 contentView 顶部到尾部完整闭合，否则高度会不稳定。

## Masonry 旧代码

Objective-C 旧项目常见 Masonry 写法：

- 初始化时用 `mas_makeConstraints`。
- 状态变化时用 `mas_updateConstraints`。
- 只有布局结构真的变化时才用 `mas_remakeConstraints`。

不要在 `configureWithModel:` 中高频 `mas_remakeConstraints`，它会移除并重建约束，列表滚动时成本很高。

## Frame 与 Auto Layout 混用

混用时要明确谁负责布局：

- Auto Layout 管理的 view 不要频繁手动改 frame。
- 手动 frame 布局的子树可以局部关闭 Auto Layout，但不要和外层约束互相争抢。
- 依赖最终 frame 的 `shadowPath`、mask path、圆角路径应在 bounds 稳定后更新，并只在 bounds 变化时更新。

## 约束冲突

约束冲突不是纯日志问题，它会触发系统尝试打破约束并重新布局。维护时：

- 优先修复 required constraint 冲突。
- 给可伸缩 label 设置合理 content hugging / compression resistance。
- 多行 label 设置 `numberOfLines`，动态高度场景确认 preferred width。
- 不要用大量 999 priority 掩盖结构问题。

## 审查清单

- 固定约束是否只创建一次？
- `configure` / `layoutSubviews` 是否重复 make/remake constraints？
- 动态变化是否只改 constant / active？
- 动态高度 key 是否包含宽度、内容版本和字体环境？
- Masonry 旧代码是否避免高频 `remakeConstraints`？
- Auto Layout 和 frame 是否职责清晰？
- 约束冲突是否被修复，而不是只降低 priority 掩盖？
