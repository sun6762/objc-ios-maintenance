# OOM、Jetsam、FOOM 与 Watchdog 诊断

当任务涉及 OOM、Jetsam、FOOM、内存压力、memory warning、App 被系统杀死、前台无 crash log 退出、`0x8badf00d`、watchdog termination、启动/前后台切换超时、主线程卡死或长时间无响应时读取本文件。若需要接入或解读 MetricKit crash/hang/exit diagnostic，继续读取 `references/crash-symbolication-metrickit.md`。

## 快速目录

- 先区分问题类型
- 证据收集
- OOM / Jetsam 诊断
- FOOM 推断
- Watchdog / 0x8badf00d 诊断
- 主线程卡顿监控
- 常见修复方向
- 不要做的事
- 审查清单

## 先区分问题类型

OOM/Jetsam/FOOM 和 watchdog 都可能表现为“App 没了”或“用户觉得闪退”，但根因不同：

| 类型 | 本质 | 常见现象 | 优先证据 |
| --- | --- | --- | --- |
| 泄漏 | 不再需要的对象仍被强引用链持有 | 页面反复进入后内存不回落 | Memory Graph、Leaks、Allocations |
| 峰值过高 | 对象最终会释放，但瞬间分配太多 | 打开大图、批量解析、首屏加载时突然退出 | Memory Gauge、Allocations、VM Tracker、关键路径埋点 |
| 缓存膨胀 | 缓存有意持有对象，但无上限或 key 失控 | 使用越久内存越高，收到 memory warning 后不下降 | 缓存数量/成本日志、memory warning 日志 |
| Jetsam | 系统因内存压力终止进程 | 通常没有普通 crash stack，设备日志有 jetsam 线索 | JetsamEvent、Organizer、设备诊断日志 |
| FOOM | 前台 OOM，被系统终止且常没有传统 crash | 前台使用中直接回桌面，下次启动无 crash report | 上次会话标记、内存水位、memory warning、MetricKit exit 数据 |
| Watchdog | 主线程或系统回调长期无响应，被 watchdog 杀死 | 启动、恢复、后台切换、后台任务超时 | crash report termination reason、主线程栈、hang 监控 |

不要把 OOM 都当成泄漏，也不要把 watchdog 当成内存问题。先分类，再决定工具和修复方向。

## 证据收集

先收集这些信息，再判断根因：

- 发生状态：启动、首屏、滚动、大图、前台使用、退后台、回前台、后台任务、低电量或低内存设备。
- 设备和系统：机型、系统版本、可用内存级别、是否低端设备集中。
- 版本和路径：最近发布差异、页面路径、数据规模、图片尺寸、缓存数量、WebView 数量。
- 日志和诊断：crash report、JetsamEvent、MetricKit payload、memory warning、内存水位、主线程卡顿栈、最后页面。
- 是否可复现：固定账号、固定数据、同设备同路径能否复现。

如果没有 crash report，不代表不是线上问题。Jetsam、FOOM 和部分 watchdog 场景可能更依赖设备日志、MetricKit、会话标记和业务埋点。

## OOM / Jetsam 诊断

OOM 和 Jetsam 的核心问题是内存压力。处理顺序：

1. 先判断内存曲线：持续上涨、阶梯上涨、瞬时尖峰，还是进入某页面后不回落。
2. 用 Xcode Memory Gauge 快速观察路径上的 footprint；用 Instruments Allocations 看分配热点和峰值。
3. 如果怀疑泄漏，使用 Memory Graph / Leaks 查强引用链。
4. 如果怀疑峰值，使用 Allocations / VM Tracker 观察图片解码、NSData、WebView、CoreAnimation backing store、富文本和大数组。
5. 对照设备日志或 Organizer 中的 JetsamEvent，确认是否为系统内存压力终止。

常见 Jetsam 来源：

- 图片按原图解码，而不是按展示尺寸 downsample。
- 大图预览、相册、聊天、瀑布流同时持有多张 decoded image。
- WebView、地图、视频、相机等高内存组件堆叠。
- JSON、数据库、富文本或图片批处理没有分批和 `@autoreleasepool`。
- `NSMutableDictionary` 做无上限缓存，或缓存 key 过细导致命中率低、对象持续累积。
- 页面泄漏导致 controller、cell、view model、图片任务和缓存链路一起留住。

读 JetsamEvent 时重点看：

- 被杀进程是否是目标 App。
- reason 是否指向 per-process-limit、highwater、vm-pageshortage 或类似内存压力线索。
- largest process、resident size、pages、memory status 快照是否显示 App 内存异常。
- 发生时 App 是 foreground、background 还是 suspended。

Jetsam 日志只能证明系统终止和当时内存状态，不能直接告诉你是哪一行代码泄漏。要结合内存曲线、页面路径和分配热点回到代码。

## FOOM 推断

FOOM 是 foreground out-of-memory，通常表现为前台使用中突然退出，但没有普通 crash report。它经常需要“推断”，不是单靠一个日志字段定罪。

可用信号：

- 上次会话处于 foreground active，未记录正常退出、崩溃或用户主动 kill。
- 下次启动发现上次会话未闭合，且最近记录过 memory warning 或内存水位过高。
- MetricKit 或系统诊断里出现 foreground memory resource limit exit 相关统计。
- 用户路径集中在大图、视频、WebView、长列表、批量导入或首屏大数据。

建议埋点：

- 启动时创建 session id，记录 app version、device、scene state、last screen。
- 进入前台、退后台、页面切换、大图打开、WebView 创建、批处理开始/结束时记录轻量事件。
- 收到 memory warning 时记录时间、页面、缓存数量、图片任务数和当前内存水位。
- 正常进入后台或用户注销等可识别路径时标记 session clean close。

下次启动时，如果发现上次 session 未正常闭合、无 crash report、最后状态是 foreground，且近期内存信号异常，可以标为 suspected FOOM。这个结论应写成“疑似”，后续用 MetricKit、设备日志和复现路径校准。

## Watchdog / 0x8badf00d 诊断

watchdog 是系统认为 App 在关键生命周期内长时间无响应后终止进程。`0x8badf00d` 是常见 watchdog 终止码。

高发阶段：

- 冷启动：`didFinishLaunching` 太重，或 pre-main / `+load` / SDK 初始化过慢。
- 回前台：`applicationWillEnterForeground:`、scene 激活、首屏刷新阻塞主线程。
- 退后台：`applicationDidEnterBackground:` 做同步落盘、数据库迁移、网络等待。
- 后台任务：`beginBackgroundTaskWithExpirationHandler:` 后没有及时结束，或 expiration handler 本身卡住。
- 主线程死锁：主线程调用 `dispatch_sync(dispatch_get_main_queue(), ...)`，或锁顺序反转。

读 watchdog crash report 时重点看：

- `Termination Reason`、`Termination Description` 或 exception code 是否指向 watchdog / `0x8badf00d`。
- 主线程栈停在哪里：同步 IO、数据库、JSON、图片解码、Auto Layout、锁、网络等待、SDK 初始化。
- 其他线程是否持有主线程等待的锁、队列或 semaphore。
- 崩溃发生阶段：launch、resume、suspend、background task、scene transition。

watchdog 的修复通常不在“防崩溃”，而在缩短关键生命周期回调、避免主线程阻塞、拆分任务和取消后台工作。

## 主线程卡顿监控

线上 watchdog 往往很难复现，建议加轻量主线程卡顿监控，但要控制开销。

监控思路：

- 在主线程 run loop 记录进入/退出状态，后台线程检测主线程是否长时间停在同一状态。
- 或周期性向主队列投递 ping，超过阈值未响应时采样主线程栈。
- 记录页面、业务动作、CPU、内存水位、线程数、队列名和最近操作。

阈值建议分层：

- 轻微卡顿：几百毫秒级，只做聚合统计。
- 严重卡顿：数秒级，采样主线程栈和上下文。
- watchdog 风险：接近系统生命周期超时前，必须重点看启动、前后台切换和后台任务。

不要在卡顿监控里频繁符号化、写大文件或同步上报。采样数据先放内存或轻量落盘，异步、限频、脱敏后上报。

## 常见修复方向

OOM / Jetsam / FOOM：

- 图片按展示尺寸 downsample，避免直接解码原图；列表图片任务可取消并限制并发。
- 大图、WebView、视频、地图等高内存组件避免堆叠，页面消失后释放非必要资源。
- 缓存使用 `NSCache` 或明确的 count/cost limit，收到 memory warning 时清理可重建缓存。
- 批量解析、导入、图片处理使用分批和局部 `@autoreleasepool`。
- 列表分页加载，避免一次性持有全部 model、富文本、图片和 cell 状态。
- 修复页面不释放、timer/observer/KVO/block retain cycle，避免泄漏叠加成 OOM。

Watchdog / `0x8badf00d`：

- 启动路径只保留首屏必需同步任务，非首屏 SDK 和预热首帧后延后。
- `+load` / `+initialize` 不做业务初始化、IO、数据库或 runtime 大扫描。
- 生命周期回调不等待网络，不同步写大文件，不做数据库大迁移。
- 主线程不做 JSON 大解析、图片解码、富文本排版或复杂 Auto Layout 批量计算。
- 避免主线程 `dispatch_sync`、锁等待、semaphore 等同步等待。
- 后台任务要保存 task id，完成或超时时调用 `endBackgroundTask:`。

## 不要做的事

- 不要把所有内存上涨都归类为泄漏；先区分 leak、peak 和 cache growth。
- 不要只在高端设备验证内存；Jetsam 往往先在低内存设备暴露。
- 不要把 watchdog 当普通 crash 修；它通常是主线程响应和生命周期超时问题。
- 不要在 crash handler 里试图处理 OOM；OOM 发生时进程可能没有机会执行任何清理逻辑。
- 不要用 runtime guard、swizzling 或 `@try/@catch` 解决 OOM、Jetsam、FOOM 或 watchdog。

## 审查清单

- 是否区分了泄漏、峰值、缓存膨胀、Jetsam、FOOM 和 watchdog？
- 是否收集了设备、系统、版本、页面路径、数据规模和最后状态？
- OOM 是否有内存曲线、分配热点、缓存数量、图片尺寸或 WebView 数量证据？
- FOOM 是否只是“疑似”结论，并结合 session 标记、memory warning、内存水位和 MetricKit/设备日志校准？
- MetricKit crash/hang/exit diagnostic 是否进入 `references/crash-symbolication-metrickit.md`，并和 dSYM/符号化 crash log 区分使用？
- watchdog 是否读取了 termination reason、主线程栈、发生阶段和锁/队列等待关系？
- 修复是否落在图片、缓存、批处理、页面释放、启动瘦身、主线程 IO/锁/解析这些真实源头？
- 是否说明 OOM/Jetsam/FOOM/watchdog 不能靠 runtime guard 兜底？
