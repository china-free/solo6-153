"""自动脱敏模块

脱敏逻辑不直接依赖配置，而是基于扫描出的 Match 结果进行替换。
未来可通过 RuleManager 增加"哪些规则允许自动修复"的精细化控制。
"""

import os
from typing import List, Tuple, Optional

from .scanner import ScanResult, Match
from .rules import RuleManager


def mask_text(text: str) -> str:
    """将文本脱敏为 ***，保留首字符和尾字符"""
    if len(text) <= 2:
        return '*' * len(text)
    return text[0] + '*' * max(len(text) - 2, 3) + text[-1]


def _rule_is_fixable(rule_name: str, rule_manager: Optional[RuleManager]) -> bool:
    """判断规则是否允许自动修复

    当前版本所有规则默认都可修复。
    未来可在 RuleManager 或 Pattern 中增加 fixable 字段做精细化控制。
    """
    if rule_manager is None:
        return True
    rule = rule_manager.get_rule(rule_name)
    if rule is None:
        return True
    return True


def apply_fix(
    file_path: str,
    matches: List[Match],
    rule_manager: Optional[RuleManager] = None,
) -> Tuple[int, List[str]]:
    """对单个文件应用脱敏修复

    Args:
        file_path: 文件路径
        matches: 该文件的匹配结果列表
        rule_manager: 规则管理器（可选），用于判断规则是否可修复

    Returns:
        (修复数量, 修改后的行列表)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except (IOError, OSError):
        return 0, []

    fixable_matches = [
        m for m in matches
        if _rule_is_fixable(m.pattern.name, rule_manager)
    ]

    if not fixable_matches:
        return 0, []

    fix_count = 0
    line_matches = {}

    for match in fixable_matches:
        line_idx = match.line_number - 1
        if line_idx not in line_matches:
            line_matches[line_idx] = []
        line_matches[line_idx].append(match)

    for line_idx, match_list in line_matches.items():
        match_list.sort(key=lambda m: m.start, reverse=True)
        line = lines[line_idx]

        for match in match_list:
            masked = mask_text(match.match_text)
            line = line[:match.start] + masked + line[match.end:]
            fix_count += 1

        lines[line_idx] = line

    return fix_count, lines


def apply_fixes(results: List[ScanResult], config=None) -> int:
    """对所有扫描结果应用脱敏修复

    Args:
        results: 扫描结果列表
        config: Config 对象（向后兼容），从中提取 RuleManager

    Returns:
        总修复数量
    """
    rule_manager = None
    if config is not None and hasattr(config, 'rule_manager'):
        rule_manager = config.rule_manager

    total_fixes = 0

    for result in results:
        if not result.matches:
            continue

        fix_count, new_lines = apply_fix(result.file_path, result.matches, rule_manager)

        if fix_count > 0 and new_lines:
            try:
                with open(result.file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                total_fixes += fix_count
                print(f"  已修复 {result.file_path}: {fix_count} 处")
            except (IOError, OSError) as e:
                print(f"  修复失败 {result.file_path}: {e}")

    return total_fixes
