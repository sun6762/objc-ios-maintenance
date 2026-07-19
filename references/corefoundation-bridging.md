# CoreFoundation 桥接

当任务涉及 CoreFoundation、Security.framework、旧 AddressBook API、CG 对象、toll-free bridging 或 ARC bridge cast 时读取本文件。

## 所有权规则

先看函数名：

- 名称包含 `Create` 或 `Copy` 的函数通常返回已拥有对象。必须 release，或把所有权转给 ARC。
- 名称包含 `Get` 的函数通常返回未拥有对象。除非文档特别说明，否则不要 release。

## 桥接转换（Bridge Cast）

不转移所有权：

```objc
CFStringRef cfName = (__bridge CFStringRef)name;
NSString *name = (__bridge NSString *)cfName;
```

把 CF 所有权转给 ARC：

```objc
CFStringRef copied = CFURLCopyHostName(url);
NSString *host = CFBridgingRelease(copied);
```

等价写法：

```objc
NSString *host = (__bridge_transfer NSString *)CFURLCopyHostName(url);
```

把 Objective-C 对象转给假设接管所有权的 CF API：

```objc
CFTypeRef retained = CFBridgingRetain(object);
CFArrayAppendValue(array, retained);
CFRelease(retained);
```

等价写法：

```objc
CFTypeRef retained = (__bridge_retained CFTypeRef)object;
```

## 常见失败

- 泄漏：调用 `Create`/`Copy` 函数后只用 `__bridge`。
- 崩溃：用了 `__bridge_transfer` 后又手动 `CFRelease`。
- 悬垂指针：Objective-C owner 已释放后继续使用 bridged CF pointer。
- 回调所有权错误：在 C callback 中存放 Objective-C 对象，却没有按 callback 契约 retain/release。

## Security.framework 模式

很多 Security API 会通过 output parameter 返回 retained CF 值：

```objc
CFTypeRef result = NULL;
OSStatus status = SecItemCopyMatching((__bridge CFDictionaryRef)query, &result);
if (status == errSecSuccess) {
    NSData *data = CFBridgingRelease(result);
    return data;
}
if (result != NULL) {
    CFRelease(result);
}
```

只有当函数确实产出了 `result` 时，才 release 或 bridge-transfer 它。每个 output parameter 的所有权都要以具体 API 文档为准。

## Toll-free 桥接

toll-free bridging 让部分 Objective-C 类型与 CF 类型可以互通，但不会抹掉所有权规则。`NSArray`/`CFArrayRef`、`NSDictionary`/`CFDictionaryRef`、`NSString`/`CFStringRef`、`NSData`/`CFDataRef` 仍然需要正确的 bridge 语义。
