# 构建系统、依赖与模块化治理

当任务涉及 Xcode 工程、`project.pbxproj`、target/scheme/build setting、`.xcconfig`、CocoaPods、SPM、静态库、闭源 `.a`、`xcframework`、`-ObjC`、`-force_load`、category 符号裁剪、头文件依赖、PCH、umbrella header、modulemap 或编译速度时读取本文件。若线上现象是 `unrecognized selector`，同时读取 `references/crash-prevention.md` 和 `references/runtime-kvo-categories.md`。

## 快速目录

- 处理原则
- Category 符号被裁剪
- Linker Flag 使用边界
- `project.pbxproj` 与 scheme 漂移
- `.xcconfig` 分层治理
- CocoaPods、SPM 与手动二进制混用
- 闭源 `.a` 迁移到 `xcframework`
- 头文件依赖、PCH 与模块化
- 编译速度治理
- 静态巡检
- 审查清单

## 处理原则

构建系统问题要先收敛证据，再改最小范围：

- 先确认失败发生在编译、链接、运行时加载、启动后 selector 调用、Archive 还是 CI 环境。
- 先对比 App target、extension target、Debug/Release、Archive 和 CI 的 build settings，不要只看当前 Xcode UI。
- 修改 linker flag、header search path、modulemap 或 Podfile 时，同时验证真机、模拟器、Archive 和受影响 extension。
- 不要用 `-all_load`、递归 header search path 或全局 PCH import 作为长期兜底。
- 每次治理保留可回滚边界：一个依赖、一个 target 或一组 build setting，不要一次升级所有 Pod、迁移所有二进制并重排所有 xcconfig。

常用盘点命令：

```bash
xcodebuild -list -workspace App.xcworkspace
xcodebuild -showBuildSettings -workspace App.xcworkspace -scheme App -configuration Release
xcodebuild -workspace App.xcworkspace -scheme App -configuration Debug -showBuildTimingSummary build
plutil -lint App.xcodeproj/project.pbxproj
python3 scripts/scan_objc_risks.py /path/to/YourProject --category build
```

## Category 符号被裁剪

典型现象：

- 线上或 Release 包出现 `unrecognized selector sent to instance`，selector 来自某个 category。
- Debug 能复现概率低，Archive、CI 或特定 App/Extension target 才出问题。
- 静态库、Pod、闭源 `.a` 或历史手动 SDK 最近调整过链接方式。

根因通常是静态库只按已引用符号加载 object file。Objective-C category 没有自己的类符号，只有方法表元数据；如果 category 所在 object file 没被链接器加载，运行时就看不到这些方法。

排查顺序：

1. 从 crash log 确认 receiver class、selector、版本、构建方式和 target。
2. 搜索 selector 定义，确认它是否在 category 中，以及 category 属于源码、Pod、静态库还是闭源二进制。
3. 检查最终链接产物的 App/Extension target，而不是只检查 Pod target：

```bash
xcodebuild -showBuildSettings -workspace App.xcworkspace -scheme App -configuration Release | rg "OTHER_LDFLAGS|DEAD_CODE_STRIPPING"
```

4. 检查 `OTHER_LDFLAGS` 是否保留 `$(inherited)`，否则 CocoaPods 或上层 xcconfig 注入的 flag 可能被覆盖。
5. 对闭源库或静态库，确认 category 方法符号是否在 archive 内：

```bash
xcrun nm -m Vendor/libLegacy.a | rg "CategoryName|selectorName|_OBJC_"
```

修复优先级：

- 首选：在最终 App/Extension target 的 `OTHER_LDFLAGS` 中保留 `$(inherited)` 并加入 `-ObjC`，只作用于需要加载 Objective-C category 的最终链接目标。
- 次选：对确实只有 category、且 `-ObjC` 仍无法加载的特定静态库使用精确 `-force_load /path/to/libLegacy.a`。
- 避免：全局 `-all_load`。它会加载所有静态库 object file，常引入重复符号、体积膨胀和不可控副作用。
- 长期：让 SDK 提供者交付 `xcframework`、modulemap、headers、dSYM 和资源 bundle；或者把 category 改为显式 helper / wrapper，降低运行时依赖。

验证：

- Release 真机包和 Archive 都要跑。
- 对每个 App extension 单独检查 build settings；extension 不继承主 App 的最终链接参数。
- 用最小调用路径触发 category selector，确认不再崩溃。
- 记录为何使用 `-ObjC` 或 `-force_load`，避免后续清理时被误删。

## Linker Flag 使用边界

`OTHER_LDFLAGS` 常见坑：

- 丢失 `$(inherited)`，导致 Pods、xcconfig 或父层配置失效。
- 同一 flag 分散在 project、target、configuration、xcconfig 和 Podfile post_install 多处，合并时容易漂移。
- Debug 有 `-ObjC`，Release 没有；App 有，extension 没有。
- `-force_load` 写成相对路径，CI 或 DerivedData 路径变化后失效。
- `-all_load` 掩盖了真实缺失依赖，之后升级 SDK 时触发重复符号。

推荐治理：

- 把公共 linker flag 下沉到共享 xcconfig。
- 每个 target 只保留与自身有关的差异。
- 所有可继承 build setting 都保留 `$(inherited)`。
- `-force_load` 只绑定一个明确库文件，并在旁边注释来源和 selector crash 证据。

## `project.pbxproj` 与 scheme 漂移

`project.pbxproj` 是文本 plist，冲突解决容易造成不可见漂移。处理合并冲突时：

- 先保存冲突双方涉及的 target、build phase、file reference、build setting 和 scheme 变化。
- 不要只删除 conflict marker 后提交；必须跑 `plutil -lint` 和 `xcodebuild -list`。
- 对关键 target 跑 `xcodebuild -showBuildSettings`，比较 Debug/Release、App/Extension、CI scheme。
- 确认 scheme 是否 shared，是否遗漏 Test、Archive、Run 的 configuration。
- 检查 Build Phases 里脚本顺序、input/output files 和“Based on dependency analysis”。

可用检查：

```bash
plutil -lint App.xcodeproj/project.pbxproj
xcodebuild -list -project App.xcodeproj
xcodebuild -showBuildSettings -project App.xcodeproj -target App -configuration Debug
xcodebuild -showBuildSettings -project App.xcodeproj -target App -configuration Release
```

多人协作时，优先把经常变化的 build settings 移入 `.xcconfig`，减少 `project.pbxproj` 冲突面。

## `.xcconfig` 分层治理

推荐分层：

```text
Config/
├── Base.xcconfig
├── Pods.generated.xcconfig
├── Debug.xcconfig
├── Release.xcconfig
├── App.xcconfig
└── Extension.xcconfig
```

原则：

- `Base.xcconfig` 放所有 target 共享且稳定的设置。
- Debug/Release 放优化级别、日志开关、宏和签名差异。
- App/Extension 放 bundle id、entitlement、linker flag 等 target 差异。
- CocoaPods 生成的 xcconfig 用 `#include` 或 Xcode base configuration 接入，不要手抄。
- 对 `OTHER_LDFLAGS`、`HEADER_SEARCH_PATHS`、`FRAMEWORK_SEARCH_PATHS`、`LIBRARY_SEARCH_PATHS`、`GCC_PREPROCESSOR_DEFINITIONS` 保留 `$(inherited)`。

避免：

- 在 Xcode UI、xcconfig 和 Podfile post_install 里重复设置同一项。
- 在 Debug/Release 里写不一致的 category linker flag。
- 递归 header search path 覆盖整个仓库。

## CocoaPods、SPM 与手动二进制混用

老项目常同时存在 CocoaPods、SPM、手动 `.a/.framework` 和源码拖入。治理时先盘点依赖来源：

- `Podfile` / `Podfile.lock`：Pod 名称、版本、source、是否 `use_frameworks!`、是否 `use_modular_headers!`、CocoaPods 版本。
- `Package.swift` / `Package.resolved`：SPM 依赖和精确 revision。
- Xcode Build Phases：手动链接的 `.a`、`.framework`、`.xcframework` 和资源 bundle。
- Build Settings：search paths、linker flags、module 开关、excluded architectures。

CocoaPods 老版本锁死：

- 用 Bundler 或团队脚本固定 CocoaPods 版本，保证本地和 CI 一致。
- 升级时先跑 `pod install` 生成最小 diff；不要顺手 `pod update` 全量升级。
- 检查老版本 CocoaPods 对静态 framework、xcframework、SPM 混用和 Xcode 新版本的支持边界。

与 SPM 混用：

- 确认是否重复引入同一底层库，例如 OpenSSL、protobuf、sqlite、日志或图片库。
- 检查重复资源 bundle、module 名冲突和最低系统版本。
- App target、extension target、unit test target 的依赖集合要分别验证。
- 如需长期共存，记录每个依赖的唯一 owner：Pod、SPM 还是手动二进制。

## 闭源 `.a` 迁移到 `xcframework`

迁移目标不是“把文件包起来”，而是交付可验证的二进制接口：

- 每个平台/架构 slice 明确：iOS device、iOS simulator、必要时 Mac Catalyst。
- Headers 完整且只暴露 public API。
- 提供 modulemap 或 umbrella header，支持 `@import` / Swift import。
- dSYM、BCSymbolMaps 和资源 bundle 随版本归档。
- license、隐私清单、最低系统版本和 bitcode 历史设置有记录。

创建示例：

```bash
xcodebuild -create-xcframework \
  -library build/iphoneos/libLegacy.a -headers Headers \
  -library build/iphonesimulator/libLegacy.a -headers Headers \
  -output LegacySDK.xcframework
```

验证：

- 真机和模拟器分别编译。
- Archive 成功，且符号归档能匹配 UUID。
- Objective-C 调用、Swift import、资源加载和 category selector 都有 smoke test。
- 移除旧 `.a` 和 search path 后仍能编译，避免新旧二进制同时链接。

## 头文件依赖、PCH 与模块化

头文件依赖爆炸的症状：

- 改一个业务头导致大量文件重编。
- `Prefix.pch` 引入业务层、SDK 总头或频繁变化的 header。
- `HEADER_SEARCH_PATHS` 使用 `/**` 或 recursive。
- 公开 `.h` 中 import 过多，甚至 import 生成的 `Product-Swift.h`。
- framework 的 umbrella header 暴露 private headers。

治理顺序：

1. 公开 `.h` 中优先 forward declare；只在 `.m/.mm` import 具体依赖。
2. PCH 只保留稳定系统头和极少量基础宏，移除业务头和大型 SDK。
3. 删除递归 header search path，改为明确路径或 module import。
4. framework/pod 使用清晰的 public/private/project header 分类。
5. modulemap 只导出稳定 public header；private header 不进入 umbrella。

modulemap 示例：

```text
framework module LegacySDK {
  umbrella header "LegacySDK.h"
  export *
  module * { export * }
}
```

检查 umbrella header：

- 是否只 import public headers。
- 是否存在循环 import。
- 是否泄漏内部模型、配置或第三方 SDK 头。
- Swift 导入后 API 是否有 nullability 和 lightweight generics。

## 编译速度治理

先建立基线：

```bash
xcodebuild -workspace App.xcworkspace -scheme App -configuration Debug -showBuildTimingSummary build
xcodebuild -workspace App.xcworkspace -scheme App -configuration Debug clean build
```

排查重点：

- 哪些 target 或 Swift/ObjC/C++ 编译单元耗时最高。
- 改一个常用头会触发多少重编。
- Script Phase 是否缺少 input/output files，导致每次都跑。
- 是否把生成代码、资源处理、lint、格式化或上传符号放进每次本地 Debug build。
- Header Search Paths 是否递归且过宽。
- PCH 是否包含高频变化头。
- Pod 是否被配置成大量 dynamic framework，增加链接和启动成本。

治理建议：

- 给耗时脚本补 input/output files，或只在 Release/CI/Archive 跑。
- 缩窄公共头暴露，减少 `.h` import 链。
- 拆掉过重 PCH，改为模块或局部 import。
- Debug 使用合适的增量构建设置；不要让本地 Debug 总是 Archive 级别工作。
- 对 Pods/SPM 依赖升级和链接方式调整做小步验证，不要一次性迁移所有依赖。
- 记录优化前后耗时、机器、Xcode、模拟器/真机、configuration 和 DerivedData 状态。

## 静态巡检

本 skill 的扫描脚本可辅助发现构建配置线索：

```bash
python3 scripts/scan_objc_risks.py /path/to/YourProject --category build
python3 scripts/scan_objc_risks.py /path/to/YourProject --category build --min-level warning
python3 scripts/scan_objc_risks.py /path/to/YourProject --category build --format json --max-findings 100
```

脚本会扫描 Objective-C 源码和常见配置文件，包括 `.pbxproj`、`.xcconfig`、`.xcscheme`、`.podspec`、`.modulemap`、`.pch`、`Podfile`、`Podfile.lock`、`Package.swift` 和 `Package.resolved`。

静态命中只是线索：

- category 命中不等于一定会被裁剪；要看它是否在静态库/Pod/闭源 `.a` 内，以及最终 target linker flag。
- `-ObjC` 命中不等于正确；要看是否配置在最终链接目标，是否 Debug/Release 一致。
- `use_frameworks!`、SPM、xcframework 命中不等于问题；要结合重复依赖、资源和 module 验证。

## 审查清单

- 线上 selector crash 是否确认来自 category，且 category 位于静态库/Pod/闭源二进制？
- 最终 App/Extension target 的 Release/Archive `OTHER_LDFLAGS` 是否包含 `$(inherited)` 和必要的 `-ObjC`？
- 是否避免了全局 `-all_load`，只在确有证据时对单个库使用 `-force_load`？
- `project.pbxproj` 是否无 conflict marker，且通过 `plutil -lint`、`xcodebuild -list` 和关键 target build settings 对比？
- scheme 是否 shared，Run/Test/Profile/Archive configuration 是否符合预期？
- `.xcconfig` 是否分层清楚，避免 Xcode UI、Podfile 和 xcconfig 多处重复设置？
- CocoaPods 版本是否由 Bundler/CI 固定，升级是否最小化 diff？
- CocoaPods、SPM 和手动二进制是否存在重复依赖、重复资源、module 名冲突或最低系统版本冲突？
- 闭源 `.a` 迁移到 `xcframework` 时，headers、modulemap、dSYM、BCSymbolMaps、资源和 license 是否齐全？
- PCH 是否只包含稳定公共头，公开 `.h` 是否减少 import 并使用 forward declaration？
- Header Search Paths 是否去掉递归和过宽路径？
- modulemap/umbrella header 是否只暴露 public API，不泄漏 private header？
- 编译速度是否先建立基线，再分别治理头文件、PCH、script phase、依赖链接方式和缓存？
