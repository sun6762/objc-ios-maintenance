# 内存、泄漏与对象生命周期性能

当任务涉及内存上涨、页面不释放、图片内存、缓存、循环引用、`autoreleasepool`、Core Graphics/CF 对象释放、timer/display link 或内存警告时读取本文件。

## 快速目录

- 先区分内存问题类型
- 页面不释放
- Timer / DisplayLink / Observer
- 图片内存
- 缓存策略
- Autoreleasepool
- Core Graphics 与 CF
- 审查清单

## 先区分内存问题类型

内存问题常见有三类：

- 泄漏：对象已经不可能再使用，但仍被强引用链持有。
- 峰值过高：对象最终会释放，但短时间分配太多，可能触发 jetsam。
- 缓存膨胀：缓存符合预期地持有对象，但没有上限或失效策略。

用 Instruments / Allocations / Leaks / Memory Graph 先看是哪一类。不要把所有内存上涨都当成 retain cycle。

## 页面不释放

页面退出后不释放，优先检查：

- self 持有 block，block 强捕获 self。
- timer / display link 持有 target。
- block 形式 notification observer token 没保存或没移除。
- KVO 没移除，或 observation 对象被强持有链留住。
- 子对象 delegate 用 strong。
- associated object 隐藏持有 owner。

在 Objective-C 旧项目里，可以临时加 `dealloc` 日志验证生命周期，但不要把日志长期留在业务代码里。

```objc
- (void)dealloc {
    [_timer invalidate];
    [_displayLink invalidate];

    if (_notificationToken) {
        [[NSNotificationCenter defaultCenter] removeObserver:_notificationToken];
    }
}
```

弱捕获只能解决 block 捕获问题，不能替代取消任务、移除 observer 或失效 timer。

## Timer / DisplayLink / Observer

`NSTimer` 和 `CADisplayLink` 会持有 target。重复触发任务要有明确生命周期：

- 页面可见才需要时，在 `viewWillAppear:` 启动，在 `viewWillDisappear:` 停止。
- 页面生命周期内才需要时，在 `dealloc` 兜底 invalidate。
- 用 weak proxy 可以打断 target 循环，但 timer 自身仍要失效。

当前 skill 提供弱代理模板：

- `assets/snippets/OCMWeakProxy.h`
- `assets/snippets/OCMWeakProxy.m`

使用模板时，把 `OCM` 前缀替换成项目自己的前缀。

## 图片内存

图片内存成本按解码后像素计算，不按文件大小计算。粗略公式：

```text
width * height * scale * scale * 4 bytes
```

规则：

- 列表小图按展示尺寸缩放和解码，不要直接持有原图。
- 大图预览使用分辨率受控的预览图，必要时再加载原图。
- 头像圆角可以预渲染成目标尺寸 bitmap，并把圆角半径写入缓存 key。
- 不需要透明的图片渲染使用 opaque 上下文，减少混合成本。
- 页面消失后释放不再需要的大图和中间处理结果。

## 缓存策略

`NSCache` 适合内存缓存，因为系统内存紧张时可以自动清理。不要用无上限 `NSMutableDictionary` 长期缓存图片、高度或富文本结果。

```objc
@interface ImageStore ()
@property (nonatomic, strong) NSCache<NSString *, UIImage *> *memoryCache;
@end

- (instancetype)init {
    self = [super init];
    if (self) {
        _memoryCache = [[NSCache alloc] init];
        _memoryCache.countLimit = 300;
        _memoryCache.totalCostLimit = 30 * 1024 * 1024;
    }
    return self;
}
```

缓存 key 必须包含影响结果的参数，例如 URL、尺寸、scale、圆角、渲染模式、字体配置或内容版本。

## Autoreleasepool

大量循环处理图片、JSON、字符串或临时 Foundation 对象时，ARC 也可能产生很高 autorelease 峰值。后台批处理里可以局部使用 `@autoreleasepool`。

```objc
dispatch_async(self.processingQueue, ^{
    for (NSData *data in dataList) {
        @autoreleasepool {
            Model *model = [self.parser parseData:data];
            [self.store appendModel:model];
        }
    }
});
```

不要在普通小方法里到处加 `@autoreleasepool`。它适合长循环和批量处理边界。

## Core Graphics 与 CF

维护绘图、音视频、地址簿、Security、CoreText 等代码时，按 Create/Copy/Get 规则确认释放路径：

- `Create` / `Copy` 返回的对象需要释放或转移给 ARC。
- `Get` 返回的对象通常不拥有。
- `__bridge_transfer` / `CFBridgingRelease` 后不要再手动 release。

对多 return 分支，优先把释放写到清晰的 cleanup 路径，避免成功分支释放、失败分支泄漏。

## 审查清单

- 页面退出后 controller/cell/view model 是否释放？
- block、timer、display link、observer、KVO 是否形成隐藏强引用链？
- 缓存是否有上限，key 是否包含所有影响渲染结果的参数？
- 图片是否按展示尺寸处理，是否避免持有无必要原图？
- 批量处理是否有局部 `@autoreleasepool` 控制峰值？
- CF/Core Graphics 对象是否只有一个明确 owner 负责释放？
- 内存优化是否用 Allocations / Leaks / Memory Graph 验证？
