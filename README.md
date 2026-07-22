# Objective-C iOS Maintenance Agent Skill

一个面向 Objective-C + UIKit 项目的 Agent Skill，可用于 Codex 和 Claude Code，帮助维护、审查、重构、调试和编写更安全的 OC iOS 代码。

它重点关注旧项目里最容易出问题的地方：ARC 所有权、循环引用、KVO/KVC、Swift 混编、UIKit 性能、列表滚动、渲染卡顿、网络异步、内存泄漏、野指针诊断、崩溃日志符号化、dSYM/MetricKit、OOM/Jetsam/watchdog、pre-main 启动拆解和崩溃边界。

## 适合场景

- 维护老 Objective-C iOS 项目。
- 审查 `.h`、`.m`、`.mm` 中的内存、线程、崩溃和性能风险。
- 优化 UIKit 页面、列表、cell 复用、Auto Layout、渲染和启动性能。
- 处理 retain cycle、block capture、timer、observer、delegate、KVO/KVC 等常见坑。
- 改善 Objective-C 与 Swift 混编边界。
- 给新手生成更保守、更不容易出错的 OC + UIKit 基础架构。

## 核心能力

- **内存与所有权**：`strong` / `weak` / `copy` / `assign`、block 必须 `copy`、weak delegate、weak/strong dance。
- **崩溃治理**：崩溃分类、证据闭环、崩溃日志符号化、dSYM/UUID 管理、MetricKit 接入、集合 nil/越界、KVC/KVO 崩溃、动态 selector、列表批量更新一致性、野指针诊断、OOM/Jetsam/FOOM/watchdog、运行时兜底边界。
- **UIKit 性能**：离屏渲染、圆角、阴影、mask、透明混合、`shouldRasterize`、cell 复用、滚动掉帧、pre-main/`+load`/动态库启动拆解。
- **异步与线程**：`NSError **`、completion handler、GCD、NSOperation、NSURLSession、主线程 UI 更新。
- **Swift 混编**：bridging header、module、生成的 `-Swift.h`、nullability、generics、`NS_SWIFT_NAME`、`NS_REFINED_FOR_SWIFT`。
- **诊断辅助**：提供 Objective-C 风险巡检脚本，帮助快速发现需要人工 review 的代码线索。
- **新手安全层**：当用户经验不明确或从零写功能时，默认采用保守 MVC + MVVM-lite 分层，避免 runtime/swizzling/manual KVO 等高风险方案。

## 安装与使用

这个仓库以 `SKILL.md` 作为统一入口，Codex 和 Claude Code 都可以读取。`agents/openai.yaml` 只用于 Codex/OpenAI UI 展示；Claude Code 会使用 `SKILL.md`、`references/`、`scripts/` 和 `assets/`。

### Codex

将仓库克隆到 Codex skills 目录：

```bash
mkdir -p "${CODEX_HOME:-$HOME/.codex}/skills"
git clone https://github.com/sun6762/objc-ios-maintenance.git "${CODEX_HOME:-$HOME/.codex}/skills/objc-ios-maintenance"
```

在 Codex 中可通过 `$objc-ios-maintenance` 明确调用，也可以让 Codex 根据任务自动选择：

```text
使用 $objc-ios-maintenance 审查这个 Objective-C 页面退出后不释放的问题。
```

```text
使用 $objc-ios-maintenance 帮我优化这个 UITableView 滚动掉帧问题。
```

```text
使用 $objc-ios-maintenance 从零写一个安全的 Objective-C + UIKit 列表页。
```

### Claude Code

作为个人 skill 安装到 Claude Code：

```bash
mkdir -p ~/.claude/skills
git clone https://github.com/sun6762/objc-ios-maintenance.git ~/.claude/skills/objc-ios-maintenance
```

也可以作为某个项目的 project skill 安装。若希望团队共享，推荐用 git submodule 提交到业务项目：

```bash
mkdir -p .claude/skills
git submodule add https://github.com/sun6762/objc-ios-maintenance.git .claude/skills/objc-ios-maintenance
```

在 Claude Code 中可通过 `/objc-ios-maintenance` 明确调用，也可以直接描述任务让 Claude 自动选择：

```text
/objc-ios-maintenance 审查这个 Objective-C 页面退出后不释放的问题。
```

```text
/objc-ios-maintenance 帮我优化这个 UITableView 滚动掉帧问题。
```

```text
/objc-ios-maintenance 从零写一个安全的 Objective-C + UIKit 列表页。
```

### 使用建议

- 如果是审查、修复或重构旧 OC 项目，直接描述代码位置和问题现象。
- 如果是从零写 OC + UIKit 功能，说明页面类型、数据来源、是否已有 Masonry/SDWebImage 等项目依赖。
- 如果要求 runtime 防崩溃兜底，需要同时提供崩溃日志、启用范围、灰度/回滚要求；该 Skill 默认不会把 runtime/swizzling 当作首选方案。
- Claude Code skills 官方说明见 [Extend Claude with skills](https://docs.anthropic.com/en/docs/claude-code/skills)。

## 目录结构

```text
objc-ios-maintenance/
├── SKILL.md
├── agents/
│   └── openai.yaml        # Codex/OpenAI UI 元数据；Claude Code 可忽略
├── scripts/
│   ├── scan_objc_risks.py
│   └── test_scan_objc_risks.py
├── references/
│   ├── beginner-uikit-architecture.md
│   ├── memory-ownership.md
│   ├── scrolling-performance.md
│   ├── uikit-rendering-performance.md
│   ├── crash-symbolication-metrickit.md
│   ├── dangling-pointer-diagnostics.md
│   ├── oom-watchdog-diagnostics.md
│   ├── runtime-crash-guard.md
│   └── ...
├── assets/
│   ├── snippets/
│   └── templates/
└── evals/
    └── evals.json
```

## 可用脚本

`scripts/scan_objc_risks.py` 可以对 Objective-C 项目做启发式风险扫描：

```bash
python3 scripts/scan_objc_risks.py /path/to/YourProject
python3 scripts/scan_objc_risks.py /path/to/YourProject --category rendering
python3 scripts/scan_objc_risks.py /path/to/YourProject --min-level warning
python3 scripts/scan_objc_risks.py /path/to/YourProject --format json --max-findings 50
```

注意：脚本输出是 review 线索，不是确定缺陷。每条命中都需要结合调用路径、生命周期、线程和业务语义人工判断。

## 内置模板

- `assets/snippets/UIView+OCMPerformance.*`：显式调用的 UIView 渲染性能辅助分类。
- `assets/snippets/OCMWeakProxy.*`：用于 timer / display link target 循环引用场景。
- `assets/snippets/OCMCrashSafety.*`：用于集合边界、JSON 类型收敛和主线程 UI 回调的显式 helper。
- `assets/templates/beginner-uikit/`：新手安全层的 Objective-C + UIKit 列表页模板，包含 Model、Service、ViewModel、Cell、ViewController。

复制模板到业务项目后，建议把 `OCM` 前缀替换为项目自己的前缀，避免 category 或类名冲突。

## 重要边界

这个 Skill 默认优先修真实问题，不鼓励用“全局防崩溃分类”掩盖业务缺陷。

运行时兜底、method swizzling、集合 swizzling、KVO swizzling 属于**非默认方案**，只适合历史包袱项目的线上止血。使用前应具备崩溃日志、白名单、日志限频、灰度、远端开关和回滚方案。

野指针、内存破坏、OOM、Jetsam、FOOM、watchdog、C/C++ 崩溃不能依靠 Objective-C runtime guard 可靠兜底。

## 后续计划

- 增加 Masonry 布局模板。
- 增加 SDWebImage 图片加载模板。
- 增加更多真实旧项目审查案例。
- 扩展静态扫描脚本的规则和输出格式。

## License

本项目使用 [MIT License](LICENSE)。
