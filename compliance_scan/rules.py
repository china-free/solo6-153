"""规则管理模块

RuleManager 是规则系统的统一入口，封装了：
- 规则集合的增删改查
- 文件级别的过滤（excludes / includes）
- 基于文件上下文的动态规则选择
- 按严重程度、文件类型等维度的规则筛选

后续做精细化合规策略控制时，只需在 RuleManager 上扩展，
不需要改动扫描器、修复器等下游模块。
"""

import os
import re
import fnmatch
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Dict, Set, Iterable


@dataclass
class Pattern:
    """匹配规则

    Attributes:
        name: 规则唯一标识
        pattern: 正则表达式字符串
        severity: 严重程度 (critical / high / medium / low)
        description: 规则描述
        includes: 仅对匹配这些 glob 模式的文件生效（空列表表示全部生效）
        excludes: 对匹配这些 glob 模式的文件不生效（优先级高于 includes）
        regex: 编译后的正则对象（自动生成）
    """
    name: str
    pattern: str
    severity: str = "medium"
    description: str = ""
    includes: List[str] = field(default_factory=list)
    excludes: List[str] = field(default_factory=list)
    regex: re.Pattern = field(init=False)

    def __post_init__(self):
        self.regex = re.compile(self.pattern, re.MULTILINE)

    def applies_to_file(self, file_path: str) -> bool:
        """判断该规则是否适用于指定文件"""
        norm_path = file_path.replace('\\', '/')
        base_name = os.path.basename(norm_path)

        if self.excludes:
            for pattern in self.excludes:
                if _match_glob(pattern, norm_path, base_name):
                    return False

        if self.includes:
            for pattern in self.includes:
                if _match_glob(pattern, norm_path, base_name):
                    return True
            return False

        return True


def _match_glob(pattern: str, full_path: str, base_name: str) -> bool:
    """统一的 glob 匹配工具函数

    - 以 / 结尾的 pattern 视为目录前缀匹配
    - 其他 pattern 先对完整路径匹配，失败后再对文件名匹配
    """
    if pattern.endswith('/'):
        return pattern in full_path
    if fnmatch.fnmatch(full_path, pattern):
        return True
    if fnmatch.fnmatch(base_name, pattern):
        return True
    return False


class RuleManager:
    """规则管理器

    统一管理所有合规规则和全局文件过滤器，
    并根据文件上下文动态返回需要应用的规则集合。
    """

    def __init__(self):
        self._rules: Dict[str, Pattern] = {}
        self._global_excludes: List[str] = []
        self._severity_order = {'critical': 0, 'high': 1, 'medium': 2, 'low': 3}

    def add_rule(self, rule: Pattern) -> None:
        """添加一条规则，同名则覆盖"""
        self._rules[rule.name] = rule

    def add_rules(self, rules: Iterable[Pattern]) -> None:
        """批量添加规则"""
        for rule in rules:
            self.add_rule(rule)

    def remove_rule(self, name: str) -> bool:
        """移除一条规则，返回是否存在"""
        if name in self._rules:
            del self._rules[name]
            return True
        return False

    def get_rule(self, name: str) -> Optional[Pattern]:
        """根据名称获取规则"""
        return self._rules.get(name)

    def get_all_rules(self) -> List[Pattern]:
        """获取所有规则，按严重程度从高到低排序"""
        rules = list(self._rules.values())
        rules.sort(key=lambda r: self._severity_order.get(r.severity, 99))
        return rules

    def get_rule_names(self) -> Set[str]:
        """获取所有规则名称"""
        return set(self._rules.keys())

    @property
    def rule_count(self) -> int:
        """规则总数"""
        return len(self._rules)

    def set_global_excludes(self, patterns: List[str]) -> None:
        """设置全局文件排除模式"""
        self._global_excludes = list(patterns)

    def add_global_exclude(self, pattern: str) -> None:
        """添加一条全局排除模式"""
        if pattern not in self._global_excludes:
            self._global_excludes.append(pattern)

    def get_global_excludes(self) -> List[str]:
        """获取全局排除模式"""
        return list(self._global_excludes)

    def should_exclude(self, file_path: str) -> bool:
        """判断文件是否被全局排除

        这是文件级别的快速过滤，用于在文件遍历阶段跳过整个文件。
        """
        norm_path = file_path.replace('\\', '/')
        base_name = os.path.basename(norm_path)

        for pattern in self._global_excludes:
            if _match_glob(pattern, norm_path, base_name):
                return True
        return False

    def get_rules_for_file(self, file_path: str) -> List[Pattern]:
        """获取适用于指定文件的规则集合

        这是规则级别的细粒度过滤，每个规则可以有自己的 includes/excludes。
        返回的规则按严重程度从高到低排序。
        """
        applicable = [
            rule for rule in self._rules.values()
            if rule.applies_to_file(file_path)
        ]
        applicable.sort(key=lambda r: self._severity_order.get(r.severity, 99))
        return applicable

    def filter_by_severity(
        self,
        min_severity: str,
        rules: Optional[List[Pattern]] = None,
    ) -> List[Pattern]:
        """按最低严重程度过滤规则

        Args:
            min_severity: 最低严重程度 (critical / high / medium / low)
            rules: 待过滤的规则列表，为 None 则使用全部规则

        Returns:
            严重程度 >= min_severity 的规则列表
        """
        if rules is None:
            rules = self.get_all_rules()

        min_level = self._severity_order.get(min_severity, 99)
        return [
            r for r in rules
            if self._severity_order.get(r.severity, 99) <= min_level
        ]

    def merge(self, other: 'RuleManager') -> None:
        """合并另一个 RuleManager

        合并策略:
        - 规则: 同名覆盖，新增追加
        - 全局排除: 合并去重
        """
        for name, rule in other._rules.items():
            self._rules[name] = rule

        seen = set(self._global_excludes)
        for pattern in other._global_excludes:
            if pattern not in seen:
                self._global_excludes.append(pattern)
                seen.add(pattern)

    def clone(self) -> 'RuleManager':
        """深拷贝一份 RuleManager"""
        new_mgr = RuleManager()
        new_mgr._rules = {name: Pattern(
            name=rule.name,
            pattern=rule.pattern,
            severity=rule.severity,
            description=rule.description,
            includes=list(rule.includes),
            excludes=list(rule.excludes),
        ) for name, rule in self._rules.items()}
        new_mgr._global_excludes = list(self._global_excludes)
        return new_mgr
