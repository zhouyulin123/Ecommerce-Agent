"""地址文本归一化工具，供路由与 SQL 过滤复用。"""

import re

from app.constants import LOCATION_MARKERS


def strip_location_whitespace(value: str) -> str:
    """去除地址中的空白字符，便于口语输入与库内地址匹配。"""
    return re.sub(r"\s+", "", value or "")


def normalize_location_text(value: str) -> str:
    """移除地址中的行政区划后缀，提升“普陀区/上海普陀区/上海市普陀区”匹配鲁棒性。"""
    normalized = strip_location_whitespace(value)
    for marker in LOCATION_MARKERS:
        normalized = normalized.replace(marker, "")
    return normalized


def canonical_location(value: str) -> str:
    """将完整地址压缩为更实用的查询词（例如“上海市普陀区” -> “普陀区”）。"""
    collapsed = strip_location_whitespace(value)
    for marker in LOCATION_MARKERS:
        if marker in collapsed:
            tail = collapsed.split(marker, 1)[1].strip()
            if tail:
                collapsed = tail
    return collapsed


def sql_normalize_location(address_column: str) -> str:
    """生成与 Python 端一致的 SQL 地址归一化表达式。"""
    expr = address_column
    for marker in LOCATION_MARKERS:
        expr = f"REPLACE({expr}, '{marker}', '')"
    return expr
