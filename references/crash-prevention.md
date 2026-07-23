# 崩溃防护与边界处理

当任务涉及 Objective-C 旧代码崩溃、数组越界、字典 nil、KVC/KVO 异常、unrecognized selector、table/collection 更新崩溃、主线程 UI、野指针或“防崩溃分类”时读取本文件。若 `unrecognized selector` 指向静态库/Pod/闭源 `.a` 中的 category 方法，继续读取 `references/build-system-dependencies.md`。若任务涉及未符号化 crash log、dSYM、UUID 不匹配、第三方 SDK 符号或 MetricKit，先读取 `references/crash-symbolication-metrickit.md`。若任务明确是 `EXC_BAD_ACCESS`、`objc_msgSend`、Zombie、ASan、Malloc Scribble 或 Guard Malloc 诊断，继续读取 `references/dangling-pointer-diagnostics.md`。若任务涉及 OOM、Jetsam、FOOM、memory warning、watchdog 或 `0x8badf00d`，读取 `references/oom-watchdog-diagnostics.md`。

## 快速目录

- 崩溃治理分层
- 崩溃分类矩阵
- 治理闭环
- 优先级建议
- 防崩溃原则
- 集合与 nil
- 类型校验
- Table / Collection 更新一致性
- KVC / KVO
- Selector 与动态调用
- UIKit 主线程
- 可复用 helper 模板
- Review 示例
- 不推荐全局吞异常
- 可选运行时兜底
- 审查清单

## 崩溃治理分层

崩溃治理不是单个“防崩溃工具”，而是一条从发现、归因、修复到验证的闭环。维护 Objective-C iOS 旧项目时，按下面顺序处理：

1. 先拿证据：符号化崩溃日志、dSYM UUID 匹配、版本、设备、系统、线程栈、最近发布差异、用户路径、MetricKit 诊断和关键业务参数。
2. 再做分类：判断崩溃属于数据边界、生命周期、线程、runtime、UIKit 状态一致性、内存所有权、底层 C/CF/C++ 或 OOM。
3. 优先修源头：在 model/service/view model/view controller 的输入、状态和生命周期边界修复，不默认吞异常。
4. 才做兜底：只有高频线上问题短期无法彻底修复时，才讨论白名单 runtime guard、灰度、日志和回滚。
5. 最后防回归：补静态扫描规则、单元测试、手工复现步骤或线上指标观察。

## 崩溃分类矩阵

| 分类 | 常见现象 | 优先修复方向 | 证据与验证 |
| --- | --- | --- | --- |
| 数据边界 | 集合插入 `nil`、数组越界、`NSNull` 当字符串使用 | model/service 层类型收敛，构造集合前过滤，访问前检查 index | crash log、服务端 payload、缓存样本、`scripts/scan_objc_risks.py --category crash` |
| UIKit 状态一致性 | table/collection batch update 崩溃、cell 复用错乱 | 数据源先变更且数量匹配；不确定 diff 时先 `reloadData`；异步回调用稳定 identifier 校验 | 复现路径、更新前后 count、indexPath、滚动状态 |
| 生命周期 | 页面退出后回调、timer/display link/observer 未释放 | 明确 owner，页面消失或 dealloc 取消任务、移除 observer、invalidate timer | Memory Graph、dealloc 日志、Leaks、Zombies |
| 线程与异步 | 后台线程更新 UI、主线程死锁、旧请求覆盖新状态 | UIKit 回主线程；避免主线程 `dispatch_sync`；generation token 防乱序 | Main Thread Checker、线程栈、请求时序日志 |
| KVC/KVO/runtime | undefined key、KVO remove 不平衡、unknown selector | key 白名单、static context、add/remove 状态记录、协议替代动态 selector | exception reason、selector/keyPath、observer 生命周期 |
| 静态库 category 链接 | Release/Archive 才出现 category selector 的 `unrecognized selector` | 最终 target 保留 `$(inherited)` 和必要 `-ObjC`，必要时精确 `-force_load` | `references/build-system-dependencies.md`、`OTHER_LDFLAGS`、`nm`、Archive smoke test |
| 所有权与桥接 | 野指针、double free、CF 对象泄漏或重复释放 | ARC 属性修饰符、避免 `assign` 对象、Create/Copy/Get bridge 审查 | `references/dangling-pointer-diagnostics.md`、Zombies、ASan、Malloc Scribble、崩溃地址 |
| 底层与资源 | C/C++ 越界、OOM、内存破坏 | 边界检查、RAII/智能指针、降低峰值内存和缓存上限 | `references/crash-symbolication-metrickit.md`、`references/oom-watchdog-diagnostics.md`、ASan/UBSan/TSan、Jetsam 日志、内存曲线 |

## 治理闭环

处理每个崩溃时，记录一条简短闭环：

- **分类**：属于哪一类崩溃，为什么。
- **证据**：符号化崩溃栈、dSYM UUID、输入样本、生命周期路径、线程、MetricKit 或工具数据。
- **根因**：哪个边界没有收敛，哪个状态不一致，或哪个所有权假设错误。
- **修复**：最小改动位置，是否影响公开 `.h`、Swift 导入、调用方或 runtime 行为。
- **验证**：测试、脚本扫描、手工复现、Instruments 或线上灰度指标。
- **残留**：是否还有无法兜底的野指针、OOM、C/C++ 或第三方 SDK 风险。

## 优先级建议

- **P0**：高频线上崩溃、启动崩溃、支付/登录/核心链路崩溃、数据损坏或不可恢复状态。
- **P1**：可复现但影响局部功能的崩溃、列表更新崩溃、页面退出后回调、明确的 KVO/KVC 边界问题。
- **P2**：静态扫描命中的潜在风险、低频兜底日志、需要结合业务语义确认的问题。

默认先修 P0/P1 的源头问题。P2 可以进入巡检和代码健康任务，不要因为低风险命中而做大范围重构。

## 防崩溃原则

优先修复输入边界和状态不一致，而不是用全局 category 或 swizzling 吞掉异常。全局吞异常会隐藏真实数据问题，并可能让 UI 进入更难排查的错误状态。

合理防护应该满足：

- 调用点能看出为什么可能失败。
- 失败后有明确降级路径。
- 记录足够上下文，便于修复数据或状态源头。
- 不改变 Foundation/UIKit 全局行为。

## 集合与 nil

Objective-C 集合不能插入 `nil`。常见崩溃：

- `@[maybeNil]`
- `@{@"key": maybeNil}`
- `[array objectAtIndex:index]` 越界。
- 遍历 mutable collection 时同时修改。

推荐在构造边界显式过滤：

```objc
NSMutableDictionary *payload = [NSMutableDictionary dictionary];
if (user.identifier.length > 0) {
    payload[@"user_id"] = user.identifier;
}
if (user.name.length > 0) {
    payload[@"name"] = user.name;
}
```

数组访问要先验证边界：

```objc
- (nullable Item *)itemAtIndex:(NSUInteger)index {
    if (index >= self.items.count) {
        return nil;
    }
    return self.items[index];
}
```

不要把 `safeObjectAtIndex:` 写成全局 category 并到处替换。更好的做法是让调用点处理“没有数据”的业务状态。

## 类型校验

服务端 JSON、缓存、push payload、KVC 字典都可能类型不稳定。进入 model 层前做类型收敛：

```objc
id rawTitle = dictionary[@"title"];
NSString *title = [rawTitle isKindOfClass:NSString.class] ? rawTitle : @"";

id rawItems = dictionary[@"items"];
NSArray *items = [rawItems isKindOfClass:NSArray.class] ? rawItems : @[];
```

不要直接信任 `id` 并调用字符串、数组或字典方法；这类崩溃常表现为 `unrecognized selector sent to instance`。

## Table / Collection 更新一致性

列表批量更新崩溃通常来自数据源和 UI 操作不一致：

- 先改数据源，再执行插入/删除/reload。
- insert/delete 的 indexPath 必须对应更新前后的数据数量关系。
- 不确定 diff 正确性时，先用 `reloadData` 保证正确，再逐步优化动画。
- 滚动中收到频繁更新时，合并到下一轮 run loop 或滚动停止后处理。

```objc
[self.tableView performBatchUpdates:^{
    [self.items removeObjectAtIndex:indexPath.row];
    [self.tableView deleteRowsAtIndexPaths:@[indexPath]
                          withRowAnimation:UITableViewRowAnimationAutomatic];
} completion:nil];
```

对 `UITableView` 老接口，`beginUpdates` / `endUpdates` 也遵循同样顺序和数量一致性。

## KVC / KVO

KVC 用异常表达错误，不适合处理不可信 key。维护 KVC 代码时：

- key 来自服务端、用户输入或配置文件时，要白名单映射。
- 标量属性不要接收 `nil`。
- 能用类型化属性就不要用 KVC。

KVO 防崩溃重点：

- add/remove 平衡，且只移除已经添加的 observation。
- 使用唯一 static context 指针。
- teardown 路径覆盖 `dealloc`、页面消失、任务取消。
- 不要在 observation callback 中造成递归更新。

## Selector 与动态调用

动态调用前必须确认对象响应 selector，并确认签名符合预期：

```objc
SEL selector = @selector(refreshWithContext:);
if ([target respondsToSelector:selector]) {
    ((void (*)(id, SEL, id))objc_msgSend)(target, selector, context);
}
```

使用 `objc_msgSend` 时，函数指针签名必须和真实方法签名一致。签名不一致可能不是立刻崩溃，而是造成栈或返回值错误。

如果只是普通调用，优先使用协议或类型化 selector，不要引入动态调用。

## UIKit 主线程

UIKit 对象只能在主线程读写。后台回调更新 UI 前统一切回主队列：

```objc
dispatch_async(dispatch_get_main_queue(), ^{
    if (!self.view.window) {
        return;
    }
    [self.tableView reloadData];
});
```

不要用 `dispatch_sync(dispatch_get_main_queue(), ...)` 包 UI 更新；如果当前已经在主线程会死锁。

## 可复用 helper 模板

如果业务项目缺少统一边界工具，可以参考或复制 `assets/snippets/OCMCrashSafety.h` 和 `assets/snippets/OCMCrashSafety.m`。复制后把 `OCM` 前缀替换为项目自己的前缀。

该模板只覆盖局部显式调用：

- `OCMDispatchAsyncOnMainQueue`：后台回调更新 UI 前回主线程。
- `OCMObjectAtIndex`：数组越界返回 nil，让调用点处理空状态。
- `OCMSetObjectIfValid`：字典写入前过滤 nil key/value 和 `NSNull`。
- `OCMStringOrEmpty` / `OCMArrayOrEmpty` / `OCMDictionaryOrEmpty`：外部 JSON、缓存和配置进入 model 层前做类型收敛。

不要把这些 helper 包成全局 category 自动替换系统行为；helper 的价值是让风险边界在调用点可见。

## Review 示例

示例一：服务端字段类型不稳定。

```objc
NSString *title = payload[@"title"];
self.titleLabel.text = title;
```

风险：`title` 可能是 `NSNull`、`NSNumber` 或缺失，后续字符串方法可能触发 `unrecognized selector`。

推荐改法：在 model 或解析层收敛类型，不让不可信 `id` 进入 UI 层。

```objc
NSString *title = OCMStringOrEmpty(payload[@"title"]);
self.titleLabel.text = title.length > 0 ? title : @"--";
```

示例二：列表异步更新后继续使用旧 indexPath。

```objc
Item *item = self.items[indexPath.row];
[self openItem:item];
```

风险：网络刷新、删除或批量更新后，`indexPath.row` 可能已经越界或指向不同 model。

推荐改法：读取前检查边界；异步回调还要校验稳定 model identifier。

```objc
Item *item = OCMObjectAtIndex(self.items, indexPath.row);
if (!item) {
    return;
}
[self openItem:item];
```

示例三：URLSession completion 直接更新 UI。

```objc
completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
    self.items = parsedItems;
    [self.tableView reloadData];
}
```

风险：URLSession completion 默认不在主线程，直接访问 UIKit 可能触发线程问题；页面退出后还可能更新无效 UI。

推荐改法：解析完成后回主线程，并检查页面仍可更新。

```objc
OCMDispatchAsyncOnMainQueue(^{
    if (!self.view.window) {
        return;
    }
    self.items = parsedItems;
    [self.tableView reloadData];
});
```

## 不推荐全局吞异常

不推荐作为 skill 模板写入：

- swizzle `NSArray` / `NSDictionary` / `NSMutableArray` 来吞越界和 nil。
- swizzle KVO add/remove 来忽略不平衡。
- swizzle `forwardInvocation:` 来吞 unknown selector。
- 捕获 `NSException` 后继续让业务流程运行。

这些方案可能降低崩溃率数字，但会增加数据损坏、状态错乱和排查成本。只有用户明确要求“兼容历史包袱并接受副作用”时，才把它们作为隔离方案讨论。

## 可选运行时兜底

如果用户明确要求 runtime 完全转发、防崩溃 category、集合 swizzling 或 KVO swizzling 作为线上止血方案，读取 `references/runtime-crash-guard.md`。

该方案是非默认方案，只用于历史包袱兜底。必须明确区分：

- 可 runtime 兜底：unknown selector。
- 可 swizzle 止血但不推荐默认启用：集合越界、字典/数组 nil。
- 可 swizzle 止血但高风险：KVO 不平衡。
- 不可 runtime 兜底：野指针、C/C++ 崩溃、OOM、内存破坏、watchdog。野指针诊断读取 `references/dangling-pointer-diagnostics.md`；OOM/Jetsam/FOOM/watchdog 诊断读取 `references/oom-watchdog-diagnostics.md`。

## 审查清单

- 集合构造是否过滤 nil，数组访问是否检查边界？
- 来自服务端/缓存/配置的 `id` 是否做类型校验？
- 列表批量更新的数据源数量和 indexPath 是否一致？
- KVC key 是否可信，KVO add/remove 是否平衡？
- 动态 selector 是否检查响应和签名？
- UI 更新是否保证在主线程，且页面仍处于可更新状态？
- 是否避免用全局防崩溃 swizzling 掩盖真实问题？
- 未符号化 crash log、dSYM/UUID 或 MetricKit 诊断是否进入 `references/crash-symbolication-metrickit.md`，而不是直接猜业务根因？
- OOM/Jetsam/FOOM/watchdog 是否进入 `references/oom-watchdog-diagnostics.md`，而不是当作普通异常处理？
