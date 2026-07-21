# 运行时兜底、防崩溃分类与不可兜底边界

当任务明确要求使用 Objective-C runtime、消息转发、category 或 swizzling 做线上崩溃兜底时读取本文件。本文件是“可选、强警告、最后兜底”方案，不是默认修复路径。

## 快速目录

- 总原则
- 启用决策模板
- 远端配置建议
- 日志字段建议
- 灰度与回滚流程
- 可 runtime 兜底：unknown selector
- 可 swizzle 止血但不推荐默认启用：集合越界与 nil
- 可 swizzle 止血但高风险：KVO 不平衡
- 不可 runtime 兜底：野指针
- 不可 runtime 兜底：C/C++ 崩溃
- 上线保护要求
- 审查清单

## 总原则

优先修复调用边界、数据校验、生命周期和线程问题。runtime guard 只能作为历史包袱项目的线上止血层，用来降低一部分已知高频崩溃，不应让业务逻辑依赖它继续运行。

使用前必须确认：

- 已有崩溃日志或线上数据证明该类崩溃高频且短期无法彻底修复。
- 兜底范围有白名单，不能影响 Foundation/UIKit/CoreData/KVO 动态子类等系统行为。
- 每次兜底都记录 class、selector、参数摘要、调用栈、线程和业务场景。
- 有远端开关、灰度策略、限频日志和回滚方案。
- 兜底后仍要创建真实修复任务，不能把吞异常当成完成。

## 启用决策模板

只有下面问题都能回答清楚，才进入 runtime guard 设计：

| 问题 | 必须有的答案 |
| --- | --- |
| 要兜哪类崩溃？ | unknown selector、集合 nil/越界、KVO 不平衡等具体类型，不能写“全部崩溃”。 |
| 证据是什么？ | 符号化 crash log、版本分布、崩溃量级、调用栈、最近变更和复现可能性。 |
| 为什么不能直接修？ | 涉及发版周期、第三方输入、历史包袱或短期无法定位源头；同时要创建真实修复任务。 |
| 影响范围多大？ | 明确类名、方法族、业务模块、版本、用户比例和排除对象。 |
| 失败后如何降级？ | 返回 nil、跳过更新、reloadData、禁用入口或提示用户；不能让业务继续依赖损坏状态。 |
| 如何关闭？ | 远端开关、版本回滚、灰度比例降为 0，且不依赖再次发版。 |

如果任一项只能回答“暂不清楚”，不要上线 guard；先补日志、复现路径或静态扫描。

## 远端配置建议

runtime guard 至少需要这些配置维度：

```json
{
  "enabled": false,
  "sampleRate": 0.01,
  "minAppVersion": "1.2.0",
  "maxAppVersion": "1.2.9",
  "guardTypes": ["unrecognized_selector"],
  "classAllowlist": ["ACMEFeedCell", "ACMEProfileViewModel"],
  "classDenylistPrefixes": ["NS", "UI", "CA", "WK", "_"],
  "selectorAllowlist": ["refreshWithContext:", "updateWithModel:"],
  "logLimitPerSession": 20
}
```

配置默认值必须是关闭。远端配置拉取失败、解析失败或版本不匹配时，也必须关闭。

## 日志字段建议

每次兜底都记录足够反推源头的上下文，并做限频：

- guard type：unknown selector、collection nil、collection bounds、KVO remove 等。
- class、selector、keyPath、index、count、参数摘要。
- 线程、调用栈、app 版本、系统版本、设备、用户分桶、开关版本。
- 当前页面、业务场景、最近一次数据刷新或路由来源。
- 降级动作：return nil、skip update、reloadData、disable feature 等。

不要记录完整用户隐私数据、token、手机号、身份证、地址或原始请求体。需要关联业务数据时，使用脱敏 ID 或 hash。

## 灰度与回滚流程

1. Debug 和内部包保持 crash 或 assert，不吞异常。
2. Release 首次只对极小比例用户打开，并限制版本、业务模块和类白名单。
3. 同时观察崩溃率、兜底日志量、关键业务成功率、卡顿、内存和用户反馈。
4. 如果兜底日志高频、业务指标下降或出现新崩溃，立即远端关闭。
5. 每个兜底日志聚合成真实修复任务；修复发版后移除或关闭对应 guard。

## 可 runtime 兜底：unknown selector

`unrecognized selector sent to instance` 可以通过 Objective-C 消息转发链路兜底：

```text
+resolveInstanceMethod:
-forwardingTargetForSelector:
-methodSignatureForSelector:
-forwardInvocation:
-doesNotRecognizeSelector:
```

完全转发兜底通常 swizzle `methodSignatureForSelector:` 和 `forwardInvocation:`：当对象找不到 selector 时，给出一个伪造方法签名，然后在 `forwardInvocation:` 中记录日志并吞掉调用。

关键风险：

- 不知道真实返回值类型。伪造 `@@:` 或 `v@:` 可能与调用方期待的返回类型不一致。
- 浮点、结构体、C++ 对象、block 返回值等 ABI 场景可能出现未定义行为。
- 吞掉调用后，业务状态可能已经不完整，后续仍可能在别处崩溃。
- swizzle `NSObject` 影响面极大，必须只对白名单业务类生效。

示意代码只用于理解边界，不建议直接复制为生产模板：

```objc
- (NSMethodSignature *)ocm_methodSignatureForSelector:(SEL)selector {
    NSMethodSignature *signature = [self ocm_methodSignatureForSelector:selector];
    if (signature) {
        return signature;
    }
    if (![self ocm_shouldGuardUnrecognizedSelector:selector]) {
        return nil;
    }
    return [NSMethodSignature signatureWithObjCTypes:"@@:"];
}

- (void)ocm_forwardInvocation:(NSInvocation *)invocation {
    if (![self respondsToSelector:invocation.selector] &&
        [self ocm_shouldGuardUnrecognizedSelector:invocation.selector]) {
        [self ocm_recordGuardEventWithSelector:invocation.selector];
        id nilValue = nil;
        if (invocation.methodSignature.methodReturnLength > 0) {
            [invocation setReturnValue:&nilValue];
        }
        return;
    }
    [self ocm_forwardInvocation:invocation];
}
```

白名单判断至少要排除系统 bundle 和系统前缀：

```objc
- (BOOL)ocm_shouldGuardUnrecognizedSelector:(SEL)selector {
    NSBundle *bundle = [NSBundle bundleForClass:self.class];
    if (bundle != NSBundle.mainBundle) {
        return NO;
    }

    NSString *className = NSStringFromClass(self.class);
    if ([className hasPrefix:@"NS"] ||
        [className hasPrefix:@"UI"] ||
        [className hasPrefix:@"CA"] ||
        [className hasPrefix:@"WK"] ||
        [className hasPrefix:@"_"]) {
        return NO;
    }

    return YES;
}
```

## 可 swizzle 止血但不推荐默认启用：集合越界与 nil

数组越界、字典插入 nil 不是消息转发问题。常见兜底方式是 swizzle Foundation collection 的族类方法，例如：

- `NSArray`：`objectAtIndex:`、`objectAtIndexedSubscript:`
- `NSMutableArray`：`addObject:`、`insertObject:atIndex:`、`removeObjectAtIndex:`
- `NSDictionary` / `NSMutableDictionary`：`setObject:forKey:`、`objectForKey:`

风险：

- Foundation 集合是 class cluster，真实类名随系统版本和对象形态变化。
- 吞掉 nil 或越界会静默丢数据，可能把明显崩溃变成隐性业务错误。
- 下标越界通常表示数据源和 UI 状态不一致，兜底后页面可能展示错乱。
- swizzle 系统类影响全局，第三方库行为也会被改变。

更推荐默认写法：

```objc
- (nullable id)ocm_objectAtIndex:(NSUInteger)index inArray:(NSArray *)array {
    if (index >= array.count) {
        [self recordInvalidIndex:index count:array.count];
        return nil;
    }
    return array[index];
}
```

如果必须做 Foundation collection swizzling，要求：

- 只在明确版本、明确崩溃类型、明确 class cluster 覆盖范围后启用。
- 对吞掉的操作记录完整上下文。
- 不在 Debug 环境吞掉异常，Debug 应尽早暴露问题。
- 支持远端关闭。

## 可 swizzle 止血但高风险：KVO 不平衡

KVO 不平衡常见崩溃包括：

- remove 未添加的 observer。
- 重复 remove。
- observer 或 observed 对象释放时 observation 仍存在。
- callback 中没有 context 判断，处理了别人的 KVO。

正确修复优先级：

1. 使用唯一 static context。
2. 用明确状态记录是否已添加 observation。
3. 在所有 teardown 路径只移除一次。
4. 能使用 block token 或封装 observation 对象时，优先让生命周期显式化。

KVO swizzling 兜底通常用 associated object 记录 observer/keyPath/context，再拦截 add/remove。它风险很高，因为 KVO 依赖动态子类、系统私有实现和对象生命周期。

如果必须启用：

- 只保护业务类或明确的业务 observed 对象。
- 不吞掉 context 不匹配的 callback。
- 不改变 KVO 通知时机。
- Debug 环境保留 crash 或 assert。
- 上线后用日志反推真实 add/remove 不平衡位置。

## 不可 runtime 兜底：野指针

野指针、过度释放、悬垂指针和内存破坏无法通过 Objective-C runtime 可靠兜底。对象可能在消息发送前已经指向无效内存，也可能在任意 C/ObjC 内存读写时崩溃。

优先处理：

- ARC 下不要对 Objective-C 对象使用 `assign`。
- 避免 `__unsafe_unretained`。
- 检查 MRC 或 `-fno-objc-arc` 文件的 retain/release/autorelease。
- 检查 CoreFoundation bridge 是否重复 release 或漏 transfer。
- 使用 Zombie、Address Sanitizer、Malloc Scribble、Guard Malloc、Memory Graph 和符号化崩溃日志定位。

runtime guard 不能证明野指针问题被解决。

## 不可 runtime 兜底：C/C++ 崩溃

C/C++ 崩溃不走 Objective-C 消息转发，例如：

- 空指针解引用。
- C 数组或 buffer 越界。
- double free / use after free。
- 栈破坏。
- C++ exception 未捕获。
- `std::vector`、`std::string`、裸指针生命周期错误。
- signal / Mach exception 级崩溃。

处理方式：

- 边界检查、长度校验、所有权清晰化。
- C++ 使用 RAII、智能指针和明确对象生命周期。
- 打开 Address Sanitizer、Undefined Behavior Sanitizer、Thread Sanitizer。
- 符号化 crash log，结合寄存器、线程栈和崩溃地址定位。
- 对跨 C/ObjC 的 buffer、CF 对象、回调 context 做所有权审查。

不要承诺用 Objective-C category 或 runtime guard 兜住 C/C++ 崩溃。

## 上线保护要求

任何 runtime crash guard 上线前必须具备：

- 白名单：只保护明确业务类或明确方法族。
- 黑名单：排除系统类、第三方 SDK、KVO 动态子类、CoreData、WebKit 等敏感对象。
- 日志：记录崩溃类型、类名、selector、key/index、线程、调用栈、版本和开关状态。
- 限频：避免高频异常造成日志风暴或性能问题。
- 灰度：按版本、用户比例或远端配置启用。
- 回滚：远端可关闭，不依赖发版；配置失败、版本不匹配或白名单为空时默认关闭。
- 验证：Debug 不吞异常；Release 灰度后对比崩溃率、日志量和业务异常指标。

## 审查清单

- 是否先尝试修复调用边界、数据校验、生命周期和线程问题？
- 该兜底是否有真实崩溃数据支持，而不是为了“看起来更安全”？
- 是否明确区分 unknown selector、集合越界/nil、KVO 不平衡、野指针、C/C++ 崩溃？
- 是否只对白名单业务类/方法生效，并排除系统类和第三方库？
- 是否记录足够上下文，能反推真实问题源头？
- 是否有远端开关、灰度、限频和回滚？
- Debug 是否仍暴露问题，避免开发阶段被吞掉？
- 是否明确说明这是非默认方案，只用于历史包袱项目的最后兜底？
