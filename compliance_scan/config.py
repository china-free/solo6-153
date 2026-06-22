"""配置加载模块"""

import os
import re
import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Tuple

try:
    import yaml
except ImportError:
    yaml = None

PROJECT_CONFIG_NAMES = [
    '.compliance-scan.yaml',
    'compliance-scan.yaml',
    'custom-rules.yaml',
]


@dataclass
class Pattern:
    """匹配规则"""
    name: str
    pattern: str
    severity: str = "medium"
    description: str = ""
    regex: re.Pattern = field(init=False)

    def __post_init__(self):
        self.regex = re.compile(self.pattern, re.MULTILINE)


@dataclass
class Config:
    """扫描配置"""
    patterns: List[Pattern]
    excludes: List[str]
    config_path: Optional[Path] = None
    project_config_path: Optional[Path] = None

    def should_exclude(self, path: str) -> bool:
        """检查路径是否应该被排除"""
        path = path.replace('\\', '/')
        for pattern in self.excludes:
            if pattern.endswith('/'):
                if pattern in path:
                    return True
            elif fnmatch.fnmatch(path, pattern):
                return True
            elif fnmatch.fnmatch(os.path.basename(path), pattern):
                return True
        return False


def find_git_root(start_path: str) -> Optional[str]:
    """从指定路径向上查找 Git 仓库根目录"""
    current = os.path.abspath(start_path)
    if os.path.isfile(current):
        current = os.path.dirname(current)

    while True:
        if os.path.isdir(os.path.join(current, '.git')):
            return current
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def find_project_config(scan_path: str) -> Optional[Path]:
    """从扫描路径向上查找项目级配置文件

    搜索策略:
    1. 从扫描目标路径开始，逐级向上到 Git 根目录
    2. 在每一级查找 PROJECT_CONFIG_NAMES 中的配置文件
    3. 如果不在 Git 仓库中，只搜索扫描目标路径本身
    """
    start = os.path.abspath(scan_path)
    if os.path.isfile(start):
        start = os.path.dirname(start)

    git_root = find_git_root(start)
    search_root = git_root if git_root else start

    current = start
    while True:
        for name in PROJECT_CONFIG_NAMES:
            candidate = os.path.join(current, name)
            if os.path.isfile(candidate):
                return Path(candidate)

        if current == search_root:
            break
        parent = os.path.dirname(current)
        if parent == current:
            break
        current = parent

    return None


def _load_yaml_config(config_file: Path) -> Tuple[List[Pattern], List[str]]:
    """从 YAML 文件加载规则和排除项"""
    with open(config_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    patterns = []
    for p in data.get('patterns', []):
        patterns.append(Pattern(
            name=p['name'],
            pattern=p['pattern'],
            severity=p.get('severity', 'medium'),
            description=p.get('description', '')
        ))

    excludes = data.get('excludes', [])

    return patterns, excludes


def _merge_configs(
    base_patterns: List[Pattern],
    base_excludes: List[str],
    override_patterns: List[Pattern],
    override_excludes: List[str],
) -> Tuple[List[Pattern], List[str]]:
    """合并内置配置和项目级配置

    合并策略:
    - 规则: 项目级按 name 覆盖内置同名规则，新增规则追加到末尾
    - 排除项: 合并去重
    """
    merged_patterns = list(base_patterns)
    base_names = {p.name for p in base_patterns}

    for op in override_patterns:
        if op.name in base_names:
            merged_patterns = [p if p.name != op.name else op for p in merged_patterns]
        else:
            merged_patterns.append(op)

    merged_excludes = list(base_excludes)
    seen = set(base_excludes)
    for ex in override_excludes:
        if ex not in seen:
            merged_excludes.append(ex)
            seen.add(ex)

    return merged_patterns, merged_excludes


def load_config(
    config_path: Optional[str] = None,
    scan_path: Optional[str] = None,
) -> Config:
    """加载配置文件

    加载策略 (当 config_path 未显式指定时):
    1. 加载内置 default-patterns.yaml 作为基础
    2. 从 scan_path 向上搜索项目级配置文件
    3. 如果找到项目级配置，与内置规则合并 (项目级同名规则覆盖内置，新增规则追加)
    4. 如果找不到任何配置文件则报错

    当 config_path 显式指定时:
    - 仅加载指定文件，不与内置规则合并 (用户全权控制)
    """
    if yaml is None:
        raise ImportError("PyYAML 未安装，请运行: pip install PyYAML")

    if config_path:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        patterns, excludes = _load_yaml_config(config_file)
        return Config(
            patterns=patterns,
            excludes=excludes,
            config_path=config_file,
        )

    default_path = Path(__file__).parent / "default-patterns.yaml"
    if not default_path.exists():
        raise FileNotFoundError("未找到内置配置文件 default-patterns.yaml")

    base_patterns, base_excludes = _load_yaml_config(default_path)

    project_config_path = None
    if scan_path:
        project_config_path = find_project_config(scan_path)

    if project_config_path:
        project_patterns, project_excludes = _load_yaml_config(project_config_path)
        merged_patterns, merged_excludes = _merge_configs(
            base_patterns, base_excludes,
            project_patterns, project_excludes,
        )
        return Config(
            patterns=merged_patterns,
            excludes=merged_excludes,
            config_path=default_path,
            project_config_path=project_config_path,
        )

    return Config(
        patterns=base_patterns,
        excludes=base_excludes,
        config_path=default_path,
    )
