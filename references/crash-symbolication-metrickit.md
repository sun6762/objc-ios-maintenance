# 崩溃日志符号化、dSYM 管理与 MetricKit 接入

当任务涉及线上 crash log、未符号化栈、dSYM 丢失、UUID 不匹配、第三方 SDK 崩溃、崩溃平台接入、MetricKit、`MXDiagnosticPayload`、`MXCrashDiagnostic`、`MXHangDiagnostic` 或需要把线上诊断数据回连到 Objective-C 代码时读取本文件。

## 快速目录

- 先确认诊断链路
- Crash log 先读什么
- dSYM 与 UUID 匹配
- 符号化流程
- dSYM 管理策略
- 第三方 SDK 与历史包
- MetricKit 接入
- MetricKit 数据怎么读
- 回到 Objective-C 修复
- 隐私与留存
- 审查清单

## 先确认诊断链路

崩溃治理的第一步不是改代码，而是确认这次崩溃能不能被稳定定位：

1. crash log 是否完整，至少包含 app 版本、build、设备、系统、exception、thread backtrace 和 binary images。
2. 崩溃栈是否已经符号化，是否能看到业务类、方法名和行号。
3. 目标版本的 app binary、dSYM、第三方动态库 dSYM 是否都能找到。
4. dSYM UUID 是否和 crash log 里的 binary image UUID 一致。
5. 是否有 MetricKit、业务埋点、最近页面、最后一次网络/缓存/路由状态辅助分类。

如果栈没有符号化，后续所有“根因分析”都只能算猜测。先把符号化链路补齐。

## Crash log 先读什么

拿到 crash report 后，先定位这些字段：

- `Exception Type` / `Exception Codes`：区分 Objective-C exception、`EXC_BAD_ACCESS`、`SIGABRT`、watchdog、资源终止等。
- `Termination Reason`：如果出现 watchdog、Jetsam 或 resource limit，继续读 `references/oom-watchdog-diagnostics.md`。
- `Triggered by Thread`：先看触发线程，再看主线程是否被锁、队列或同步 IO 卡住。
- crashed thread backtrace：关注第一个业务栈帧，不要只看最顶层系统函数。
- `Last Exception Backtrace`：Objective-C exception 常见关键证据。
- `Binary Images`：记录 app binary 和相关 framework 的 load address、UUID、架构。

常见判断：

- `objc_exception_throw` / `-[NSException raise]`：优先看 exception reason 和 `Last Exception Backtrace`。
- `objc_msgSend` / `EXC_BAD_ACCESS`：读 `references/dangling-pointer-diagnostics.md`，再用 Zombie/ASan 回查释放栈。
- `0x8badf00d` 或 watchdog：读 `references/oom-watchdog-diagnostics.md`，重点看主线程栈和生命周期阶段。
- 第三方 framework 顶栈：先确认对应 framework dSYM 是否匹配，避免把未符号化地址误判成系统问题。

## dSYM 与 UUID 匹配

dSYM 必须和发生崩溃的二进制一一匹配。只看版本号不够，必须看 UUID。

常用检查：

```bash
dwarfdump --uuid MyApp.app/MyApp
dwarfdump --uuid MyApp.app.dSYM
dwarfdump --uuid SomeSDK.framework.dSYM
```

也可以用 Spotlight 查本机是否存在对应 UUID：

```bash
mdfind "com_apple_xcode_dsym_uuids == <UUID>"
```

判断规则：

- crash log 的 `Binary Images` 中 app binary UUID 必须能在 app dSYM 中找到。
- 如果崩溃栈落在动态 framework，framework 的 UUID 也要匹配对应 dSYM。
- Debug、Ad Hoc、TestFlight、App Store、企业包的 dSYM 不能混用，除非 UUID 完全一致。
- 同一个版本号重新 archive 后也可能产生不同 UUID。归档策略必须以 archive/build id/UUID 为准。

如果 UUID 不匹配，不要强行符号化。错误符号会把排查方向带偏。

## 符号化流程

推荐优先使用稳定工具链和 crash 平台：

1. Xcode Organizer 或 App Store Connect 下载/查看对应版本 crash。
2. 确认本机或 crash 平台已经拥有匹配 dSYM。
3. 让平台自动符号化；若失败，手工用 UUID 定位缺失 dSYM。
4. 对单个地址可用 `atos` 校验，确认 load address 和架构正确。

手工校验单个地址时，使用 crash report 中 `Binary Images` 的 load address：

```bash
xcrun atos -arch arm64 \
  -o MyApp.app.dSYM/Contents/Resources/DWARF/MyApp \
  -l <load_address> \
  <crashed_address>
```

注意：

- `-arch` 要和 crash report 架构一致，例如 `arm64`。
- `-l` 使用 binary image 的 load address，不是崩溃地址。
- 如果是 framework 崩溃，`-o` 指向该 framework 的 DWARF 文件。
- 只符号化一帧适合验证 dSYM，完整事故分析仍应拿完整符号化 report。

## dSYM 管理策略

线上崩溃治理必须把 dSYM 当作发布产物保存，而不是依赖某台开发机。

建议归档字段：

- app version、build number、git commit、branch、archive 时间。
- archive id 或 CI build id。
- app binary UUID 和所有 embedded framework UUID。
- app dSYM、extension dSYM、watch app/extension dSYM、第三方动态库 dSYM。
- 上传到 crash 平台和内部存储的结果。

CI 建议：

- 每次 archive 后自动导出 dSYM 并压缩保存。
- 上传 dSYM 到 crash 平台时校验返回结果，失败要让发布流程告警。
- 保存 `dwarfdump --uuid` 输出，便于线上 crash 反查。
- App Store/TestFlight 构建如果需要从 App Store Connect 获取处理后的 dSYM，要把下载动作纳入发布后检查。
- 清理策略按版本支持周期和合规要求制定，不要只保留最近一个包。

目录命名示例：

```text
symbols/
  2026-07-22_1.8.0_4802_<git-sha>/
    MyApp.app.dSYM.zip
    Frameworks.dSYM.zip
    uuids.txt
    manifest.json
```

## 第三方 SDK 与历史包

旧 Objective-C 项目常见问题不是业务 dSYM 丢失，而是依赖的 framework 没有符号：

- 手动集成的闭源 SDK 需要供应商提供对应版本 dSYM。
- CocoaPods / Carthage / SPM 生成的动态库也要进入 dSYM 归档。
- Extension、Notification Service、Share Extension 是独立 binary，dSYM 要分别保存。
- 历史开启 Bitcode 或服务端重新处理的包，要以最终可下载的 dSYM 为准。

如果第三方 SDK 只能给到部分符号，至少记录 SDK 名称、版本、UUID 和顶层调用路径。业务栈能证明是传入参数、线程或生命周期导致时，仍应从业务边界修复。

## MetricKit 接入

MetricKit 适合补线上设备侧诊断：crash、hang、CPU exception、disk write、exit reason、启动/响应性等指标。它不能替代 crash log 和 dSYM，也不能保证每次崩溃都有 payload。

Objective-C 接入骨架：

```objc
#import <MetricKit/MetricKit.h>

@interface OCMMetricSubscriber : NSObject <MXMetricManagerSubscriber>
@end

@implementation OCMMetricSubscriber

- (void)start {
    if (@available(iOS 13.0, *)) {
        [[MXMetricManager sharedManager] addSubscriber:self];
    }
}

- (void)stop {
    if (@available(iOS 13.0, *)) {
        [[MXMetricManager sharedManager] removeSubscriber:self];
    }
}

- (void)didReceiveMetricPayloads:(NSArray<MXMetricPayload *> *)payloads API_AVAILABLE(ios(13.0)) {
    for (MXMetricPayload *payload in payloads) {
        [self uploadMetricPayload:payload.dictionaryRepresentation];
    }
}

- (void)didReceiveDiagnosticPayloads:(NSArray<MXDiagnosticPayload *> *)payloads API_AVAILABLE(ios(14.0)) {
    for (MXDiagnosticPayload *payload in payloads) {
        [self uploadDiagnosticPayload:payload.dictionaryRepresentation];
    }
}

@end
```

接入要求：

- subscriber 要有进程级生命周期，不要用会提前释放的临时对象。
- 上传要异步、限频、可失败重试，不能阻塞启动、前后台切换或 crash/hang 诊断路径。
- Debug 可用 Xcode 的模拟 MetricKit payload 验证解析链路，但不要用模拟数据判断线上分布。
- 按当前 SDK 检查 API availability 和 deprecation；旧系统要降级为空实现。

## MetricKit 数据怎么读

MetricKit payload 通常用于补充趋势和上下文：

- `MXCrashDiagnostic`：看 call stack tree、异常类型、信号、终止信息，和 crash 平台栈互相校验。
- `MXHangDiagnostic`：看主线程或关键线程是否长时间无响应，和 watchdog/卡顿监控互相校验。
- CPU exception / disk write diagnostics：定位 CPU 过量、磁盘写入过量等系统诊断。
- exit reason / memory 相关指标：辅助判断 FOOM、Jetsam、后台退出或用户主动结束。
- launch / responsiveness metrics：观察启动、首屏和交互响应性趋势。

阅读原则：

- 先聚合版本、设备、系统、页面和最近发布差异，再看单条 payload。
- 用 MetricKit 证明“哪类问题在增加”，用符号化 crash log 和复现路径定位“哪一行需要改”。
- 对 hang/watchdog，优先看主线程栈、锁等待、同步 IO、数据库、JSON、图片解码和 SDK 初始化。
- 对 memory/exit，优先结合 session 标记、memory warning、内存水位和最后页面，不要把所有退出都归为 OOM。

## 回到 Objective-C 修复

符号化和 MetricKit 的目标是把线上信号落回代码边界：

1. 根据栈帧定位业务类和方法，确认是否涉及公开 `.h`、Swift 导入或 category/swizzling。
2. 对 Objective-C exception，优先修输入边界、集合构造、KVC key、列表状态一致性。
3. 对 `EXC_BAD_ACCESS`，读野指针诊断 reference，回查属性所有权、CF bridge、MRC 文件、timer/observer/KVO 和异步取消。
4. 对 hang/watchdog，读 OOM/watchdog reference，缩短生命周期回调和启动热路径。
5. 对第三方 SDK 顶栈，确认业务传参、线程、初始化顺序和 SDK 版本，再决定升级、隔离或反馈供应商。

每个高优先级崩溃要留下闭环记录：

- 符号化 report 链接或关键栈。
- dSYM UUID 匹配证据。
- MetricKit/业务日志/设备日志补充证据。
- 根因和最小修复位置。
- 验证方式和灰度观察指标。

## 隐私与留存

上传 crash 和 MetricKit 数据时，默认脱敏：

- 不上传 token、cookie、手机号、身份证、地址、完整请求体或用户输入原文。
- 页面、接口、业务 id 尽量用枚举、脱敏 id 或 hash。
- call stack、设备、系统、版本、线程、内存水位、耗时和错误码通常足够排查。
- dSYM 是发布调试资产，不应公开分发；内部存储要控制权限和留存周期。

## 审查清单

- crash log 是否完整且已符号化？
- app binary、extension、framework 的 dSYM UUID 是否和 crash log 匹配？
- CI 是否保存 dSYM、UUID manifest，并上传到 crash 平台？
- 第三方 SDK、动态 framework、extension 是否都有对应 dSYM？
- 手工 `atos` 时架构、load address、DWARF 文件是否正确？
- MetricKit subscriber 生命周期是否足够长，上传是否异步、限频、脱敏？
- 是否区分 crash log 的精确定位价值和 MetricKit 的趋势/补充价值？
- crash/hang/OOM/watchdog 是否按对应 reference 继续分类，而不是混成“崩溃率”一个指标？
