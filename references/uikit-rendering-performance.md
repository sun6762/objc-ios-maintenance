# UIKit 渲染性能

当任务涉及 UIKit 渲染性能、离屏渲染、圆角、阴影、mask、透明混合、`shouldRasterize`、滚动掉帧、列表 cell 视觉效果优化时读取本文件。

## 快速目录

- 判断原则
- 常见离屏渲染触发点
- 圆角处理
- 阴影处理
- mask 与 CAShapeLayer
- 透明混合
- Rasterize
- UIView 分类的边界
- 不适用场景
- 审查清单

## 判断原则

不要机械地“消灭所有离屏渲染”。真正要优化的是热路径上的不必要离屏渲染，尤其是 UITableView/UICollectionView cell、频繁动画的 view、首屏大量重复出现的卡片组件。

处理顺序：

1. 先确认场景：是否在滚动列表、动画过程、首屏加载或频繁刷新区域。
2. 再确认视觉需求：是否必须同时有圆角、裁剪、阴影、半透明、mask 或渐变。
3. 最后选方案：能预渲染就预渲染，能分层就分层，能给 `shadowPath` 就不要让系统动态计算。

调试时优先使用 Instruments 和 Core Animation 调试选项：

- Color Offscreen-Rendered：观察离屏渲染热点。
- Color Blended Layers：观察透明混合。
- FPS / Core Animation：观察滚动或动画是否掉帧。
- Time Profiler：确认瓶颈是否真的在渲染，而不是主线程 IO、图片解码或 Auto Layout。

## 常见离屏渲染触发点

下面这些写法不是绝对不能用，但在热路径中要特别审查：

- `layer.cornerRadius` + `layer.masksToBounds = YES`，尤其用于图片或复杂子层裁剪。
- `layer.shadowOpacity` / `shadowRadius` / `shadowOffset` 但没有设置 `shadowPath`。
- 同一个 layer 同时需要裁剪圆角和显示阴影。
- `layer.mask` 或复杂 `CAShapeLayer` mask。
- `shouldRasterize = YES`，它本身会触发一次离屏缓存。
- 半透明背景、alpha 小于 1 的大面积 view、带 alpha 通道的大图。
- 在 `layoutSubviews` / `drawRect:` 中频繁创建 path、mask、gradient、constraint 或 image。

## 圆角处理

### 简单背景圆角

只有纯色背景或简单内容时，可以直接使用 `cornerRadius`。如果不需要裁剪子视图，不要打开 `masksToBounds`：

```objc
self.cardView.layer.cornerRadius = 8.0;
self.cardView.layer.masksToBounds = NO;
self.cardView.backgroundColor = UIColor.whiteColor;
```

### 需要裁剪内容的圆角

图片、复杂子视图或异步加载内容需要裁剪时，`masksToBounds = YES` 常见但要谨慎。列表中大量圆角图片更适合在图片处理阶段生成圆角 bitmap，或使用已经裁好的资源。

```objc
self.avatarImageView.layer.cornerRadius = 20.0;
self.avatarImageView.layer.masksToBounds = YES;
```

这段代码可读性好，但如果 avatar 出现在高频滚动 cell 中，应进一步考虑：

- 图片是否已经按展示尺寸缩放。
- 是否在后台线程解码或预处理圆角。
- cell 复用时是否取消旧图片任务。
- 是否有实测掉帧，而不是只凭经验改动。

### 不要在 layout 中重复设置相同圆角

`layoutSubviews` 可以根据最终 bounds 更新圆角，但要避免重复创建昂贵对象：

```objc
- (void)layoutSubviews {
    [super layoutSubviews];

    CGFloat radius = CGRectGetHeight(self.avatarImageView.bounds) * 0.5;
    if (self.avatarImageView.layer.cornerRadius != radius) {
        self.avatarImageView.layer.cornerRadius = radius;
    }
}
```

## 阴影处理

### 总是优先设置 shadowPath

没有 `shadowPath` 时，系统需要根据 layer 内容动态计算阴影轮廓，滚动列表中尤其容易出问题。bounds 确定后设置 `shadowPath`：

```objc
- (void)layoutSubviews {
    [super layoutSubviews];

    self.cardView.layer.shadowColor = UIColor.blackColor.CGColor;
    self.cardView.layer.shadowOpacity = 0.12;
    self.cardView.layer.shadowRadius = 8.0;
    self.cardView.layer.shadowOffset = CGSizeMake(0.0, 3.0);
    self.cardView.layer.shadowPath = [UIBezierPath bezierPathWithRoundedRect:self.cardView.bounds
                                                                cornerRadius:8.0].CGPath;
}
```

如果 bounds 不变，不要反复生成 path。可以缓存上一次 bounds：

```objc
- (void)layoutSubviews {
    [super layoutSubviews];

    if (!CGRectEqualToRect(self.lastShadowBounds, self.cardView.bounds)) {
        self.lastShadowBounds = self.cardView.bounds;
        self.cardView.layer.shadowPath = [UIBezierPath bezierPathWithRoundedRect:self.cardView.bounds
                                                                    cornerRadius:8.0].CGPath;
    }
}
```

### 圆角和阴影分层处理

同一个 layer 同时 `masksToBounds = YES` 和显示阴影通常是冲突的：裁剪会把阴影也裁掉。推荐使用外层负责阴影，内层负责圆角裁剪：

```objc
// 外层 shadowContainerView 负责阴影，不裁剪
self.shadowContainerView.layer.shadowColor = UIColor.blackColor.CGColor;
self.shadowContainerView.layer.shadowOpacity = 0.12;
self.shadowContainerView.layer.shadowRadius = 8.0;
self.shadowContainerView.layer.shadowOffset = CGSizeMake(0.0, 3.0);
self.shadowContainerView.layer.shadowPath =
    [UIBezierPath bezierPathWithRoundedRect:self.shadowContainerView.bounds cornerRadius:8.0].CGPath;

// 内层 contentView 负责圆角和裁剪
self.roundedContentView.layer.cornerRadius = 8.0;
self.roundedContentView.layer.masksToBounds = YES;
```

这个模式比写一个“万能 UIView 分类”更安全，因为它明确表达了两个不同 layer 的职责。

## Mask 使用

`layer.mask` 和复杂 `CAShapeLayer` mask 很适合表达不规则形状，但不适合在滚动热路径里频繁创建和更新。

使用 mask 时：

- 在 bounds 稳定后创建 path。
- 只有 bounds 或形状参数变化时才更新 mask。
- 避免在 cell 每次 `configure` 时新建 mask。
- 对静态形状优先考虑预渲染图片或独立资源。

```objc
- (void)layoutSubviews {
    [super layoutSubviews];

    if (!CGRectEqualToRect(self.lastMaskBounds, self.imageView.bounds)) {
        self.lastMaskBounds = self.imageView.bounds;

        UIBezierPath *path = [UIBezierPath bezierPathWithRoundedRect:self.imageView.bounds
                                                        cornerRadius:12.0];
        CAShapeLayer *maskLayer = (CAShapeLayer *)self.imageView.layer.mask;
        if (![maskLayer isKindOfClass:CAShapeLayer.class]) {
            maskLayer = [CAShapeLayer layer];
            self.imageView.layer.mask = maskLayer;
        }
        maskLayer.path = path.CGPath;
    }
}
```

## 透明混合

透明混合会让 GPU 读取并混合后面的像素。单个 view 影响可能不大，但列表中大量半透明 layer 会叠加成明显成本。

优化方向：

- 不需要透明时，设置 `opaque = YES`。
- 为 view、label、cell contentView 设置明确的非透明 `backgroundColor`。
- 避免大面积 `alpha < 1.0` 的容器。
- 尽量使用无 alpha 通道的图片资源。
- 不要为了“看起来没背景”而让大量 label 背景透明叠在复杂图片上。

```objc
self.contentView.opaque = YES;
self.contentView.backgroundColor = UIColor.whiteColor;
self.titleLabel.backgroundColor = UIColor.whiteColor;
self.titleLabel.opaque = YES;
```

不要撒谎设置 `opaque = YES`：如果 view 实际包含透明内容，错误的 opaque 设置可能导致显示异常。

## Rasterize 使用

`shouldRasterize` 会把 layer 渲染成 bitmap 缓存。它适合“复杂但静态”的内容，不适合持续变化的内容。

适合考虑 rasterize 的场景：

- 复杂阴影、渐变、多个子层组合成的静态卡片。
- 内容短时间内不会变化。
- view 没有持续动画、缩放、透明度变化。
- 已实测 rasterize 后滚动或动画更稳。

使用时必须设置 `rasterizationScale`：

```objc
self.cardView.layer.shouldRasterize = YES;
self.cardView.layer.rasterizationScale = UIScreen.mainScreen.scale;
```

避免使用的场景：

- cell 内容频繁变化。
- view 正在缩放、旋转或改变 alpha。
- 大尺寸 view，bitmap 缓存内存成本高。
- 文本频繁变化，缓存不断失效。

如果只在动画期间需要，可以在动画结束后关闭：

```objc
self.cardView.layer.shouldRasterize = YES;
self.cardView.layer.rasterizationScale = UIScreen.mainScreen.scale;

[UIView animateWithDuration:0.25 animations:^{
    self.cardView.alpha = 1.0;
} completion:^(BOOL finished) {
    self.cardView.layer.shouldRasterize = NO;
}];
```

## UIView 分类的边界

可以提供 UIView 分类作为模板，但不要让分类自动 swizzle 或偷偷改变所有 view 的渲染行为。分类适合封装显式、低风险的方法：

- 设置圆角但不裁剪子视图。
- 设置阴影并要求调用方在 bounds 确定后更新 `shadowPath`。
- 为外层 shadow view 和内层 rounded content view 提供组合方法。

当前 skill 已提供可复制模板：

- `assets/snippets/UIView+OCMPerformance.h`
- `assets/snippets/UIView+OCMPerformance.m`

模板方法使用 `ocm_` 前缀。复制到业务项目时，建议替换为项目自己的三字母或公司前缀。

不建议在分类中做：

- 自动在所有 view 上开启 `shouldRasterize`。
- 自动 swizzle `layoutSubviews`。
- 不区分场景地设置 `masksToBounds = YES`。
- 在方法内部假设所有 view 的 bounds 已经稳定。

推荐分类 API 形状：

```objc
- (void)xxx_applyCornerRadius:(CGFloat)cornerRadius clipsToBounds:(BOOL)clipsToBounds;
- (void)xxx_applyShadowWithColor:(UIColor *)color
                         opacity:(CGFloat)opacity
                          radius:(CGFloat)radius
                          offset:(CGSize)offset;
- (void)xxx_updateShadowPathWithCornerRadius:(CGFloat)cornerRadius;
```

这些方法应该是“工具”，不是策略本身。真正的策略仍由具体 view 层级决定。

## 不适用场景

不要把本文件当成“所有圆角/阴影都必须改”的规则：

- 非滚动、非动画、低频展示的 view，即使有离屏渲染，也不一定值得增加复杂度。
- 单个小头像使用 `cornerRadius + masksToBounds` 可读性高，只有在实测滚动掉帧或数量很大时再预渲染。
- 动态内容持续变化时，不要盲目开启 `shouldRasterize`，缓存失效可能比直接绘制更贵。
- 视觉需求必须依赖复杂 mask、渐变或毛玻璃时，优先确认热路径和帧率，再决定是否降级视觉。
- 不要用 category 或 swizzling 自动修改所有 UIView 行为；渲染优化应由业务调用点显式选择。

## 审查清单

- 圆角：是否真的需要裁剪子视图？是否在高频 cell 中大量使用 `masksToBounds`？
- 阴影：是否设置了 `shadowPath`？path 是否只在 bounds 变化时更新？
- 圆角 + 阴影：是否拆成外层 shadow、内层 clipped content？
- Mask：是否在 `configure` 或滚动过程中重复创建 mask/path？
- 透明混合：大面积 view 是否有明确不透明背景？图片是否含不必要 alpha？
- Rasterize：内容是否足够静态？是否设置 `rasterizationScale`？是否验证过收益？
- 验证：是否用 Core Animation / Instruments 看过实际热点，而不是只凭猜测修改？
