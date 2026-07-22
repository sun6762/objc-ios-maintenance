# 启动性能

当任务涉及 App 启动慢、首屏慢、pre-main、dyld、动态库数量、`AppDelegate` / `SceneDelegate` 重、`+load` 统计、SDK 初始化、首屏网络、首帧渲染或冷启动优化时读取本文件。若启动、回前台、退后台或后台任务被 watchdog 终止，尤其是 `0x8badf00d`，继续读取 `references/oom-watchdog-diagnostics.md`。

## 快速目录

- 判断启动阶段
- Pre-main 耗时分解
- 启动路径瘦身
- `+load` 与 `+initialize`
- `+load` 统计与改造
- 动态库数量
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

如果 crash report 指向 watchdog 或 `0x8badf00d`，先读 `references/oom-watchdog-diagnostics.md`，确认终止阶段和主线程栈，再回到本文件拆启动路径。

## Pre-main 耗时分解

pre-main 是进程启动到进入 `main` 之前的阶段，业务代码还没进入 `AppDelegate`，但 dyld 和 Objective-C runtime 已经做了大量工作。常见成本包括：

- 加载主二进制和动态库。
- rebase / bind / lazy bind 符号。
- Objective-C class、category、selector、protocol 注册。
- C/C++ 静态初始化、全局对象构造。
- Objective-C `+load`。

排查顺序：

1. 先确认启动慢是否真在 pre-main。用 Xcode Organizer / App Launch、Instruments Time Profiler 或本地启动统计拆分阶段。
2. 本地 Debug/开发包可临时打开 dyld 统计观察趋势，但不要把它当线上精确指标。
3. 如果 pre-main 高，优先审查动态 framework 数量、`+load`、C++ 全局构造、SDK 自动注册和 category swizzling。
4. 如果 pre-main 正常，回到 `didFinishLaunching`、首帧和首屏数据渲染路径排查。

本地调试可用的 dyld 环境变量示例：

```text
DYLD_PRINT_STATISTICS=1
DYLD_PRINT_STATISTICS_DETAILS=1
```

这些输出适合看相对变化，不适合作为线上 KPI。Release、TestFlight、线上包应优先用 Organizer、MetricKit、埋点和真实设备对比。

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

## `+load` 统计与改造

旧项目要先把 `+load` 盘出来，再决定改哪些。静态搜索可以作为第一步：

```bash
rg -n "^\\+\\s*\\(void\\)\\s*load|\\+\\s*\\(void\\)load" /path/to/YourProject
rg -n "method_exchangeImplementations|objc_getClassList|objc_copyClassList|NSClassFromString" /path/to/YourProject
```

人工复核时记录：

- 类名或 category 名。
- 所属业务模块或第三方 SDK。
- 是否 swizzling，是否有 `dispatch_once`。
- 是否读文件、扫类、初始化数据库、注册大量服务或发网络。
- 是否可移动到显式 bootstrap、首帧后任务或按需懒加载。

改造原则：

- 删除无用 `+load`，把业务初始化移到明确入口，例如 `AppBootstrapper`。
- 对必须保留的 swizzling，加白名单、签名校验、`dispatch_once` 和日志。
- 第三方 SDK 的自动注册不要随意改源码；优先查 SDK 文档是否支持手动初始化或关闭 auto start。
- 改一个模块就补启动阶段数据，避免一次性移动大量初始化后难以归因。

## 动态库数量

动态 framework 数量过多会增加 dyld 加载、符号绑定和 ObjC runtime setup 成本。尤其是老项目中 CocoaPods、手动 SDK、插件化壳层同时存在时，要把动态库数量作为 pre-main 排查项。

盘点方式：

```bash
find MyApp.app/Frameworks -maxdepth 1 -name "*.framework" -print
xcrun otool -L MyApp.app/MyApp
```

审查重点：

- 是否有只被首屏后功能使用、却在启动时动态加载的 framework。
- CocoaPods 依赖是否被配置成大量 dynamic framework；能否在不破坏分发和 Swift/资源要求的前提下改为 static linkage。
- 同类 SDK 是否重复接入，例如多套埋点、推送、图片、网络或日志库。
- extension 是否携带了主 App 才需要的 framework。
- 大 framework 是否在 `+load` 或 C++ 全局构造里做了额外初始化。

不要为了减少数量盲目改链接方式。动态改静态可能影响资源 bundle、符号冲突、Swift ABI、license 和二进制体积；必须结合构建系统和发布方式验证。

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

- process start 到 `main` 或最早可记录点。如果拿不到真实 process start，使用系统/平台启动指标补充。
- `main` 到 `didFinishLaunching` 返回。
- root view controller 创建完成。
- 首屏 `viewDidAppear:`.
- 首屏第一批数据渲染完成。
- 首帧后延后任务开始/结束。

使用埋点时不要在启动热路径同步写磁盘或发网络；先写内存，再异步落盘或上报。

可用信号：

- Xcode Organizer / App Launch：看真实设备启动趋势。
- Instruments Time Profiler：定位主线程 CPU、IO、锁和初始化热点。
- MetricKit：看启动、响应性、hang 和 exit 趋势。涉及接入和 crash/hang diagnostic 解读时读 `references/crash-symbolication-metrickit.md`。
- 自定义埋点：补业务阶段，例如登录态、路由、根页面、首屏数据渲染。

同一个优化要在相同设备、相同系统、相同构建类型、相同账号和相同数据规模下比较。

## 审查清单

- 是否区分 pre-main、`didFinishLaunching`、首帧和可交互阶段？
- `+load` / `+initialize` 是否做了业务初始化、IO、数据库、SDK 启动或 runtime 扫描？
- 是否统计了业务和第三方 SDK 的 `+load`，并记录可移动到显式 bootstrap 的项目？
- 动态 framework 数量是否被盘点，是否有可延后、可合并或可改静态链接的候选？
- `didFinishLaunching` 是否只保留首屏必需同步工作？
- 首屏 view controller 是否在生命周期方法中同步 IO、解码、解析或建大量约束？
- 非首屏 SDK、数据预热、埋点上报是否延后且可取消？
- 首屏网络是否有缓存或轻量占位，不阻塞窗口展示？
- 是否有分阶段耗时数据、dyld/Organizer/MetricKit/Instruments 或埋点证据，而不是凭感觉移动代码？
- 如果出现 watchdog / `0x8badf00d`，是否读取了 `references/oom-watchdog-diagnostics.md` 并确认主线程栈和生命周期阶段？
