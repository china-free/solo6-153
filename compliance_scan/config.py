"""配置加载模块"""

import os
import re
import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict

try:
    import yaml
except ImportError:
    yaml = None


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


def load_config(config_path: Optional[str] = None) -> Config:
    """加载配置文件"""
    if yaml is None:
        raise ImportError("PyYAML 未安装，请运行: pip install PyYAML")

    if config_path:
        config_file = Path(config_path)
        if not config_file.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")
    else:
        default_path = Path(__file__).parent / "default-patterns.yaml"
        if default_path.exists():
            config_file = default_path
        else:
            raise FileNotFoundError("未找到配置文件")

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

    return Config(
        patterns=patterns,
        excludes=excludes,
        config_path=config_file
    )
