"""终端输出模块 - 支持标红高亮"""

import sys
import os
from typing import List

from .scanner import ScanResult, Match


class Colors:
    """ANSI 颜色代码"""
    RED = '\033[91m'
    YELLOW = '\033[93m'
    GREEN = '\033[92m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

    SEVERITY_COLORS = {
        'critical': '\033[95m',
        'high': '\033[91m',
        'medium': '\033[93m',
        'low': '\033[96m',
    }


def supports_color() -> bool:
    """检查终端是否支持颜色"""
    if not sys.stdout.isatty():
        return False
    if os.environ.get('NO_COLOR'):
        return False
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass
    return True


def highlight_match(line: str, start: int, end: int, use_color: bool = True) -> str:
    """高亮匹配的文本"""
    if not use_color:
        return line
    return (
        line[:start]
        + Colors.RED + Colors.BOLD
        + line[start:end]
        + Colors.RESET
        + line[end:]
    )


def format_match(match: Match, use_color: bool = True) -> str:
    """格式化单个匹配结果"""
    severity = match.pattern.severity.upper()
    if use_color:
        severity_color = Colors.SEVERITY_COLORS.get(match.pattern.severity, '')
        severity = f"{severity_color}{severity}{Colors.RESET}"

    highlighted_line = highlight_match(
        match.line_content,
        match.start,
        match.end,
        use_color
    )

    file_path = match.file_path
    if use_color:
        file_path = f"{Colors.CYAN}{file_path}{Colors.RESET}"

    rule_name = match.pattern.name
    if use_color:
        rule_name = f"{Colors.YELLOW}{rule_name}{Colors.RESET}"

    lines = [
        f"  {file_path}:{match.line_number}:{match.start + 1}",
        f"    规则: {rule_name} [{severity}] - {match.pattern.description}",
        f"    匹配: '{match.match_text}'",
        f"    代码: {highlighted_line}",
    ]
    return '\n'.join(lines)


def print_report(results: List[ScanResult], use_color: bool = None) -> None:
    """打印扫描报告"""
    if use_color is None:
        use_color = supports_color()

    total_matches = sum(len(r.matches) for r in results)
    files_with_issues = len(results)

    if total_matches == 0:
        if use_color:
            print(f"{Colors.GREEN}{Colors.BOLD}✓ 未发现敏感信息{Colors.RESET}")
        else:
            print("✓ 未发现敏感信息")
        return

    if use_color:
        print(f"{Colors.RED}{Colors.BOLD}✗ 发现 {total_matches} 个敏感信息匹配（涉及 {files_with_issues} 个文件）{Colors.RESET}")
    else:
        print(f"✗ 发现 {total_matches} 个敏感信息匹配（涉及 {files_with_issues} 个文件）")

    print()

    for result in results:
        for match in result.matches:
            print(format_match(match, use_color))
            print()

    if use_color:
        print(f"{Colors.YELLOW}提示: 使用 --fix 参数可自动脱敏{Colors.RESET}")
    else:
        print("提示: 使用 --fix 参数可自动脱敏")
