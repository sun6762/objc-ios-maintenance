# 野指针与内存访问崩溃诊断

当任务涉及 `EXC_BAD_ACCESS`、`SIGSEGV`、`KERN_INVALID_ADDRESS`、`objc_msgSend` 崩溃、message sent to deallocated instance、use-after-free、double free、over-release、`assign` 对象、`__unsafe_unretained`、MRC 文件或 CoreFoundation bridge 所有权时读取本文件。

## 快速目录

- 先判断是不是野指针
- 工具选择顺序
- Zombie Objects
- Address Sanitizer
- Malloc Scribble
- Guard Malloc
- 从报告回到代码
- 常见修复方向
- 不要做的事
- 审查清单

## 先判断是不是野指针

看到下面线索时，优先怀疑野指针、释放后访问或内存破坏：

- crash type 是 `EXC_BAD_ACCESS`、`SIGSEGV`、`BUS_ADRERR`、`KERN_INVALID_ADDRESS`。
- 崩溃栈停在 `objc_msgSend`、`objc_retain`、`objc_release`、`CFRelease`、`free`、`memcpy`、`-[NSObject respondsToSelector:]` 附近。
- 控制台出现 `message sent to deallocated instance`。
- 崩溃地址像小地址、已释放对象地址、重复字节模式，或每次崩在不同位置。
- 最近改动涉及 `assign` 对象、`__unsafe_unretained`、MRC、CoreFoundation bridge、timer、KVO、notification、C buffer 或 C++ 对象生命周期。

不要把所有 `EXC_BAD_ACCESS` 都归因于 Objective-C 野指针。C/C++ 越界、栈破坏、重复释放、block 生命周期和 CF bridge 错误也会表现成类似崩溃。

## 工具选择顺序

按最可能的问题选择工具，不要一次全开。诊断工具会改变内存布局和时序，多个工具同时启用可能掩盖真实问题。

```text
疑似 Objective-C 对象释放后继续收消息
        -> 先开 Zombie Objects

疑似 C/CF/C++ 越界、double free、use-after-free、bridge 错误
        -> 先开 Address Sanitizer

低频、时序敏感，Zombie/ASan 没抓到，但怀疑释放后访问或内存破坏
        -> 再用 Malloc Scribble / Guard Malloc 辅助复现
```

建议固定复现路径、设备型号、系统版本、构建配置和账号数据。每次只换一个诊断开关，记录开关组合和现象变化。

## Zombie Objects

Zombie 适合定位 Objective-C 对象释放后继续收到消息。

开启方式：

1. 在 Xcode 选择目标 scheme。
2. 打开 `Product -> Scheme -> Edit Scheme...`。
3. 选择 `Run -> Diagnostics`。
4. 勾选 `Enable Zombie Objects`。
5. 用 Debug 构建复现崩溃。

也可以使用 Instruments 的 Zombies 相关能力观察对象的 retain/release 生命周期。不同 Xcode 版本的入口可能变化；如果模板不可见，优先使用 Scheme Diagnostics 的 Zombie 开关。

怎么看：

- 控制台通常会出现类似 `message sent to deallocated instance` 的信息。
- 记录对象 class、对象地址、收到的 selector 和当前线程栈。
- 如果 Instruments 能展示对象历史，重点看 allocation stack、最后一次 release/dealloc stack、崩溃时发送消息的 stack。
- 如果命中的是 view controller、view、cell、view model 或 service，继续查页面退出后的 block、timer、display link、notification、KVO、delegate 回调。

局限：

- Zombie 会让已释放对象不真正释放，不能用来判断泄漏和内存峰值。
- Zombie 主要针对 Objective-C 对象；C buffer 越界、纯 C++ 对象、OOM 和大多数内存破坏不靠它定位。
- 低频竞态可能因为 Zombie 改变内存布局而消失。

## Address Sanitizer

ASan 适合定位内存访问错误，尤其是 use-after-free、buffer overflow、double free 和部分栈/全局内存越界。

开启方式：

1. 打开 `Product -> Scheme -> Edit Scheme...`。
2. 选择 `Run -> Diagnostics`。
3. 勾选 `Address Sanitizer`。
4. 重新运行并按固定路径复现。

怎么看：

- 先看错误类型：`heap-use-after-free`、`stack-use-after-scope`、`heap-buffer-overflow`、`global-buffer-overflow`、`attempting double-free`。
- 再看三组栈：出错访问栈、对象分配栈、释放栈。修复通常落在分配和释放之间的所有权边界。
- 如果报告指向 `CFRelease`、`CFRetain`、`__bridge_transfer`、`CFBridgingRelease`，回到 Create/Copy/Get 规则检查是否重复释放或漏转移所有权。
- 如果报告指向 `memcpy`、`bytes`、`malloc`、C 数组、图片 buffer 或 C++ 容器，按长度、容量、生命周期和线程并发方向查。

局限：

- ASan 开销明显，只适合 Debug、测试包或本地复现。
- ASan 不能证明线上问题已全部解决；修复后仍要走原复现路径和回归用例。
- 某些第三方库、汇编、系统库或优化构建可能让栈不完整。

## Malloc Scribble

Malloc Scribble 适合让释放后访问和未初始化内存使用更容易暴露。

开启方式：

1. 打开 `Product -> Scheme -> Edit Scheme...`。
2. 选择 `Run -> Diagnostics`。
3. 勾选 `Malloc Scribble`。必要时再配合 `Malloc Stack` / `Malloc Stack Logging` 类诊断项记录分配栈。
4. 复现低频路径，观察崩溃是否提前或变得稳定。

怎么看：

- 已释放或未初始化内存可能出现稳定填充值，崩溃地址或对象内容会更像“被写坏”。
- 如果开启后崩溃位置从业务深处提前到某个写入、释放或拷贝附近，优先查这个边界。
- 结合 Zombies/ASan 的栈，确认是释放后访问、未初始化读，还是越界写导致后续对象损坏。

局限：

- 它通常提供线索，不一定直接指出根因。
- 会改变内存内容和时序，低频问题可能消失或表现改变。

## Guard Malloc

Guard Malloc 适合捕捉越界写、释放后访问和堆内存破坏，尤其是小范围可复现路径。

开启方式：

1. 打开 `Product -> Scheme -> Edit Scheme...`。
2. 选择 `Run -> Diagnostics`。
3. 勾选 `Guard Malloc`。
4. 尽量只跑最小复现路径。

怎么看：

- Guard Malloc 可能让越界访问在更靠近出错写入的位置崩溃。
- 如果崩溃从随机位置变成稳定位置，优先看该栈附近的 buffer 长度、对象释放、`memcpy`、`strcpy`、C 数组和跨线程访问。
- 对 `EXC_BAD_ACCESS` 地址和线程栈做记录，再关掉 Guard Malloc 对比是否回到原始线上形态。

局限：

- 开销很大，会显著改变内存布局和性能。
- iOS 真机排查优先使用 ASan；Guard Malloc 的可用性受平台和运行环境限制，更适合小范围本地复现。
- 不适合大规模流程、性能判断或内存峰值判断。

## 从报告回到代码

把工具报告翻译成 Objective-C 维护动作：

| 报告线索 | 优先检查 |
| --- | --- |
| `message sent to deallocated instance`，class 是 view controller/view model/service | block 强弱引用、timer/display link、notification token、KVO add/remove、异步任务取消、delegate 生命周期 |
| 崩在 `objc_msgSend`，对象属性是 `assign` 或 `__unsafe_unretained` | 属性改为 `weak` / `strong` / `copy`，或明确 owner 生命周期；避免旧式非置零弱引用 |
| ASan `heap-use-after-free` 指向 CF 对象 | `__bridge` / `__bridge_transfer` / `CFBridgingRelease` / `CFRelease` 是否重复转移或重复释放 |
| ASan `heap-buffer-overflow` 指向 C API | buffer 长度、`sizeof`、编码长度、图片/音视频数据 stride、`NSData bytes` 生命周期 |
| `attempting double-free` | MRC retain/release、CFRelease、C malloc/free、C++ RAII 和所有权交接 |
| 低频随机崩溃，Guard Malloc 后位置提前 | 先修最早稳定崩溃点，不要只处理最终 `objc_msgSend` 栈 |

如果只有线上崩溃日志没有本地复现，先补符号化、版本范围、最近发布差异、用户路径和关键对象生命周期日志。不要为了降低崩溃率直接上 runtime guard。

## 常见修复方向

- ARC 下 Objective-C 对象属性不要用 `assign`；delegate/back reference 用 `weak`，owned object 用 `strong`，block 和值语义对象用 `copy`。
- 避免 `__unsafe_unretained`，除非有明确旧系统兼容要求并能证明 owner 长寿。
- MRC 文件要成对检查 retain/release/autorelease，尤其是早返回、异常路径和跨线程回调。
- CoreFoundation 按 Create/Copy/Get 判断所有权；同一个对象不要既 `__bridge_transfer` 又手动 `CFRelease`。
- timer、display link、KVO、notification、URLSession task 和 operation 要有明确取消或 teardown 路径。
- C/C++ buffer 要校验长度和容量，避免把 `NSData bytes`、栈变量地址或临时 C++ 对象保存到异步回调里。

## 不要做的事

- 不要用 runtime 完全转发、`forwardInvocation:` 或全局 category 试图兜住野指针。
- 不要在没有证据时把 `EXC_BAD_ACCESS` 归因于某个最近改动。
- 不要同时开启所有诊断工具后直接判断性能、内存峰值或泄漏。
- 不要只看最终崩溃栈。内存破坏经常在更早的位置发生，最终栈只是受害者。

## 审查清单

- 是否先判断是 Objective-C 对象释放后访问，还是 C/CF/C++ 内存访问错误？
- Zombie 是否给出了 class、selector、对象地址和释放/访问栈？
- ASan 是否明确了错误类型、访问栈、分配栈和释放栈？
- Malloc Scribble / Guard Malloc 是否只用于最小复现路径，并记录了开关组合？
- 是否检查了 `assign` 对象、`__unsafe_unretained`、MRC、CF bridge、timer、observer、KVO 和异步取消？
- 是否明确说明 runtime guard 不能证明野指针问题被解决？
