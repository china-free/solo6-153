"""自动脱敏模块"""

import os
from typing import List, Tuple

from .scanner import ScanResult, Match
from .config import Config


def mask_text(text: str) -> str:
    """将文本脱敏为 ***，保留首字符和尾字符"""
    if len(text) <= 2:
        return '*' * len(text)
    return text[0] + '*' * max(len(text) - 2, 3) + text[-1]


def apply_fix(file_path: str, matches: List[Match], config: Config) -> Tuple[int, List[str]]:
    """对单个文件应用脱敏修复
    
    返回: (修复数量, 修改后的行列表)
    """
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except (IOError, OSError):
        return 0, []

    fix_count = 0
    line_matches = {}

    for match in matches:
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


def apply_fixes(results: List[ScanResult], config: Config) -> int:
    """对所有扫描结果应用脱敏修复
    
    返回: 总修复数量
    """
    total_fixes = 0

    for result in results:
        if not result.matches:
            continue

        fix_count, new_lines = apply_fix(result.file_path, result.matches, config)

        if fix_count > 0 and new_lines:
            try:
                with open(result.file_path, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                total_fixes += fix_count
                print(f"  已修复 {result.file_path}: {fix_count} 处")
            except (IOError, OSError) as e:
                print(f"  修复失败 {result.file_path}: {e}")

    return total_fixes
