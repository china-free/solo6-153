"""CLI 主模块"""

import argparse
import sys
import os
from typing import List, Optional

from .config import load_config, Config
from .scanner import scan_path, ScanResult
from .reporter import print_report
from .fixer import apply_fixes
from . import __version__


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        prog='compliance-scan',
        description='合规扫描工具 - 防止敏感信息泄露',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  compliance-scan .                          # 扫描当前目录
  compliance-scan src/ --config my-rules.yaml # 使用自定义规则
  compliance-scan . --fix                    # 扫描并自动脱敏
  compliance-scan . --no-color               # 禁用颜色输出
  compliance-scan --install-hook             # 安装 pre-commit hook
        """
    )

    parser.add_argument(
        'path',
        nargs='?',
        default='.',
        help='要扫描的文件或目录路径（默认: 当前目录）'
    )

    parser.add_argument(
        '-c', '--config',
        help='自定义规则配置文件路径（YAML 格式）'
    )

    parser.add_argument(
        '--fix',
        action='store_true',
        help='自动脱敏匹配到的敏感信息'
    )

    parser.add_argument(
        '--no-color',
        action='store_true',
        help='禁用终端颜色输出'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=None,
        help='并发扫描的线程数（默认: CPU 核心数，最大 16）'
    )

    parser.add_argument(
        '--install-hook',
        action='store_true',
        help='安装 pre-commit hook 到当前 Git 仓库'
    )

    parser.add_argument(
        '--uninstall-hook',
        action='store_true',
        help='卸载 pre-commit hook'
    )

    parser.add_argument(
        '-v', '--version',
        action='version',
        version=f'compliance-scan {__version__}'
    )

    return parser


def install_hook() -> int:
    """安装 pre-commit hook"""
    git_dir = os.path.join(os.getcwd(), '.git')
    if not os.path.isdir(git_dir):
        print("错误: 当前目录不是 Git 仓库", file=sys.stderr)
        return 1

    hooks_dir = os.path.join(git_dir, 'hooks')
    os.makedirs(hooks_dir, exist_ok=True)

    hook_path = os.path.join(hooks_dir, 'pre-commit')

    hook_content = """#!/usr/bin/env bash
# compliance-scan pre-commit hook
# 自动扫描暂存文件中的敏感信息

echo "正在运行合规扫描..."

# 获取暂存的文件列表
staged_files=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)

if [ -z "$staged_files" ]; then
    echo "没有暂存的文件，跳过扫描"
    exit 0
fi

# 扫描暂存的文件
if command -v compliance-scan >/dev/null 2>&1; then
    compliance-scan $staged_files
    scan_exit=$?
elif command -v python >/dev/null 2>&1; then
    python -m compliance_scan $staged_files
    scan_exit=$?
elif command -v python3 >/dev/null 2>&1; then
    python3 -m compliance_scan $staged_files
    scan_exit=$?
else
    echo "警告: 未找到 compliance-scan，请先安装"
    echo "  pip install compliance-scan"
    exit 0
fi

if [ $scan_exit -ne 0 ]; then
    echo ""
    echo "✗ 发现敏感信息，提交已被阻止"
    echo "  请修复上述问题后再提交，或使用:"
    echo "  compliance-scan . --fix"
    exit 1
fi

echo "✓ 合规扫描通过"
exit 0
"""

    try:
        with open(hook_path, 'w', encoding='utf-8') as f:
            f.write(hook_content)

        if os.name != 'nt':
            os.chmod(hook_path, 0o755)

        print(f"✓ pre-commit hook 已安装: {hook_path}")
        print("  每次提交前将自动扫描敏感信息")
        return 0
    except IOError as e:
        print(f"错误: 安装 hook 失败: {e}", file=sys.stderr)
        return 1


def uninstall_hook() -> int:
    """卸载 pre-commit hook"""
    git_dir = os.path.join(os.getcwd(), '.git')
    if not os.path.isdir(git_dir):
        print("错误: 当前目录不是 Git 仓库", file=sys.stderr)
        return 1

    hook_path = os.path.join(git_dir, 'hooks', 'pre-commit')

    if not os.path.exists(hook_path):
        print("pre-commit hook 不存在")
        return 0

    try:
        os.remove(hook_path)
        print(f"✓ pre-commit hook 已卸载")
        return 0
    except IOError as e:
        print(f"错误: 卸载 hook 失败: {e}", file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    """主入口函数"""
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.install_hook:
        return install_hook()

    if args.uninstall_hook:
        return uninstall_hook()

    try:
        config = load_config(args.config)
    except Exception as e:
        print(f"错误: 加载配置失败: {e}", file=sys.stderr)
        return 2

    if args.config:
        print(f"使用配置文件: {config.config_path}")

    target_path = args.path
    if not os.path.exists(target_path):
        print(f"错误: 路径不存在: {target_path}", file=sys.stderr)
        return 2

    print(f"正在扫描: {target_path}")
    print(f"规则数量: {len(config.patterns)}")
    print()

    results = scan_path(target_path, config, max_workers=args.workers)

    use_color = not args.no_color
    print_report(results, use_color=use_color)

    total_matches = sum(len(r.matches) for r in results)

    if total_matches > 0 and args.fix:
        print()
        print("正在自动脱敏...")
        fixed = apply_fixes(results, config)
        print()
        print(f"✓ 已完成脱敏，共修复 {fixed} 处敏感信息")

    return 1 if total_matches > 0 and not args.fix else 0
