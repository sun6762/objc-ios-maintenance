# 崩溃防护与边界处理

当任务涉及 Objective-C 旧代码崩溃、数组越界、字典 nil、KVC/KVO 异常、unrecognized selector、table/collection 更新崩溃、主线程 UI、野指针或“防崩溃分类”时读取本文件。

## 快速目录

- 防崩溃原则
- 集合与 nil
- 类型校验
- Table / Collection 更新一致性
- KVC / KVO
- Selector 与动态调用
- UIKit 主线程
- 不推荐全局吞异常
- 可选运行时兜底
- 审查清单

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
- 不可 runtime 兜底：野指针、C/C++ 崩溃、OOM、内存破坏。

## 审查清单

- 集合构造是否过滤 nil，数组访问是否检查边界？
- 来自服务端/缓存/配置的 `id` 是否做类型校验？
- 列表批量更新的数据源数量和 indexPath 是否一致？
- KVC key 是否可信，KVO add/remove 是否平衡？
- 动态 selector 是否检查响应和签名？
- UI 更新是否保证在主线程，且页面仍处于可更新状态？
- 是否避免用全局防崩溃 swizzling 掩盖真实问题？
