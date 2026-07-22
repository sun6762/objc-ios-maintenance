# 性能诊断与静态巡检

当任务涉及性能优化前的定位、Instruments、Core Animation 调试、Leaks、Zombies、Main Thread Checker、MetricKit、静态扫描或需要先找高风险 Objective-C 写法时读取本文件。若任务聚焦未符号化崩溃、dSYM、UUID、MetricKit crash/hang 诊断，读取 `references/crash-symbolication-metrickit.md`。若任务聚焦 `EXC_BAD_ACCESS`、Zombie、ASan、Malloc Scribble、Guard Malloc 或野指针，读取 `references/dangling-pointer-diagnostics.md`。若任务聚焦 OOM、Jetsam、FOOM、watchdog、`0x8badf00d` 或系统终止，读取 `references/oom-watchdog-diagnostics.md`。

## 快速目录

- 先测量再优化
- Instruments 选择
- Core Animation 调试
- 内存诊断
- 主线程诊断
- 静态巡检脚本
- 优化结果记录
- 审查清单

## 先测量再优化

性能优化先回答三个问题：

- 卡在哪里：启动、首屏、滚动、转场、图片、网络、布局、内存。
- 卡在谁身上：主线程 CPU、GPU 渲染、IO、锁等待、解码、Auto Layout。
- 修改是否有效：优化前后同设备、同数据、同路径比较。

不要只凭经验套优化。比如滚动掉帧可能来自主线程 JSON 解析，而不是离屏渲染。

## Instruments 选择

常用工具：

- Time Profiler：找主线程 CPU 热点、同步 IO、JSON 解析、富文本排版、Auto Layout 计算。
- Allocations：看对象分配热点、峰值、短时间大量 autorelease 对象。
- Leaks / Memory Graph：找真实泄漏和强引用链。
- Zombies：定位野指针或过度释放。ARC 项目仍可能通过 CoreFoundation、unsafe 指针或旧代码触发。具体诊断流程见 `references/dangling-pointer-diagnostics.md`。
- Address Sanitizer / Malloc Scribble / Guard Malloc：定位 use-after-free、double free、buffer overflow 和内存破坏。不要和性能数据采集混用。
- Memory Gauge / Allocations / VM Tracker：观察 OOM、Jetsam、FOOM 的内存水位、分配热点、虚拟内存和瞬时峰值。具体流程见 `references/oom-watchdog-diagnostics.md`。
- MetricKit：聚合线上 crash、hang、CPU、内存、exit、启动和响应性趋势。涉及 dSYM、`MXCrashDiagnostic` 或 `MXHangDiagnostic` 时读 `references/crash-symbolication-metrickit.md`。
- Core Animation：看 FPS、offscreen rendering、blended layers、misaligned images。
- Network：确认首屏网络等待和重复请求。

一次只验证一个假设。不要同时改图片、约束、缓存、异步队列后再猜是哪项生效。

## Core Animation 调试

渲染类问题优先打开：

- Color Blended Layers：检查透明混合。
- Color Offscreen-Rendered：检查离屏渲染热点。
- Color Misaligned Images：检查像素未对齐或缩放。
- FPS / Hitches：看滚动或动画是否稳定。

看到红/黄颜色不等于一定要改。只处理热路径上的问题，例如列表 cell、频繁动画 view、首屏大量重复元素。

## 内存诊断

判断页面是否释放：

- 反复 push/pop 页面，观察 controller、view model、cell、timer 是否释放。
- Memory Graph 看强引用链。
- Allocations 看是否每次进入页面都增长且不回落。

判断峰值：

- 滚动大图列表、打开大图预览、批量解析数据时观察峰值。
- 关注 decoded image、NSData、NSAttributedString、大数组。
- 批处理里使用 `@autoreleasepool` 控制短期峰值。

## 主线程诊断

主线程卡顿常见来源：

- 同步磁盘或网络。
- 图片解码、缩放、圆角处理。
- JSON 解析和 model 映射。
- 大量 Auto Layout 求解。
- 富文本排版。
- 过于频繁的 `reloadData`。

可以先用 Time Profiler 的 main thread call tree 找热点，再决定把哪一段移到后台或缓存。

## 静态巡检脚本

当前 skill 提供脚本：

- `scripts/scan_objc_risks.py`

它用于扫描 Objective-C 文件中的高风险模式，例如 KVO、swizzling、timer、同步 IO、`reloadData`、`shouldRasterize`、`masksToBounds`、动态 selector 等。

示例：

```bash
python3 scripts/scan_objc_risks.py /path/to/YourProject
python3 scripts/scan_objc_risks.py /path/to/YourProject --category rendering
python3 scripts/scan_objc_risks.py /path/to/YourProject --min-level warning
python3 scripts/scan_objc_risks.py /path/to/YourProject --format json --max-findings 50
python3 scripts/scan_objc_risks.py /path/to/YourProject --fail-on-finding
```

脚本输出是“需要人工复核的风险提示”，不是确定 bug。它适合做改造前盘点、review 辅助和回归巡检。

维护脚本时运行：

```bash
python3 scripts/test_scan_objc_risks.py
```

## 优化结果记录

提交性能改动时，记录：

- 测试设备、系统版本、构建类型。
- 测试路径和数据规模。
- 优化前后指标，例如启动耗时、平均 FPS、主线程耗时、内存峰值。
- 仍未处理的风险。

没有可重复数据时，至少说明用过哪些工具、观察到什么现象、为什么选择当前改法。

## 审查清单

- 是否明确了性能问题属于启动、滚动、渲染、内存还是网络？
- 是否用 Instruments 或埋点验证瓶颈，而不是直接猜？
- 是否一次只验证一个主要假设？
- 是否区分真实泄漏、峰值过高和缓存膨胀？
- 未符号化崩溃、dSYM 或 MetricKit 诊断是否读取了 `references/crash-symbolication-metrickit.md`？
- 野指针诊断是否读取了 `references/dangling-pointer-diagnostics.md`，并区分 Zombie、ASan、Malloc Scribble 和 Guard Malloc 的适用场景？
- OOM/Jetsam/FOOM/watchdog 是否读取了 `references/oom-watchdog-diagnostics.md`，并区分内存压力和主线程无响应？
- 静态扫描结果是否经过人工判断，没有机械改所有命中？
- 性能改动是否记录了对比数据和剩余风险？
