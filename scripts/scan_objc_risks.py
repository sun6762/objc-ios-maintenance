#!/usr/bin/env python3
"""扫描 Objective-C iOS 项目中的高风险写法。

输出结果只是 review 线索，不代表确定缺陷。命中后应结合调用上下文人工判断。
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
from typing import Iterable


SCANNABLE_EXTENSIONS = {
    ".h",
    ".m",
    ".mm",
    ".pbxproj",
    ".xcconfig",
    ".xcscheme",
    ".podspec",
    ".modulemap",
    ".pch",
}
SCANNABLE_FILE_NAMES = {
    "Podfile",
    "Podfile.lock",
    "Package.swift",
    "Package.resolved",
}
DEFAULT_EXCLUDED_DIRS = {
    ".git",
    "Pods",
    "Carthage",
    "DerivedData",
    "build",
    ".build",
    "node_modules",
}

LEVEL_ORDER = {"info": 0, "warning": 1, "error": 2}


@dataclass(frozen=True)
class Rule:
    category: str
    level: str
    pattern: re.Pattern[str]
    message: str
    window: int = 1
    file_pattern: re.Pattern[str] | None = None


RULES = [
    Rule("build", "error", re.compile(r"^(?:<<<<<<<|=======|>>>>>>>)"), "项目或配置文件仍有合并冲突标记，会导致 Xcode/CocoaPods/SPM 配置解析失败。"),
    Rule("build", "warning", re.compile(r"@implementation\s+[A-Za-z_]\w*\s*\([^)]+\)"), "这是 Objective-C category。若它位于静态库、Pod 或闭源 .a 中，确认最终 App target 的 OTHER_LDFLAGS 包含 -ObjC；个别纯 category 静态库可能需要精确 -force_load。", window=2),
    Rule("build", "warning", re.compile(r"OTHER_LDFLAGS\s*=\s*(?!.*\$\((?:inherited|INHERITED)\))"), "OTHER_LDFLAGS 缺少 $(inherited) 时容易覆盖 CocoaPods/xcconfig 注入的 -ObjC、framework 或 library 标记。"),
    Rule("build", "info", re.compile(r"OTHER_LDFLAGS\s*=.*-ObjC"), "发现 -ObjC；确认只在需要加载 Objective-C category 的 App/Extension 最终链接 target 上设置，并避免多处漂移。"),
    Rule("build", "warning", re.compile(r"OTHER_LDFLAGS\s*=.*-all_load"), "-all_load 会加载所有静态库对象文件，容易引入重复符号和体积膨胀；优先使用 -ObjC 或对特定库 -force_load。"),
    Rule("build", "info", re.compile(r"OTHER_LDFLAGS\s*=.*-force_load"), "-force_load 应精确绑定到确实需要完整加载的静态库路径，并记录原因，避免变成全局兜底。"),
    Rule("build", "warning", re.compile(r"\bvendored_libraries\b.*\.a\b"), "Podspec 仍暴露闭源 .a。迁移到 xcframework 前需确认 slice、bitcode/BCSymbolMaps、dSYM、modulemap、资源和 license。", window=3),
    Rule("build", "info", re.compile(r"\bvendored_frameworks\b.*\.xcframework\b"), "发现 xcframework；确认每个 slice、Headers/Modules、dSYM/BCSymbolMaps 和资源 bundle 都随发布产物归档。", window=3),
    Rule("build", "info", re.compile(r"^\s*use_frameworks!"), "CocoaPods use_frameworks! 会影响静态/动态链接、Swift module、资源 bundle 和启动成本；与 SPM 混用时要统一 linkage 策略。"),
    Rule("build", "info", re.compile(r"\buse_modular_headers!|:modular_headers\s*=>\s*true"), "modular headers 会改变头文件可见性和 include 方式；迁移时检查 umbrella header、modulemap 和私有头泄漏。"),
    Rule("build", "info", re.compile(r"^\s*COCOAPODS:\s*[0-9]+(?:\.[0-9]+)*"), "Podfile.lock 锁定 CocoaPods 版本；团队应统一安装方式，并评估老版本与 Xcode、SPM、静态链接策略的兼容性。"),
    Rule("build", "info", re.compile(r"\.package\s*\("), "发现 Swift Package 依赖；与 CocoaPods/手动二进制混用时确认重复符号、资源 bundle、最低系统版本和构建缓存策略。", window=2),
    Rule("build", "warning", re.compile(r"(?:HEADER_SEARCH_PATHS|FRAMEWORK_SEARCH_PATHS|LIBRARY_SEARCH_PATHS)\s*=\s*(?!.*\$\((?:inherited|INHERITED)\))"), "搜索路径配置缺少 $(inherited) 容易覆盖 Pods、SPM 或上层 xcconfig 的路径。"),
    Rule("build", "warning", re.compile(r"HEADER_SEARCH_PATHS\s*=.*(?:/\*\*|\brecursive\b)"), "递归 Header Search Paths 会扩大头文件依赖图，增加误 include、模块冲突和编译时间。"),
    Rule("build", "warning", re.compile(r"ALWAYS_SEARCH_USER_PATHS\s*=\s*YES"), "ALWAYS_SEARCH_USER_PATHS=YES 是旧工程常见遗留项，可能让头文件解析顺序不可控。"),
    Rule("build", "info", re.compile(r"GCC_PREFIX_HEADER\s*="), "发现 PCH 配置；PCH 只应放稳定系统/基础头，不要放业务头、重型 SDK 或频繁变化的 header。"),
    Rule("build", "warning", re.compile(r"#\s*import\s+[\"<].+[\">]"), "PCH 中的 import 会放大编译依赖；确认只包含稳定、低变化频率的公共头。", file_pattern=re.compile(r"\.pch$")),
    Rule("build", "info", re.compile(r"CLANG_ENABLE_MODULES\s*=\s*NO"), "关闭 Clang modules 会影响模块化和 Swift/ObjC 混编体验；迁移 umbrella header/modulemap 时需重新评估。"),
    Rule("build", "info", re.compile(r"DEFINES_MODULE\s*=\s*YES"), "发现可导入 module；确认 public/umbrella header 只暴露稳定 API，不泄漏私有头。"),
    Rule("build", "info", re.compile(r"(?:PRODUCT_BUNDLE_IDENTIFIER|DEVELOPMENT_TEAM|PROVISIONING_PROFILE_SPECIFIER|CODE_SIGN_STYLE)\s*="), "签名或 bundle 配置可能在多 target/configuration 间漂移；合并冲突后要用 xcodebuild -showBuildSettings 对比。"),
    Rule("threading", "error", re.compile(r"dispatch_sync\s*\(\s*dispatch_get_main_queue\s*\("), "主线程调用时会死锁，UI 更新通常改为 dispatch_async 或重新设计同步依赖。"),
    Rule("threading", "warning", re.compile(r"completionHandler\s*:\s*\^.*\b(?:tableView|collectionView|navigationController|label|imageView|view)\b"), "URLSession completion 默认不在主线程，直接访问 UIKit 前需要切回主队列。", window=8),
    Rule("threading", "warning", re.compile(r"performSelector\s*:"), "动态 selector 需要确认 respondsToSelector 和方法签名，优先使用协议或类型化调用。", window=3),
    Rule("threading", "warning", re.compile(r"objc_msgSend"), "objc_msgSend 必须使用与真实方法完全匹配的函数指针签名。"),
    Rule("async", "warning", re.compile(r"dataWithContentsOfURL\s*:"), "疑似同步网络/文件读取，避免在主线程或滚动热路径调用。"),
    Rule("async", "warning", re.compile(r"stringWithContentsOfURL\s*:"), "疑似同步读取 URL 内容，避免阻塞主线程。"),
    Rule("async", "warning", re.compile(r"sendSynchronousRequest\s*:"), "同步网络请求会阻塞线程，启动和 UI 路径应替换为异步请求。"),
    Rule("network", "info", re.compile(r"(?:data|download|upload)TaskWith(?:URL|Request)\s*:"), "确认请求 owner、取消路径、回调队列和旧结果丢弃逻辑。", window=3),
    Rule("network", "info", re.compile(r"backgroundSessionConfigurationWithIdentifier\s*:"), "后台 URLSession 适合文件上传/下载，确认 delegate、文件型 upload 和 force-quit 边界。", window=3),
    Rule("network", "warning", re.compile(r"NSURLConnection"), "NSURLConnection 是旧网络 API，维护时确认同步请求、取消、回调队列和迁移边界。"),
    Rule("network", "info", re.compile(r"\[NSURLSession\s+sharedSession\]"), "生产网络层若需要超时、缓存、delegate 或连通性策略，应考虑注入配置好的 NSURLSession。"),
    Rule("network", "info", re.compile(r"\bresume\s*\]"), "确认 NSURLSessionTask 不会重复 resume，且页面退出或条件变化时可取消。"),
    Rule("memory", "warning", re.compile(r"@property\s*\([^)]*\bassign\b[^)]*\)[^;]*\*"), "Objective-C 对象属性使用 assign 可能造成悬垂指针，确认是否应为 weak/strong/copy。", window=3),
    Rule("memory", "warning", re.compile(r"__unsafe_unretained"), "__unsafe_unretained 不会置 nil，容易形成悬垂引用，需确认生命周期绝对受控。"),
    Rule("memory", "warning", re.compile(r"@property\s*\([^)]*\b(?:strong|retain)\b[^)]*\)\s*[^;]*\(\s*\^"), "block 属性必须使用 copy，strong/retain 不能表达 block 从栈复制到堆的语义。", window=3),
    Rule("memory", "warning", re.compile(r"@property\s*\([^)]*\b(?:strong|retain)\b[^)]*\)\s*[^;]*(?:delegate|dataSource)\b", re.IGNORECASE), "delegate/dataSource 通常应为 weak，strong/retain 容易形成循环引用。", window=3),
    Rule("memory", "warning", re.compile(r"scheduledTimerWithTimeInterval\s*:"), "NSTimer 会持有 target，确认 invalidate 路径或 weak proxy。"),
    Rule("memory", "warning", re.compile(r"displayLinkWithTarget\s*:"), "CADisplayLink 会持有 target，确认 invalidate 路径或 weak proxy。"),
    Rule("memory", "warning", re.compile(r"addObserverForName\s*:"), "block observer 会返回 token，确认保存并移除 token。", window=3),
    Rule("runtime", "warning", re.compile(r"addObserver\s*:.*forKeyPath\s*:"), "KVO 需要唯一 context，并确认所有 teardown 路径 remove 平衡。", window=5),
    Rule("runtime", "warning", re.compile(r"addObserver\s*:.*forKeyPath\s*:.*context\s*:\s*NULL"), "KVO 使用 NULL context 难以区分来源，建议使用唯一 static context。", window=6),
    Rule("runtime", "warning", re.compile(r"removeObserver\s*:.*forKeyPath\s*:"), "KVO remove 前确认 observation 已添加且只移除一次。", window=5),
    Rule("runtime", "info", re.compile(r"observeValueForKeyPath\s*:"), "KVO 回调需要先判断 context，只处理自己的 observation，其他事件交给 super。", window=6),
    Rule("runtime", "warning", re.compile(r"\bvalueForKey(?:Path)?\s*:"), "KVC key 若来自动态输入可能抛异常，优先白名单或类型化访问。", window=3),
    Rule("runtime", "warning", re.compile(r"\bsetValue\s*:.*forKey(?:Path)?\s*:"), "KVC setValue 需处理 nil、标量和未知 key 边界。", window=5),
    Rule("runtime", "warning", re.compile(r"\bsetValuesForKeysWithDictionary\s*:"), "批量 KVC 赋值需要先做 key 白名单和 NSNull/类型收敛，避免 undefined key 或标量 nil 崩溃。", window=3),
    Rule("runtime", "warning", re.compile(r"method_exchangeImplementations\s*\("), "swizzling 会改变全局行为，确认 dispatch_once、签名兼容和原实现调用。"),
    Rule("rendering", "warning", re.compile(r"masksToBounds\s*=\s*YES"), "masksToBounds 可能触发裁剪/离屏问题；若同层还有阴影应拆分内外层。"),
    Rule("rendering", "warning", re.compile(r"shouldRasterize\s*=\s*YES"), "rasterize 只适合复杂但静态内容，确认 rasterizationScale 和缓存失效成本。"),
    Rule("rendering", "info", re.compile(r"shadowOpacity\s*="), "设置阴影时检查是否有稳定 shadowPath，尤其是列表 cell。"),
    Rule("layout", "warning", re.compile(r"(?:mas_)?remakeConstraints\s*:"), "remakeConstraints 会移除并重建约束，避免在滚动热路径高频调用。", window=3),
    Rule("layout", "info", re.compile(r"activateConstraints\s*:"), "确认固定约束只创建一次，不在 configure/layoutSubviews 中重复创建。"),
    Rule("layout", "info", re.compile(r"layoutSubviews"), "确认 layoutSubviews 中没有重复添加约束、同步 IO 或复杂计算。"),
    Rule("layout", "info", re.compile(r"layoutIfNeeded\s*\]"), "确认 layoutIfNeeded 不在循环或滚动热路径中高频触发。"),
    Rule("scrolling", "warning", re.compile(r"\breloadData\s*\]"), "reloadData 命中滚动热路径时可能卡顿；确认是否可改为局部刷新或 diff。"),
    Rule("scrolling", "info", re.compile(r"dequeueReusableCellWithIdentifier\s*:"), "确认 reuse identifier 稳定、已 register，且 cell 配置幂等。", window=3),
    Rule("scrolling", "info", re.compile(r"estimatedRowHeight\s*="), "确认 estimatedRowHeight 与高度策略匹配，偏差过大会导致滚动条跳动和布局修正。"),
    Rule("scrolling", "info", re.compile(r"prefetch(?:Rows|Items)AtIndexPaths\s*:"), "prefetch 必须只做可取消的预热工作，避免 completion 直接更新 UI。", window=3),
    Rule("crash", "warning", re.compile(r"\b(?:arrayWithObjects|dictionaryWithObjectsAndKeys)\s*:"), "可变参数集合构造遇到 nil 会截断或异常，传入可空值前先过滤或提供降级值。", window=3),
    Rule("crash", "info", re.compile(r"\b(?:addObject|insertObject)\s*:"), "向数组插入外部数据前确认非 nil；若上一行已校验可忽略。"),
    Rule("crash", "warning", re.compile(r"\bsetObject\s*:.*?\bforKey\s*:"), "向字典写入 nil key/value 会崩溃，外部数据入库前需要显式校验。"),
    Rule("crash", "warning", re.compile(r"\b(?:self\.)?[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)?\s*\[\s*(?:index|idx|row|section|i|indexPath\.(?:row|section|item)|\w+Index)\s*\]"), "数组下标访问需要边界保护，尤其是异步更新或服务端数据变化后。"),
    Rule("crash", "warning", re.compile(r"\bobjectAtIndexedSubscript\s*:"), "数组下标访问需要边界保护，尤其是异步更新或服务端数据变化后。"),
    Rule("crash", "warning", re.compile(r"objectAtIndex\s*:"), "数组访问需要边界检查，尤其是服务端数据或异步更新后。"),
    Rule("crash", "warning", re.compile(r"objectForKey\s*:"), "字典值来自外部数据时需要类型校验，避免后续 unrecognized selector。"),
    Rule("crash", "warning", re.compile(r"performBatchUpdates\s*:"), "列表批量更新前后数据源数量必须和 insert/delete/reload 操作一致。", window=3),
    Rule("crash", "warning", re.compile(r"\b(?:insert|delete|reload)(?:Rows|Items)AtIndexPaths\s*:|\bmove(?:Row|Item)AtIndexPath\s*:|\b(?:insert|delete|reload)Sections\s*:"), "列表局部更新必须保证数据源先完成对应变更，且 indexPath/section 与更新前后数量一致。", window=3),
    Rule("crash", "info", re.compile(r"beginUpdates|endUpdates"), "UITableView begin/end updates 需要先更新数据源，并保证 indexPath 与数量变化一致。"),
    Rule("crash", "info", re.compile(r"@catch\s*\("), "不要用 @try/@catch 作为常规防崩溃方案；捕获异常后继续运行可能隐藏状态损坏。", window=3),
]


@dataclass(frozen=True)
class Finding:
    path: Path
    line_number: int
    end_line_number: int
    rule: Rule
    text: str


def is_scannable_file(path: Path) -> bool:
    return path.suffix in SCANNABLE_EXTENSIONS or path.name in SCANNABLE_FILE_NAMES


def iter_scannable_files(root: Path, include_tests: bool) -> Iterable[Path]:
    if root.is_file():
        if is_scannable_file(root):
            yield root
        return

    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if not is_scannable_file(path):
            continue
        parts = set(path.parts)
        if parts & DEFAULT_EXCLUDED_DIRS:
            continue
        if not include_tests and any(part.lower().endswith("tests") or part.lower().endswith("uitests") for part in path.parts):
            continue
        yield path


def strip_block_comments(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    in_block_comment = False
    for line in lines:
        result = []
        index = 0
        string_delimiter: str | None = None
        escaped = False
        while index < len(line):
            if in_block_comment:
                end = line.find("*/", index)
                if end == -1:
                    index = len(line)
                    continue
                in_block_comment = False
                index = end + 2
                continue

            char = line[index]
            if string_delimiter:
                result.append(char)
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == string_delimiter:
                    string_delimiter = None
                index += 1
                continue

            if char in {'"', "'"}:
                string_delimiter = char
                result.append(char)
                index += 1
                continue

            if line.startswith("//", index):
                index = len(line)
                continue
            if line.startswith("/*", index):
                in_block_comment = True
                index += 2
                continue

            result.append(char)
            index += 1
        cleaned.append("".join(result))
    return cleaned


def normalized_window(lines: list[str], start_index: int, window: int) -> tuple[str, int]:
    selected = lines[start_index:start_index + window]
    non_empty = [line.strip() for line in selected if line.strip()]
    text = " ".join(non_empty)
    text = re.sub(r"\s+", " ", text)
    end_line = start_index + max(len(selected), 1)
    return text, end_line


def scan_file(path: Path, rules: list[Rule], min_level: str) -> Iterable[Finding]:
    min_order = LEVEL_ORDER[min_level]
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:
        print(f"无法读取 {path}: {exc}", file=sys.stderr)
        return

    lines = strip_block_comments(raw_lines)
    emitted: set[tuple[int, str, str]] = set()

    for line_number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped:
            continue
        for rule in rules:
            if LEVEL_ORDER[rule.level] < min_order:
                continue
            if rule.file_pattern and not rule.file_pattern.search(path.name):
                continue
            search_text, end_line = normalized_window(lines, line_number - 1, rule.window)
            if not search_text:
                continue
            key = (line_number, rule.category, rule.message)
            if key in emitted:
                continue
            if rule.pattern.search(search_text):
                emitted.add(key)
                yield Finding(path, line_number, end_line, rule, stripped)


def select_rules(category: str | None) -> list[Rule]:
    if category is None:
        return RULES
    return [rule for rule in RULES if rule.category == category]


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="扫描 Objective-C iOS 项目中的性能、崩溃、运行时和构建配置风险模式。")
    parser.add_argument("path", type=Path, help="要扫描的项目目录或单个源码/配置文件")
    parser.add_argument("--category", choices=sorted({rule.category for rule in RULES}), help="只扫描指定分类")
    parser.add_argument("--min-level", choices=sorted(LEVEL_ORDER, key=LEVEL_ORDER.get), default="info", help="最低输出级别")
    parser.add_argument("--format", choices=("text", "json"), default="text", help="输出格式")
    parser.add_argument("--max-findings", type=int, default=0, help="最多输出多少条；0 表示不限制")
    parser.add_argument("--include-tests", action="store_true", help="包含 Tests / UITests 目录")
    parser.add_argument("--fail-on-finding", action="store_true", help="发现风险提示时返回非 0 状态码，适合接入 CI")
    return parser.parse_args(argv)


def finding_to_dict(root: Path, finding: Finding) -> dict[str, object]:
    relative = finding.path.relative_to(root) if root.is_dir() else Path(finding.path.name)
    return {
        "path": str(relative),
        "line": finding.line_number,
        "end_line": finding.end_line_number,
        "category": finding.rule.category,
        "level": finding.rule.level,
        "message": finding.rule.message,
        "text": finding.text,
    }


def print_findings(root: Path, findings: list[Finding], output_format: str) -> None:
    if output_format == "json":
        payload = {
            "count": len(findings),
            "findings": [finding_to_dict(root, finding) for finding in findings],
            "note": "这些结果是人工 review 线索，不代表确定缺陷。",
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    for finding in findings:
        relative = finding.path.relative_to(root) if root.is_dir() else finding.path.name
        line_range = f"{finding.line_number}" if finding.end_line_number == finding.line_number else f"{finding.line_number}-{finding.end_line_number}"
        print(f"[{finding.rule.level}] {finding.rule.category} {relative}:{line_range}")
        print(f"  {finding.rule.message}")
        print(f"  {finding.text}")

    print()
    print(f"共发现 {len(findings)} 条风险提示。请结合上下文人工复核，不要机械替换。")


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    root = args.path.expanduser().resolve()
    if not root.exists():
        print(f"路径不存在: {root}", file=sys.stderr)
        return 2

    rules = select_rules(args.category)
    findings: list[Finding] = []
    for scannable_file in iter_scannable_files(root, include_tests=args.include_tests):
        findings.extend(scan_file(scannable_file, rules, args.min_level))
        if args.max_findings > 0 and len(findings) >= args.max_findings:
            findings = findings[:args.max_findings]
            break

    if not findings:
        if args.format == "json":
            print(json.dumps({"count": 0, "findings": [], "note": "未发现匹配的风险模式。"}, ensure_ascii=False, indent=2))
        else:
            print("未发现匹配的风险模式。")
        return 0

    print_findings(root, findings, args.format)
    return 1 if args.fail_on_finding else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
