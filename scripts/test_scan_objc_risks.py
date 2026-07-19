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
        }

        @end
        """
    ).strip()
    (project / "FeedController.m").write_text(source, encoding="utf-8")


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
        assert_contains(text_result.stdout, "KVO 需要唯一 context")
        assert_contains(text_result.stdout, "remakeConstraints 会移除并重建约束")
        assert_contains(text_result.stdout, "reloadData 命中滚动热路径")

        json_result = run_scan(project, "--format", "json", "--category", "runtime")
        if json_result.returncode != 0:
            raise AssertionError(json_result.stderr)
        payload = json.loads(json_result.stdout)
        if payload["count"] < 1:
            raise AssertionError("JSON 输出应包含 runtime 命中")

        failing_result = run_scan(project, "--min-level", "warning", "--fail-on-finding")
        if failing_result.returncode != 1:
            raise AssertionError("--fail-on-finding 发现风险时应返回 1")

    print("scan_objc_risks.py tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
