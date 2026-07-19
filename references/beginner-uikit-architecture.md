# 新手安全层：Objective-C + UIKit 项目架构

当用户要从零编写 Objective-C + UIKit 功能、请求“帮我搭架构/写页面/写列表/写网络层”，或经验水平不清晰时读取本文件。目标是给新手一个不容易崩、不容易卡、后续也能维护的保守默认方案。

## 快速目录

- 何时进入新手安全模式
- 默认架构
- 推荐目录结构
- 开发顺序
- 默认禁用清单
- ViewController 安全规则
- UITableView / UICollectionView 安全规则
- 网络与异步安全规则
- Model 与数据输入安全规则
- 性能与崩溃默认底线
- 模板使用
- 审查清单

## 何时进入新手安全模式

满足任一条件时，默认进入新手安全模式：

- 用户明确说自己是新手、不懂 iOS、不熟 Objective-C、不熟 UIKit，或要求“从零写”“帮我搭一个基础架构”。
- 用户只描述业务结果，没有给出现有项目结构、线程模型、网络层、缓存方案或团队约定。
- 任务是新增页面、列表、网络请求、表单、详情页、登录注册、设置页等常见 UIKit 功能。
- 代码中出现明显基础风险：`assign` 持有对象、block 属性未 `copy`、cell 无复用标识符、网络回调直接改 UI、数组/字典输入未校验、ViewController 过大。
- 用户要求“防崩溃兜底”“runtime 完全转发”“swizzling 统一处理”，但没有崩溃日志、灰度、回滚和副作用接受说明。

经验水平不确定时，先按新手安全模式给方案；如果项目已有成熟架构，再说明会贴合现有架构做最小改动。

## 默认架构

默认采用 MVC + MVVM-lite，不引入复杂响应式框架或运行时魔法：

- `ViewController`：只负责生命周期、绑定 view、触发请求、处理导航和轻量状态分发。
- `ViewModel` / `Presenter`：把 model 转成 UI 文案、颜色、开关状态和 cell 配置数据；不持有 UIKit view。
- `Service` / `APIClient`：负责请求、取消、解析入口和 completion 队列契约。
- `Model`：负责类型安全的数据承载和输入收敛；不要把服务端 `id` 直接传到 UI 层。
- `Cell` / `View`：只渲染传入数据；复用时重置状态；不写业务请求编排。

如果功能很小，可以省略 ViewModel，但不要让 cell 承担网络、缓存、跳转和业务判断。

## 推荐目录结构

```text
YourFeature/
├── Scenes/
│   └── ItemList/
│       ├── OCMItemListViewController.h
│       ├── OCMItemListViewController.m
│       ├── OCMItemListViewModel.h
│       └── OCMItemListViewModel.m
├── Models/
│   ├── OCMItem.h
│   └── OCMItem.m
├── Services/
│   ├── OCMItemService.h
│   └── OCMItemService.m
├── Views/
│   └── Cells/
│       ├── OCMItemCell.h
│       └── OCMItemCell.m
├── Networking/
│   └── 项目已有网络基础设施
└── Support/
    └── 常量、错误域、工具对象
```

在既有项目里优先沿用原目录命名；如果没有结构，再使用上面的最小分层。

## 开发顺序

1. 先定义 model：字段可空性、类型转换、默认值和非法输入处理。
2. 再定义 service：请求参数、返回类型、错误、取消方式和 completion 队列。
3. 再定义 view model：把业务数据转成 UI 需要的稳定值。
4. 再写 view controller：创建 UI、注册 cell、发起/取消请求、主线程刷新。
5. 再写 cell：固定 reuse identifier、幂等 configure、`prepareForReuse` 重置。
6. 最后验证：空数据、错误态、慢网、快速进出页面、快速滚动、旋转/字体变化。

## 默认禁用清单

新手默认不要使用：

- 全局 method swizzling、防崩溃 category、运行时完全消息转发。
- 手写 KVO 和 manual KVO；能用显式回调、delegate、notification token 或状态刷新就不用 KVO。
- 大量 associated object 给 category 塞状态。
- 在主线程同步网络、数据库、大文件 IO、图片解码或复杂 JSON 解析。
- cell 内直接发起不可取消网络请求，或在 cell 内决定页面跳转和核心业务逻辑。
- 在 `layoutSubviews`、`cellForRow`、`configure` 中重复创建约束。
- 巨型 ViewController：网络、解析、缓存、复杂布局、业务状态都塞在同一个 `.m`。
- 为了“安全”用 `@try/@catch` 包住业务逻辑然后忽略异常。

这些能力不是永远不能用，而是只有在现有项目证据充分、边界清楚、可灰度回滚时才作为高级方案。

## ViewController 安全规则

- `viewDidLoad` 做一次性 UI 创建、约束、cell 注册和数据绑定。
- `viewWillAppear:` 做每次出现都需要刷新的轻量逻辑。
- `viewDidDisappear:` 或 `dealloc` 中取消页面拥有的网络任务、timer、display link 和 observer。
- 所有 UI 更新回到主线程，并确认页面仍然需要这次结果。
- 使用 `weak/strong dance`，但不要把 weak self 当作取消机制。
- table/collection 的数据源数组只在主线程更新；批量更新前后数量必须一致。

## UITableView / UICollectionView 安全规则

- 使用稳定的复用标识符，统一 `registerClass:` / `registerNib:` 与 `dequeueReusableCellWithIdentifier:forIndexPath:`。
- cell 配置必须幂等，不能依赖上一次复用残留状态。
- `prepareForReuse` 重置 image、text、hidden、alpha、selected/highlighted、自定义状态，并取消旧图片任务。
- 异步回调不要只检查 `indexPath`；优先检查稳定 model identifier。
- 自适应高度使用 `UITableViewAutomaticDimension` 时，`estimatedRowHeight` 要接近真实平均高度；高度差异巨大时考虑缓存或关闭不可靠估算。
- 不在滚动热路径同步读图、解码、解析 HTML/富文本或计算复杂布局。

## 网络与异步安全规则

- service 方法返回 `NSURLSessionDataTask *` 或项目内 cancel token，让 owner 能取消。
- completion 必须只调用一次，并明确回调队列。新手默认让 service 在主线程回调，减少 UI 误用。
- 网络层返回 typed model 或错误，不把原始 JSON 直接扔给 view controller。
- 请求参数变化、搜索、分页刷新等场景使用 generation token，防止旧结果覆盖新 UI。
- 失败重试要有上限、退避和幂等判断；不要重试支付、下单等非幂等请求。

## Model 与数据输入安全规则

- 头文件默认使用 `NS_ASSUME_NONNULL_BEGIN` / `NS_ASSUME_NONNULL_END`。
- 集合使用 lightweight generics。
- 外部 JSON 进入 model 时做类型检查：字符串、数字、数组、字典分别校验。
- 字典构造时不要插入 nil；对可空字段使用条件赋值。
- 数组访问前检查边界；服务端下发 index、id、key 不可信。
- 对 UI 必需字段给出清晰 fallback，而不是让 `NSNull` 或错误类型进入 UILabel。

## 性能与崩溃默认底线

- 列表先保证复用、异步图片、可取消任务、约束复用和局部刷新，再谈复杂优化。
- 圆角阴影默认分层：外层阴影加 `shadowPath`，内层圆角裁剪。
- 只在性能数据支持时使用 `shouldRasterize`，并设置正确 `rasterizationScale`。
- 对外部输入做边界收敛，避免把崩溃留给 NSArray/NSDictionary/KVC。
- Debug 阶段让问题尽早暴露；Release 阶段也优先修真实边界，不默认吞异常。

## 模板使用

可复制这些模板作为新功能起点，并把 `OCM` 前缀替换为项目自己的三字母或业务前缀：

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

模板表达的是安全边界和职责划分，不是强制命名。放入业务项目后，按项目已有网络层、图片库和路由方式调整。

## 审查清单

- 是否识别用户经验水平；不确定时是否默认进入新手安全模式？
- 是否避免默认 runtime/swizzling/manual KVO？
- 是否有清晰目录分层，而不是所有逻辑塞进 ViewController？
- `.h` 是否有 nullability、generics、`copy` block 和 weak delegate？
- 网络请求是否可取消，completion 是否只调用一次且回到约定队列？
- UI 更新是否在主线程，异步结果是否防旧数据覆盖？
- cell 是否注册、稳定复用、幂等配置、复用时重置并取消旧任务？
- 外部 JSON 是否做类型检查，集合 nil/越界是否在业务边界处理？
- 列表性能是否覆盖图片、约束、高度、刷新和 prefetch，而不只讨论离屏渲染？
- 是否给出可运行验证路径：慢网、空数据、错误态、快速进出页面、快速滚动？
