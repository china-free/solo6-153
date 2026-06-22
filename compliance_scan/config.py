"""配置加载模块

负责从 YAML 文件加载规则配置，并构建 RuleManager 实例。
规则本身的逻辑由 rules.RuleManager 管理，本模块只做配置解析和组装。
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import yaml
except ImportError:
    yaml = None

from .rules import RuleManager, Pattern

PROJECT_CONFIG_NAMES = [
    '.compliance-scan.yaml',
    'compliance-scan.yaml',
    'custom-rules.yaml',
]


@dataclass
class Config:
    """配置加载结果

    包装 RuleManager 和配置元信息，供 CLI 和下游模块使用。
    规则相关的逻辑（过滤、匹配）请通过 rule_manager 访问。
    """
    rule_manager: RuleManager
    config_path: Optional[Path] = None
    project_config_path: Optional[Path] = None

    @property
    def patterns(self) -> list:
        """向后兼容：返回所有规则列表

        新代码请使用 rule_manager.get_all_rules() 或 get_rules_for_file()。
        """
        return self.rule_manager.get_all_rules()

    @property
    def excludes(self) -> list:
        """向后兼容：返回全局排除列表

        新代码请使用 rule_manager.should_exclude()。
        """
        return self.rule_manager.get_global_excludes()

    def should_exclude(self, path: str) -> bool:
        """向后兼容：判断文件是否被排除

        新代码请使用 rule_manager.should_exclude()。
        """
        return self.rule_manager.should_exclude(path)


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


def _build_rule_manager_from_yaml(config_file: Path) -> RuleManager:
    """从 YAML 配置文件构建 RuleManager"""
    if yaml is None:
        raise ImportError("PyYAML 未安装，请运行: pip install PyYAML")

    with open(config_file, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f) or {}

    manager = RuleManager()

    for p in data.get('patterns', []):
        rule = Pattern(
            name=p['name'],
            pattern=p['pattern'],
            severity=p.get('severity', 'medium'),
            description=p.get('description', ''),
            includes=p.get('includes', []),
            excludes=p.get('excludes', []),
        )
        manager.add_rule(rule)

    excludes = data.get('excludes', [])
    manager.set_global_excludes(excludes)

    return manager


def load_config(
    config_path: Optional[str] = None,
    scan_path: Optional[str] = None,
) -> Config:
    """加载配置文件，返回包含 RuleManager 的 Config 对象

    加载策略 (当 config_path 未显式指定时):
    1. 加载内置 default-patterns.yaml 作为基础
    2. 从 scan_path 向上搜索项目级配置文件
    3. 如果找到项目级配置，与内置规则合并 (项目级同名规则覆盖，新增规则追加)

    当 config_path 显式指定时:
    - 仅加载指定文件，不与内置规则合并 (用户全权控制)
    """
    if yaml is None:
        raise ImportError("PyYAML 未安装，请运行: pip install PyYAML")

    if config_path:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
        manager = _build_rule_manager_from_yaml(config_file)
        return Config(
            rule_manager=manager,
            config_path=config_file,
        )

    default_path = Path(__file__).parent / "default-patterns.yaml"
    if not default_path.exists():
        raise FileNotFoundError("未找到内置配置文件 default-patterns.yaml")

    base_manager = _build_rule_manager_from_yaml(default_path)

    project_config_path = None
    if scan_path:
        project_config_path = find_project_config(scan_path)

    if project_config_path:
        project_manager = _build_rule_manager_from_yaml(project_config_path)
        base_manager.merge(project_manager)
        return Config(
            rule_manager=base_manager,
            config_path=default_path,
            project_config_path=project_config_path,
        )

    return Config(
        rule_manager=base_manager,
        config_path=default_path,
    )
