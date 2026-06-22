"""并发扫描模块

扫描器通过 RuleManager 获取规则，不直接依赖配置格式。
规则级别的过滤（includes/excludes）由 RuleManager 负责。
"""

import os
from dataclasses import dataclass
from typing import List, Iterator, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from .rules import Pattern
from .config import Config


@dataclass
class Match:
    """匹配结果"""
    file_path: str
    line_number: int
    line_content: str
    pattern: Pattern
    match_text: str
    start: int
    end: int


@dataclass
class ScanResult:
    """扫描结果"""
    file_path: str
    matches: List[Match]


def is_text_file(file_path: str, chunk_size: int = 8192) -> bool:
    """检查是否为文本文件"""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(chunk_size)
        if b'\x00' in chunk:
            return False
        try:
            chunk.decode('utf-8')
            return True
        except UnicodeDecodeError:
            try:
                chunk.decode('gbk')
                return True
            except UnicodeDecodeError:
                return False
    except (IOError, OSError):
        return False


def get_target_files(path: str, config: Config) -> Iterator[str]:
    """获取所有需要扫描的文件

    使用 RuleManager 的全局排除来过滤文件。
    单文件直接判断是否被排除；目录则在遍历时过滤。
    """
    rule_mgr = config.rule_manager

    if os.path.isfile(path):
        if not rule_mgr.should_exclude(path) and is_text_file(path):
            yield path
        return

    for root, dirs, files in os.walk(path):
        dirs[:] = [
            d for d in dirs
            if not rule_mgr.should_exclude(os.path.join(root, d) + '/')
        ]

        for file in files:
            file_path = os.path.join(root, file)
            if not rule_mgr.should_exclude(file_path) and is_text_file(file_path):
                yield file_path


def scan_file(file_path: str, config: Config) -> ScanResult:
    """扫描单个文件

    通过 RuleManager.get_rules_for_file() 获取该文件适用的规则，
    而不是对所有文件都应用全部规则。
    """
    rule_mgr = config.rule_manager
    applicable_rules = rule_mgr.get_rules_for_file(file_path)

    if not applicable_rules:
        return ScanResult(file_path=file_path, matches=[])

    matches = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='replace') as f:
            lines = f.readlines()
    except (IOError, OSError):
        return ScanResult(file_path=file_path, matches=[])

    for line_num, line in enumerate(lines, 1):
        for rule in applicable_rules:
            for m in rule.regex.finditer(line):
                matches.append(Match(
                    file_path=file_path,
                    line_number=line_num,
                    line_content=line.rstrip('\n'),
                    pattern=rule,
                    match_text=m.group(),
                    start=m.start(),
                    end=m.end(),
                ))

    return ScanResult(file_path=file_path, matches=matches)


def scan_path(
    path: str,
    config: Config,
    max_workers: Optional[int] = None,
) -> List[ScanResult]:
    """并发扫描路径下的所有文件"""
    if max_workers is None:
        max_workers = min(os.cpu_count() or 4, 16)

    files = list(get_target_files(path, config))
    results = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(scan_file, file_path, config): file_path
            for file_path in files
        }

        for future in as_completed(future_to_file):
            result = future.result()
            if result.matches:
                results.append(result)

    return results
