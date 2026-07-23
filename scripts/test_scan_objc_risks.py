#!/usr/bin/env python3
"""scan_objc_risks.py 的轻量自测。

该测试只验证脚本能力边界，不代表业务项目中每个命中都是真实缺陷。
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap


SCRIPT = Path(__file__).with_name("scan_objc_risks.py")


def run_scan(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(project), *args],
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def write_fixture(project: Path) -> None:
    source = textwrap.dedent(
        """
        #import <UIKit/UIKit.h>

        @interface FeedController : UIViewController
        @property (nonatomic, strong) void (^completion)(void);
        @property (nonatomic, strong) id<UITableViewDelegate> delegate;
        @property (nonatomic, assign) NSString *selectedTitle;
        @end

        @implementation FeedController

        - (void)viewDidLoad {
            [super viewDidLoad];

            [self.model addObserver:self
                         forKeyPath:@"status"
                            options:NSKeyValueObservingOptionNew
                            context:NULL];

            [self.cardView mas_remakeConstraints:^(MASConstraintMaker *make) {
                make.edges.equalTo(self.view);
            }];

            NSURLSessionDataTask *task = [[NSURLSession sharedSession]
                dataTaskWithURL:self.URL
               completionHandler:^(NSData *data, NSURLResponse *response, NSError *error) {
                   [self.tableView reloadData];
               }];
            [task resume];

            __unsafe_unretained id unsafeTarget = self.target;
            NSArray *titles = [NSArray arrayWithObjects:self.selectedTitle, self.fallbackTitle, nil];
            id item = self.items[indexPath.row];
            [self.items addObject:item];
            [self.payload setObject:self.selectedTitle forKey:@"title"];
            [self.tableView deleteRowsAtIndexPaths:@[indexPath]
                                  withRowAnimation:UITableViewRowAnimationAutomatic];
            [self.user setValuesForKeysWithDictionary:self.payload];
        }

        @end

        @implementation NSString (FeedFormatting)
        - (NSString *)ocm_feed_trimmedTitle {
            return [self stringByTrimmingCharactersInSet:NSCharacterSet.whitespaceCharacterSet];
        }
        @end
        """
    ).strip()
    (project / "FeedController.m").write_text(source, encoding="utf-8")

    xcodeproj = project / "App.xcodeproj"
    xcodeproj.mkdir()
    (xcodeproj / "project.pbxproj").write_text(
        textwrap.dedent(
            """
            <<<<<<< HEAD
            OTHER_LDFLAGS = "-ObjC";
            =======
            OTHER_LDFLAGS = "-all_load";
            >>>>>>> feature/build
            HEADER_SEARCH_PATHS = "$(SRCROOT)/Vendor/**";
            ALWAYS_SEARCH_USER_PATHS = YES;
            GCC_PREFIX_HEADER = App/App-Prefix.pch;
            CLANG_ENABLE_MODULES = NO;
            PRODUCT_BUNDLE_IDENTIFIER = com.example.app;
            """
        ).strip(),
        encoding="utf-8",
    )

    (project / "App.xcconfig").write_text(
        'FRAMEWORK_SEARCH_PATHS = "$(PROJECT_DIR)/Vendor"\n',
        encoding="utf-8",
    )
    (project / "App-Prefix.pch").write_text(
        '#import <UIKit/UIKit.h>\n#import "LegacyBusinessHeader.h"\n',
        encoding="utf-8",
    )
    (project / "Podfile").write_text(
        "use_frameworks! :linkage => :static\nuse_modular_headers!\n",
        encoding="utf-8",
    )
    (project / "Podfile.lock").write_text(
        "COCOAPODS: 1.8.4\n",
        encoding="utf-8",
    )
    (project / "LegacySDK.podspec").write_text(
        "s.vendored_libraries = 'libLegacySDK.a'\ns.vendored_frameworks = 'ModernSDK.xcframework'\n",
        encoding="utf-8",
    )
    (project / "Package.swift").write_text(
        "let package = Package(dependencies: [.package(url: \"https://example.com/lib.git\", from: \"1.0.0\")])\n",
        encoding="utf-8",
    )


def assert_contains(output: str, needle: str) -> None:
    if needle not in output:
        raise AssertionError(f"输出中缺少 {needle!r}\\n实际输出:\\n{output}")


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        project = Path(tmp)
        write_fixture(project)

        text_result = run_scan(project, "--min-level", "warning")
        if text_result.returncode != 0:
            raise AssertionError(text_result.stderr)
        assert_contains(text_result.stdout, "block 属性必须使用 copy")
        assert_contains(text_result.stdout, "delegate/dataSource 通常应为 weak")
        assert_contains(text_result.stdout, "Objective-C 对象属性使用 assign")
        assert_contains(text_result.stdout, "__unsafe_unretained 不会置 nil")
        assert_contains(text_result.stdout, "URLSession completion 默认不在主线程")
        assert_contains(text_result.stdout, "KVO 需要唯一 context")
        assert_contains(text_result.stdout, "KVO 使用 NULL context")
        assert_contains(text_result.stdout, "批量 KVC 赋值需要先做 key 白名单")
        assert_contains(text_result.stdout, "remakeConstraints 会移除并重建约束")
        assert_contains(text_result.stdout, "reloadData 命中滚动热路径")
        assert_contains(text_result.stdout, "可变参数集合构造遇到 nil")
        assert_contains(text_result.stdout, "向字典写入 nil key/value 会崩溃")
        assert_contains(text_result.stdout, "数组下标访问需要边界保护")
        assert_contains(text_result.stdout, "列表局部更新必须保证数据源")
        assert_contains(text_result.stdout, "项目或配置文件仍有合并冲突标记")
        assert_contains(text_result.stdout, "这是 Objective-C category")
        assert_contains(text_result.stdout, "OTHER_LDFLAGS 缺少 $(inherited)")
        assert_contains(text_result.stdout, "-all_load 会加载所有静态库对象文件")
        assert_contains(text_result.stdout, "递归 Header Search Paths")
        assert_contains(text_result.stdout, "ALWAYS_SEARCH_USER_PATHS=YES")
        assert_contains(text_result.stdout, "PCH 中的 import 会放大编译依赖")
        assert_contains(text_result.stdout, "搜索路径配置缺少 $(inherited)")
        assert_contains(text_result.stdout, "Podspec 仍暴露闭源 .a")

        json_result = run_scan(project, "--format", "json", "--category", "runtime")
        if json_result.returncode != 0:
            raise AssertionError(json_result.stderr)
        payload = json.loads(json_result.stdout)
        if payload["count"] < 1:
            raise AssertionError("JSON 输出应包含 runtime 命中")

        crash_result = run_scan(project, "--format", "json", "--category", "crash", "--min-level", "warning")
        if crash_result.returncode != 0:
            raise AssertionError(crash_result.stderr)
        crash_payload = json.loads(crash_result.stdout)
        if crash_payload["count"] < 4:
            raise AssertionError("JSON 输出应包含新增 crash 命中")

        build_result = run_scan(project, "--format", "json", "--category", "build")
        if build_result.returncode != 0:
            raise AssertionError(build_result.stderr)
        build_payload = json.loads(build_result.stdout)
        if build_payload["count"] < 10:
            raise AssertionError("JSON 输出应包含 build 配置命中")

        failing_result = run_scan(project, "--min-level", "warning", "--fail-on-finding")
        if failing_result.returncode != 1:
            raise AssertionError("--fail-on-finding 发现风险时应返回 1")

    print("scan_objc_risks.py tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
