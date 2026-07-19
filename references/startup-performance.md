# 启动性能

当任务涉及 App 启动慢、首屏慢、`AppDelegate` / `SceneDelegate` 重、`+load`、SDK 初始化、首屏网络、首帧渲染或冷启动优化时读取本文件。

## 快速目录

- 判断启动阶段
- 启动路径瘦身
- `+load` 与 `+initialize`
- 首屏与延后任务
- 主线程阻塞
- 首屏网络与缓存
- 可观测性
- 审查清单

## 判断启动阶段

先分清问题发生在哪一段：

- 进程创建到 `main`：动态库加载、类/分类加载、`+load`、静态初始化。
- `main` 到 `application:didFinishLaunchingWithOptions:` 返回：SDK 初始化、根控制器创建、配置读取。
- launch completion 到首帧：首屏 view controller 生命周期、Auto Layout、图片解码、同步数据读取。
- 首帧之后的可交互：首屏网络、列表渲染、缓存预热、埋点上报。

不要把所有启动问题都塞进 `didFinishLaunching`。先用 Instruments / App Launch / Time Profiler 或自定义埋点确认耗时位置。

## 启动路径瘦身

启动路径只保留“首屏必须同步完成”的工作：

- 根窗口、根控制器、必要的登录态或路由状态。
- 影响首屏展示的本地轻量配置。
- 必须在启动完成前注册的系统能力，例如 push category。

延后：

- 大型 SDK 初始化。
- 非首屏数据库迁移或数据预热。
- 埋点批量上报。
- 非首屏图片、字体、模板、规则加载。
- 可以等首帧后执行的远端配置刷新。

```objc
- (BOOL)application:(UIApplication *)application didFinishLaunchingWithOptions:(NSDictionary *)launchOptions {
    [self setupWindowAndRootViewController];
    [self setupRequiredServicesWithLaunchOptions:launchOptions];

    dispatch_async(dispatch_get_main_queue(), ^{
        [self startDeferredServicesAfterFirstRunLoop];
    });

    return YES;
}
```

如果任务很重，首帧后一轮主队列仍可能卡住交互。可以拆成小任务，分批执行。

## `+load` 与 `+initialize`

`+load` 会在运行时加载类/分类时自动执行，发生得早，难观测，也难控制顺序。旧项目中要重点审查：

- `+load` 中注册大量服务、读文件、初始化数据库、扫描类列表。
- 多个 category 都在 `+load` 里 swizzling。
- `+load` 内触发其它类加载或 Objective-C runtime 扫描。

规则：

- `+load` 只放极少量、不可延后的 runtime 注册逻辑。
- swizzling 必须 `dispatch_once`，并确保方法签名兼容。
- 普通业务初始化移到显式 bootstrap 流程。
- 不要依赖不同类或 category 的 `+load` 顺序。

`+initialize` 是懒触发，但也可能在首次消息发送时制造不可预测卡顿。维护旧代码时，优先改成显式、可测量、可控制的初始化方法。

## 首屏与延后任务

首屏控制器避免在 `viewDidLoad` / `viewWillAppear:` 做重活：

- 同步网络。
- 同步磁盘 IO。
- 大量 JSON 解析。
- 大图解码和裁剪。
- 大量 Auto Layout 约束创建。
- 富文本排版或复杂 attributed string 生成。

推荐形状：

```objc
- (void)viewDidLoad {
    [super viewDidLoad];
    [self setupViews];
    [self renderCachedSnapshotIfAvailable];
}

- (void)viewDidAppear:(BOOL)animated {
    [super viewDidAppear:animated];
    [self refreshVisibleDataIfNeeded];
}
```

注意：延后任务仍然要可取消。首屏控制器已经 dismiss 或路由切走后，不要继续更新旧 UI。

## 主线程阻塞

常见启动阻塞源：

- `NSData dataWithContentsOfURL:` / `NSString stringWithContentsOfFile:` 在主线程运行。
- 首屏一次性创建大量 view。
- 扫描 bundle 内所有资源、类、配置文件。
- 初始化数据库连接时同步迁移大表。
- `dispatch_sync(dispatch_get_main_queue(), ...)` 从主线程调用造成死锁。

旧代码可先做小范围替换：把非首屏 IO、解析、图片处理放到后台队列，完成后只把 UI 更新切回主队列。

## 首屏网络与缓存

首屏需要网络时，优先展示缓存或骨架状态，再刷新数据。不要为了等接口完成而阻塞 root view controller 展示。

```objc
- (void)loadInitialData {
    FeedSnapshot *snapshot = [self.cache latestSnapshot];
    if (snapshot) {
        [self renderSnapshot:snapshot];
    }

    __weak typeof(self) weakSelf = self;
    [self.service refreshWithCompletion:^(FeedSnapshot *snapshot, NSError *error) {
        dispatch_async(dispatch_get_main_queue(), ^{
            __strong typeof(weakSelf) self = weakSelf;
            if (!self) {
                return;
            }
            if (snapshot) {
                [self renderSnapshot:snapshot];
            }
        });
    }];
}
```

## 可观测性

给关键阶段加轻量埋点，至少记录：

- process start 到 `didFinishLaunching` 返回。
- root view controller 创建完成。
- 首屏 `viewDidAppear:`.
- 首屏第一批数据渲染完成。

使用埋点时不要在启动热路径同步写磁盘或发网络；先写内存，再异步落盘或上报。

## 审查清单

- `+load` / `+initialize` 是否做了业务初始化、IO 或 runtime 扫描？
- `didFinishLaunching` 是否只保留首屏必需同步工作？
- 首屏 view controller 是否在生命周期方法中同步 IO、解码、解析或建大量约束？
- 非首屏 SDK、数据预热、埋点上报是否延后且可取消？
- 首屏网络是否有缓存或轻量占位，不阻塞窗口展示？
- 是否有分阶段耗时数据，而不是凭感觉移动代码？
