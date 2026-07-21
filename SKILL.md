---
name: objc-ios-maintenance
description: "维护、审查、重构、现代化或调试 Objective-C iOS 项目。用于 .h/.m/.mm、UIKit、ARC 所有权、block/retain cycle、NSError、线程与异步、CoreFoundation bridge、KVC/KVO、runtime/category/swizzling、Swift 混编、Auto Layout、列表滚动、UIKit 渲染、启动、内存、崩溃、网络缓存、性能诊断、静态风险巡检、新手 OC + UIKit 架构和从零编写保守安全代码。"
---

# Objective-C iOS 维护与安全开发

当任务涉及 Objective-C iOS 代码库时使用这个 skill。维护既有项目时，默认采用小范围、兼容调用方、尊重运行时行为的方式；从零编写 OC + UIKit 功能或用户经验不清晰时，默认进入“新手安全层”，优先生成保守、可取消、主线程安全、少运行时魔法的代码。

## 内容目录

- [边界](#边界)
- [Skill 目录结构与维护入口](#skill-目录结构与维护入口)
- [维护工作流](#维护工作流)
- [新手安全层](#新手安全层)
- [任务路由决策树](#任务路由决策树)
- [引用资料路由](#引用资料路由)
- [标准输出格式](#标准输出格式)
- [可用代码模板](#可用代码模板)
- [可用脚本](#可用脚本)
- [核心规则](#核心规则)
- [常见错误](#常见错误)
- [审查清单](#审查清单)

## 边界

这个 skill 是 Objective-C iOS 旧项目维护的总入口，覆盖常见 UIKit、ARC、runtime、Swift 混编、性能和崩溃问题。它按 `SKILL.md` + `references/` + `scripts/` + `assets/` 的通用 Agent Skill 结构组织，可被 Codex 和 Claude Code 读取。保持“一个总 skill + 多个 references”的组织方式；不要把它拆成多个子 skill，除非用户后续明确要求。

直接处理：

- Objective-C `.h`、`.m`、`.mm` 代码审查、修复、重构和现代化。
- UIKit view controller、cell、delegate/data source、Auto Layout、滚动、渲染和启动性能。
- ARC 所有权、block 循环引用、KVO/KVC、CoreFoundation bridge、runtime/category/swizzling 风险。
- 网络、缓存、并发、异步结果时序和崩溃边界。
- 新手或经验不明确场景下的 OC + UIKit 页面、列表、网络、model 和基础分层代码。

不直接处理：

- 大规模 Swift 重写或架构迁移，除非用户明确要求。
- 纯 Swift/SwiftUI 新功能设计；只处理与 Objective-C 维护或混编相关的部分。
- 用全局 swizzling/category 吞异常作为默认“防崩溃”方案；只有用户明确接受副作用时才讨论隔离方案。
- 没有证据的性能大改。先给出假设和验证方式，再做最窄改动。

## Skill 目录结构与维护入口

当前会话中，这个 skill 的维护目录为 `/Users/bobo/develop/objc-ios-maintenance`。后续对该 skill 的增补、翻译、脚本和资源维护都在这个目录下进行。若将 skill 复制到其他机器，按复制后的 skill 根目录解析相对路径。

按 Codex / Claude Code 兼容的 Agent Skill 结构维护如下：

```text
objc-ios-maintenance/
├── SKILL.md              # 必需：skill 入口、触发描述、核心工作流与引用路由
├── agents/
│   └── openai.yaml       # 推荐：用于 Codex/OpenAI UI 展示；Claude Code 可忽略
├── scripts/              # 可选：放可执行脚本；当前包含 Objective-C 风险巡检脚本
├── references/           # 可选：放按需读取的长文档；当前存放 Objective-C 维护专题资料
├── assets/               # 可选：放模板、图片、字体、示例工程等资源；当前包含 UIView 渲染性能分类和 weak proxy 模板
└── evals/                # 可选：放 skill 行为评测用例，用于后续回归验证
```

维护这个 skill 时，保持 `SKILL.md` 精简，只放触发信息、工作流、核心规则和引用路由；把较长的专题说明放入 `references/`，并从 `SKILL.md` 明确说明什么时候读取。

## 维护工作流

1. 先识别项目边界，再动手修改。
   - 确认文件是否涉及 ARC、非 ARC 编译标记、`.mm`、生成的 Swift 头文件、bridging header、category、swizzling、KVO、associated object 或 CoreFoundation 所有权。
   - 把 `.h` 文件当作 API 契约处理。修改 nullability、generics、selector 名称时要考虑 Swift 导入结果和所有调用方。
2. 先保持行为，再考虑现代化。
   - 除非任务需要，不要随意做 Swift 重写、架构迁移或替换 UIKit 流程。
   - 保持周围代码既有的 Objective-C 命名、delegate 模式和错误处理约定。
3. 每次修改都检查所有权和线程契约。
   - 确认属性修饰符、block 捕获、回调队列、UIKit 主线程访问和 CoreFoundation bridge 所有权。
4. 按 Objective-C runtime 规则在脑中编译一遍。
   - selector 拼写、category 冲突、KVC key、KVO 添加/移除平衡、swizzled 方法签名、Swift 生成名，和类型语法同样重要。
5. 用最窄的有效方式验证。
   - 优先使用既有 Xcode scheme、测试命令或目标构建命令。无法验证时，明确说明缺口和对应风险区域。

## 新手安全层

当用户明确说自己是新手、不懂 iOS、不熟 Objective-C/UIKit，或要求“从零写页面/搭架构/写基础功能”，以及用户经验水平不清晰时，默认进入新手安全模式，并读取 `references/beginner-uikit-architecture.md`。

新手安全模式的默认立场：

- 采用 MVC + MVVM-lite，小分层表达职责：ViewController 管生命周期和 UI 绑定，Service 管请求和取消，Model 管类型收敛，Cell 只做幂等渲染。
- 默认不使用全局 runtime crash guard、method swizzling、manual KVO、heavy associated object 或 `@try/@catch` 吞异常。
- 默认生成带 nullability、lightweight generics、正确 ARC 属性、可取消网络任务、主线程 UI 更新、稳定 cell reuse identifier 和输入校验的代码。
- 用户主动要求高级兜底时，先说明它是非默认历史包袱止血方案；只有用户接受风险，才进入 `references/runtime-crash-guard.md`。

## 任务路由决策树

先按用户任务选择最少 reference：

1. 如果用户是新手、经验不明确、从零写 OC + UIKit 页面/列表/网络功能，或让你搭基础架构，先读 `references/beginner-uikit-architecture.md`。
2. 如果任务是泛泛“审查这个 OC 文件/项目”，先读 `references/performance-diagnostics.md`，必要时运行 `scripts/scan_objc_risks.py`，再按命中类别读取具体 reference。
3. 如果涉及属性、delegate、block、timer、observer 或页面不释放，读 `references/memory-ownership.md`；涉及内存上涨、缓存或图片内存，再读 `references/memory-leaks-performance.md`。
4. 如果涉及 completion、URLSession、GCD、NSOperation、取消或 UI 回调，读 `references/errors-async-threading.md`；涉及共享状态、死锁或乱序覆盖，再读 `references/concurrency-safety.md`。
5. 如果涉及 REST、分页、缓存、弱网重试、重复请求或网络 owner，读 `references/networking-caching.md`。
6. 如果涉及 CF/CoreGraphics/CoreText/Security 对象释放，读 `references/corefoundation-bridging.md`。
7. 如果涉及崩溃治理、crash log、崩溃率、线上止血、集合 nil/越界、列表更新崩溃或崩溃分类，先读 `references/crash-prevention.md`，再按分类读取内存、线程、runtime、UIKit 或 CoreFoundation reference。
8. 如果涉及 KVC/KVO、category、associated object、swizzling 或动态 selector，读 `references/runtime-kvo-categories.md`；涉及崩溃边界，再读 `references/crash-prevention.md`。
9. 如果用户明确要求运行时崩溃兜底、防崩溃分类、完全消息转发、集合/KVO swizzling 止血，读 `references/runtime-crash-guard.md`。这是非默认方案，只用于历史包袱兜底。
10. 如果涉及 Swift 混编、bridging header、生成的 `-Swift.h` 或 Swift 导入质量，读 `references/swift-interop.md`。
11. 如果涉及 UIKit 生命周期、delegate/data source、cell 复用或旧页面维护，读 `references/legacy-uikit.md`。
12. 如果涉及滚动掉帧、cell 复用、异步图片、高度缓存或 prefetch，读 `references/scrolling-performance.md`；涉及 Auto Layout/Masonry 动态布局，再读 `references/layout-performance.md`。
13. 如果涉及圆角、阴影、mask、透明混合或 rasterize，读 `references/uikit-rendering-performance.md`。
14. 如果涉及启动、首屏、`+load`、SDK 初始化或启动热路径，读 `references/startup-performance.md`。

## 引用资料路由

只读取当前任务需要的 reference：

- `references/memory-ownership.md`：属性修饰符、delegate 所有权、retain cycle、weak/strong dance、timer、notification、associated object 循环引用。
- `references/beginner-uikit-architecture.md`：新手安全层、OC + UIKit 保守架构、默认禁用项、ViewController/Service/Model/Cell 职责、可复制模板使用。
- `references/errors-async-threading.md`：`NSError **`、completion handler、URLSession/GCD/NSOperation 约定、主线程 UI 更新。
- `references/corefoundation-bridging.md`：`CFBridgingRetain`、`CFBridgingRelease`、`__bridge`、`__bridge_transfer`、Create/Copy/Get 所有权规则。
- `references/runtime-kvo-categories.md`：KVC/KVO 崩溃边界、manual KVO、context 指针、category、associated object、method swizzling。
- `references/runtime-crash-guard.md`：运行时兜底、防崩溃分类、完全消息转发、集合/KVO swizzling 止血和不可 runtime 兜底边界。非默认方案，只用于历史包袱兜底。
- `references/swift-interop.md`：bridging header、module、生成的 `-Swift.h`、影响 Swift 导入的 nullability/generics、`NS_SWIFT_NAME`、`NS_REFINED_FOR_SWIFT`。
- `references/legacy-uikit.md`：view controller 生命周期、table/collection cell 复用、Auto Layout、delegate/data source 维护。
- `references/uikit-rendering-performance.md`：UIKit 渲染性能、离屏渲染、圆角、阴影、mask、透明混合、`shouldRasterize`、列表滚动视觉效果优化。
- `references/scrolling-performance.md`：UITableView/UICollectionView 滚动性能、cell 复用、复用标识符、预估行高、异步图片、图片预解码、约束复用、高度缓存、prefetch、列表刷新卡顿。
- `references/layout-performance.md`：Auto Layout 性能、约束创建/更新、动态高度、Masonry `remakeConstraints`、frame 混用、约束冲突。
- `references/startup-performance.md`：启动性能、`+load` / `+initialize`、`AppDelegate` / `SceneDelegate`、首屏、SDK 初始化、启动热路径瘦身。
- `references/memory-leaks-performance.md`：内存上涨、页面不释放、图片内存、缓存、`autoreleasepool`、timer/display link/observer 生命周期。
- `references/crash-prevention.md`：崩溃治理分层、分类矩阵、治理闭环、集合 nil/越界、类型校验、列表批量更新一致性、KVC/KVO 崩溃、动态 selector、全局防崩溃分类风险。
- `references/concurrency-safety.md`：GCD、NSOperation、共享 mutable state、死锁、竞态、取消语义、异步结果时序、completion 队列契约。
- `references/networking-caching.md`：NSURLSession、请求取消、重复请求合并、缓存 key、弱网重试、分页刷新、网络回调 UI 安全。
- `references/performance-diagnostics.md`：Instruments、Core Animation、Leaks、Zombies、Main Thread Checker、静态风险巡检和性能优化记录。

## 标准输出格式

进行审查或修复建议时，优先使用下面结构，按任务复杂度裁剪：

- **结论**：一句话说明主要风险、根因假设或修改方向。
- **证据**：列出代码位置、调用路径、生命周期边界、线程队列或工具数据。没有实测数据时，明确标为“代码线索/待验证假设”。
- **问题**：按严重度和影响排序，说明为什么会造成崩溃、卡顿、泄漏或维护风险。
- **建议改法**：给出最小可行修改；涉及 API 契约、Swift 导入、runtime 或线程时说明兼容性影响。
- **验证方式**：说明应运行的测试、构建、Instruments、Memory Graph、Core Animation、脚本扫描或手工复现路径。
- **剩余风险**：列出无法验证、依赖业务语义或需要用户确认的地方。

如果用户要求直接改代码，完成后汇报修改文件、行为变化和已运行验证。不要把 `scripts/scan_objc_risks.py` 的命中结果直接当作确定缺陷；它只是 review 线索。

## 可用代码模板

- `assets/snippets/UIView+OCMPerformance.h`
- `assets/snippets/UIView+OCMPerformance.m`
- `assets/snippets/OCMWeakProxy.h`
- `assets/snippets/OCMWeakProxy.m`
- `assets/snippets/OCMCrashSafety.h`
- `assets/snippets/OCMCrashSafety.m`
- `assets/templates/beginner-uikit/OCMItem.h`
- `assets/templates/beginner-uikit/OCMItem.m`
- `assets/templates/beginner-uikit/OCMItemService.h`
- `assets/templates/beginner-uikit/OCMItemService.m`
- `assets/templates/beginner-uikit/OCMItemListViewModel.h`
- `assets/templates/beginner-uikit/OCMItemListViewModel.m`
- `assets/templates/beginner-uikit/OCMItemCell.h`
- `assets/templates/beginner-uikit/OCMItemCell.m`
- `assets/templates/beginner-uikit/OCMItemListViewController.h`
- `assets/templates/beginner-uikit/OCMItemListViewController.m`

当用户明确需要 UIView 渲染性能工具分类时，参考或复制这两个文件。复制到业务项目后，建议把 `OCM` 方法前缀替换为项目自己的前缀，避免 category 方法名冲突。不要把模板当作全局自动优化工具；它只提供显式调用的圆角、阴影、`shadowPath`、透明背景和 rasterize 辅助方法。

当用户需要处理 `NSTimer` / `CADisplayLink` 持有 target 导致页面不释放时，参考或复制 `OCMWeakProxy` 模板。weak proxy 只能打断 target 循环引用，仍要在生命周期边界调用 `invalidate`。

当用户需要处理集合 nil/越界、外部 JSON 类型收敛或后台回调更新 UI 时，参考或复制 `OCMCrashSafety` 模板。它只提供显式调用的 helper，不改变 Foundation/UIKit 全局行为；调用点仍要处理空数据和降级状态。

当用户是新手或从零写 OC + UIKit 列表/网络页面时，优先参考 `assets/templates/beginner-uikit/`。这些模板展示保守分层、nullability/generics、可取消网络、主线程 completion、稳定 reuse identifier、generation token 和外部数据类型收敛。复制后要替换 `OCM` 前缀，并贴合项目既有网络层和图片加载库。

## 可用脚本

- `scripts/scan_objc_risks.py`
- `scripts/test_scan_objc_risks.py`

当用户需要先盘点 Objective-C 项目的性能、崩溃和运行时风险时，可以运行该脚本。脚本输出是人工 review 线索，不是确定缺陷；不要机械替换所有命中项。

```bash
python3 scripts/scan_objc_risks.py /path/to/YourProject
python3 scripts/scan_objc_risks.py /path/to/YourProject --category rendering
python3 scripts/scan_objc_risks.py /path/to/YourProject --min-level warning
python3 scripts/scan_objc_risks.py /path/to/YourProject --format json --max-findings 50
python3 scripts/scan_objc_risks.py /path/to/YourProject --fail-on-finding
```

维护扫描脚本后，运行 `python3 scripts/test_scan_objc_risks.py` 验证多行匹配、JSON 输出和 CI 失败开关。

## 核心规则

### 属性所有权

- 对被当前对象拥有的 Objective-C 对象使用 `strong`。
- 对 `NSString`、`NSAttributedString`、`NSArray`、`NSDictionary`、`NSSet`、`NSData`、`NSIndexSet` 以及其他具有值语义的对象使用 `copy`，因为调用方可能传入 mutable 子类。
- block 属性必须使用 `copy`。栈上的 block 一旦需要逃逸出当前作用域，就必须被复制。
- delegate、data source、父对象/反向引用、由其他对象图拥有的对象使用 `weak`。标量和 C struct 使用 `assign`。
- 除非为了明确的旧系统兼容，不要对 Objective-C 对象引用使用 `assign`；如果必须使用，写清楚生命周期假设。
- 默认使用 `nonatomic`，除非既有 API 明确承诺 atomic 属性语义。`atomic` 不等于对象状态线程安全。

### 新手默认安全规则

- 用户经验不清晰时，把用户当作需要安全护栏的新手来写代码；先给保守 MVC + MVVM-lite 结构，再根据现有项目收窄。
- 新手默认代码必须包含 nullability、lightweight generics、正确 property ownership、block `copy`、weak delegate、可取消异步任务和主线程 UI 更新。
- 新手默认不引入全局 swizzling、runtime 完全转发、manual KVO、复杂 associated object 或吞异常兜底。
- 新手默认把外部数据在 model/service 层收敛，不让 `NSNull`、错误类型、越界 index 或 nil 插入集合进入 UI 层。
- 新手默认列表代码必须注册 cell、使用稳定 reuse identifier、幂等配置、`prepareForReuse` 重置、异步结果检查稳定 model identifier。

### 循环引用

- 任何被持有的 block 都可能强捕获 `self`：block 属性、被对象保留的动画 block、operation 持有的 completion block、timer、display link、block 形式的 notification observer。
- 对可能晚于当前调用栈执行的异步回调，使用 weak/strong dance：

```objc
__weak typeof(self) weakSelf = self;
[self.service loadWithCompletion:^(id result, NSError *error) {
    __strong typeof(weakSelf) self = weakSelf;
    if (!self) {
        return;
    }
    [self handleResult:result error:error];
}];
```

- 保存并正确失效 repeating timer、display link、KVO observation 和 block observer token。弱捕获不能替代生命周期清理。
- 不要盲目弱捕获。当任务语义要求 owner 存活时，优先使用显式取消或由 operation 对象表达所有权。

### 可空性（Nullability）与轻量泛型

- 现代头文件使用 `NS_ASSUME_NONNULL_BEGIN` / `NS_ASSUME_NONNULL_END` 包裹，再把真实可空的位置标为 `nullable`。
- 为集合内容标注 lightweight generics：`NSArray<NSString *> *`、`NSDictionary<NSString *, NSNumber *> *`、`NSSet<MyModel *> *`。
- initializer、factory、fluent API 返回接收者类型时使用 `instancetype`。
- delegate 属性和参数要精确标注：`id<MyDelegate>`，再按实际情况加 `nullable` 或 `weak`。
- 对 `NSError **`，在显式 nullability 的头文件中优先写成 `NSError * _Nullable * _Nullable error`。

### 错误、回调与线程

- 遵循 Cocoa 同步错误风格：返回 `BOOL` 或 nullable object；只在失败时写入 `*error`，写入前必须检查 `error != NULL`。
- 使用稳定的 error domain、code 和有用的 `userInfo` key。不要一边返回部分成功值一边设置 error。
- 异步 API 使用一个 completion callback，并确保只调用一次。推荐形状为 `(ResultType _Nullable result, NSError *_Nullable error)`，并文档化或强制回调队列。
- UIKit 必须在主线程访问。URLSession 和很多后台回调默认不在主线程。

### CoreFoundation 桥接

- 用 Create/Copy/Get 命名规则判断所有权。
- 不转移所有权时使用 `__bridge`。
- 把已持有的 CF 对象交给 ARC 管理时使用 `__bridge_transfer` 或 `CFBridgingRelease`。
- 把 Objective-C 对象传给会接管所有权的 CF API 时使用 `__bridge_retained` 或 `CFBridgingRetain`。
- 同一个所有权声明不要既 bridge transfer 又手动 `CFRelease`。

### 运行时（Runtime）、KVC、KVO 与分类（Category）

- KVC 对未定义 key 会抛异常，也可能根据访问路径绕过 setter。除非序列化、绑定或动态表单必须使用 KVC，否则优先使用类型化访问。
- KVO 注册必须平衡。使用唯一的 static context 指针，并只在 `observeValueForKeyPath:ofObject:change:context:` 中处理自己的 context。
- manual KVO 修改值时，用匹配的 `willChangeValueForKey:` 和 `didChangeValueForKey:` 包裹。
- category 方法要加项目前缀，降低命名冲突。category 不能添加 ivar；associated object 需要稳定 static key 和正确 association policy。
- method swizzling 只作为最后手段。确实需要时，保留方法签名，用 `dispatch_once`，调用原实现，并记录受影响 selector。

### Swift 混编

- 不要在公开 `.h` 文件里 import 生成的 `ProductModuleName-Swift.h`。在头文件中使用 forward declaration，在 `.m` 文件里按需 import 生成的 Swift 头。
- app target 用 bridging header 把 Objective-C 暴露给 Swift。framework 使用 module map 或 umbrella header。
- 用 nullability、lightweight generics、`NS_SWIFT_NAME`、`NS_REFINED_FOR_SWIFT` 改善 Swift 导入质量。
- 除非同步更新所有 Objective-C 调用方，不要只为了 Swift 调用点更好看而修改 Objective-C selector 片段。

### 旧 UIKit 代码维护

- 一次性 setup 放在 `viewDidLoad`；每次显示前需要刷新的内容放在 `viewWillAppear:`；依赖最终 frame 的布局放在 `viewDidLayoutSubviews`；cleanup/cancellation 放在与既有所有权匹配的生命周期方法中。
- 可复用 cell 的配置必须是幂等的。在 `prepareForReuse` 中重置临时状态并取消过期异步任务。
- 不要在 layout pass 中反复添加约束。代码创建约束前先设置 `translatesAutoresizingMaskIntoConstraints = NO`。
- delegate 和 data source 保持 weak。调用 optional delegate 方法前检查 `respondsToSelector:`。

### UIKit 渲染性能

- 优先优化热路径上的渲染问题，例如滚动 cell、频繁动画 view 和首屏大量重复卡片，不要机械消灭所有离屏渲染。
- 圆角和阴影通常分层处理：外层 view 负责 shadow 并设置 `shadowPath`，内层 view 负责 `cornerRadius` 和必要的裁剪。
- 阴影没有 `shadowPath` 时要重点审查，尤其是在 table/collection cell 中。
- `mask`、`masksToBounds`、透明混合和 `shouldRasterize` 都需要结合场景验证；不要把 UIView 分类写成自动修改所有 view 行为的万能工具。

### 滚动性能

- 先定位主线程、图片、布局、复用和数据刷新瓶颈，不要只凭感觉修改列表代码。
- cell 配置必须幂等：`prepareForReuse` 取消旧任务并重置状态，异步回调必须检查稳定 model identifier。
- 图片应按展示尺寸异步加载、后台解码、可取消、可缓存；不要在 cell 中同步读图或解码大图。
- 约束应创建一次并复用，动态变化优先改 `constant` 或 `active`；动态高度缓存要包含宽度、内容版本和字体环境。
- prefetch 只能做可取消的预热工作，不要在 prefetch completion 中直接更新 UI。

### 启动、内存与崩溃

- 崩溃治理先分类再修复：数据边界、UIKit 状态一致性、生命周期、线程与异步、KVC/KVO/runtime、所有权桥接、底层 C/CF/C++ 和 OOM 要分开判断。
- 每个高优先级崩溃都要有证据闭环：符号化栈、输入样本或状态路径、根因、最小修复、验证方式和残留风险。
- 启动路径只保留首屏必须同步完成的工作；`+load` / `+initialize` 不做业务初始化、IO、数据库或大型 SDK 启动。
- 内存问题先区分泄漏、峰值过高和缓存膨胀；用 Memory Graph / Allocations 验证，不要只靠猜。
- 页面不释放优先检查 block、timer、display link、observer、KVO、delegate 和 associated object 的强引用链。
- 服务端、缓存和配置输入进入 model 层前做类型收敛；集合构造过滤 nil，数组访问检查边界。
- 不推荐用全局 swizzling 的“防崩溃分类”吞异常；优先修复调用边界和状态一致性。
- 运行时崩溃兜底是非默认方案，只用于历史包袱线上止血；unknown selector、集合越界/nil、KVO 不平衡、野指针、C/C++ 崩溃必须分开判断。

### 并发与诊断

- `atomic` 不等于线程安全；共享 mutable collection 必须通过串行队列、锁或同一 concurrent queue + barrier 保护。
- 避免主线程 `dispatch_sync(dispatch_get_main_queue(), ...)`；后台结果更新 UI 前切回主队列。
- 多个异步请求可能乱序返回时，用 generation token 或稳定 model identifier 防止旧结果覆盖新状态。
- 取消语义要覆盖网络、解析、回调和 UI 更新；weak self 不能替代取消。
- 性能优化先测量后修改；用 Time Profiler、Core Animation、Allocations、Leaks 或埋点验证结果。

### 网络、缓存与布局

- 请求 owner 要明确，页面退出或条件变化时取消；首屏不等待非必要网络完成。
- 同一资源短时间多处请求时，考虑合并 in-flight request；缓存 key 包含用户、参数、尺寸、版本和语言等上下文。
- 重试必须有上限、退避和幂等性判断；支付、下单、状态变更不要客户端盲目重放。
- Auto Layout 固定约束只创建一次；状态变化优先改 constraint `constant` / `active`。
- Masonry 旧代码初始化用 `makeConstraints`，状态变化用 `updateConstraints`，避免在滚动热路径高频 `remakeConstraints`。

## 常见错误

- block 属性或看似不可变的值对象属性使用 `strong` 而不是 `copy`。
- `self` 持有 block 属性，block 又强捕获 `self`。
- 网络或后台 completion 直接更新 UI，没有切回主线程。
- 在公开 Objective-C 头文件中 import `Module-Swift.h`，导致循环 import。
- 添加 KVO 后没有覆盖所有 teardown 路径。
- 在 `+load` 中 swizzling，却没有 `dispatch_once`、签名检查或原实现调用。
- category 方法命名过于通用，例如 `-jsonString`，与其他库冲突。
- cell 复用时没有清理 image、task、selected state、hidden state 或绑定旧 model 的 delegate 回调。
- 同一个 layer 同时做圆角裁剪和阴影，或设置阴影却没有 `shadowPath`。
- 在滚动 cell 中反复创建 mask/path，或对动态内容盲目开启 `shouldRasterize`。
- 在 `cellForRow`、`configure`、`layoutSubviews` 中同步加载图片、解码图片、重复创建约束或计算复杂高度。
- reuse identifier 与 register/dequeue 不一致，或把 model identifier 当作 cell 复用标识符。
- 异步图片回调只检查 indexPath，没有检查稳定 model identifier，导致复用错图。
- 自适应高度列表开启了估算，但 estimatedRowHeight 明显偏离真实值，导致滚动跳动。
- 使用 prefetch 但没有实现取消，快速滑动时制造更多无用请求。
- 在启动阶段同步初始化非首屏 SDK、扫描大量类或资源、读取大文件。
- timer/display link 依赖 weak capture，但没有 invalidate，页面仍然不释放。
- 用 `NSMutableDictionary` 做无上限图片/高度/富文本缓存，导致内存持续上涨。
- 服务端 `id` 类型没有校验就当字符串、数组或字典使用，触发 `unrecognized selector`。
- table/collection 批量更新前后数据源数量不一致，导致列表更新崩溃。
- 把 `atomic` 当线程安全方案，或多个 completion 同时读写 mutable collection。
- 主线程调用 `dispatch_sync(dispatch_get_main_queue(), ...)`，在特定路径死锁。
- 性能优化没有测量依据，一次修改过多导致无法判断收益来源。
- 同一图片、配置或列表数据重复请求，没有 in-flight 合并或缓存命中。
- 缓存 key 缺少用户、语言、尺寸、scale、版本等上下文，导致串数据或错图。
- 弱网失败后无限重试，或对非幂等请求盲目重放。
- 在 `layoutSubviews`、`cellForRow`、`configureWithModel:` 中重复创建或 remake 约束。
- Auto Layout 和手动 frame 同时管理同一个 view，导致布局抖动或约束冲突。
- 把 runtime 完全转发、集合 swizzling 或 KVO swizzling 当成默认防崩溃方案，掩盖真实数据和生命周期问题。
- 在用户经验不清晰时，直接给高阶 runtime/KVO/swizzling 方案，没有先提供新手安全层默认方案。
- 新页面从第一版就把网络、解析、缓存、跳转、复杂状态和 UI 细节全部塞进一个 ViewController。

## 审查清单

- 头文件：nullability、generics、`instancetype`、selector 兼容性、Swift 导入影响。
- 内存：属性修饰符、delegate 所有权、被持有的 block、timer、observer、associated object。
- 错误：`NSError **` 只在失败时写入，domain/code 稳定，completion 只调用一次。
- 线程：UI 在主线程，回调队列已文档化或强制，取消路径安全。
- Bridge：Create/Copy/Get 所有权明确，被转移的 CF 对象只有一个 owner 释放。
- Runtime：KVC key 安全，KVO add/remove 平衡，category 有前缀，swizzling 被约束在小范围。
- Runtime 兜底：是否明确这是非默认历史包袱止血方案，是否有白名单、日志、灰度、远端开关和回滚？
- UIKit：生命周期位置正确，cell 复用重置完整，约束没有重复添加，optional delegate 调用前检查。
- 渲染：圆角/阴影是否分层，阴影是否有 `shadowPath`，mask/path 是否只在 bounds 变化时更新，透明混合和 rasterize 是否经过验证。
- 滚动：reuse identifier 是否稳定一致，预估行高是否与高度策略匹配，图片加载是否可取消和预解码，约束是否复用，高度缓存是否有正确 key，prefetch 是否支持取消，列表刷新是否避免滚动中全量 `reloadData`。
- 启动：`+load` / `+initialize`、`didFinishLaunching`、首屏生命周期里是否有非必要同步重活？
- 内存：页面是否释放，缓存是否有上限，图片是否按展示尺寸处理，批处理是否控制 autorelease 峰值？
- 崩溃：是否先完成分类、证据、根因、修复、验证和残留风险闭环？集合 nil/越界、外部数据类型、批量更新一致性、动态 selector 签名是否安全？
- 并发：共享状态是否受保护，异步结果是否防乱序覆盖，取消是否贯穿完整链路？
- 网络：请求 owner、取消、去重、缓存 key、重试和分页状态是否清晰？
- 布局：约束是否创建一次并复用，动态高度是否稳定，Masonry 是否避免高频 remake？
- 诊断：是否用合适工具验证瓶颈和优化效果，静态巡检结果是否经过人工复核？
- 新手安全层：是否识别新手/经验不明场景，并默认避开 runtime/swizzling/manual KVO？
- 新手架构：是否有 Model、Service、ViewController、Cell 的清晰职责，异步取消和主线程 UI 契约是否明确？
