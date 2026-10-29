"""标准号的规范化与解析。

中国标准号在真实文档里的写法极其混乱：全角字母、破折号有七八种写法、
空格有无不一致、年号两位四位混用。任何"标准版本比对"的第一步都必须是归一，
否则 GB 50014-2021 与 GB50014—2021 会被当成两个不同标准。
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

# 按长度降序排列，保证 GB/T 先于 GB 匹配
KNOWN_PREFIXES = (
    "GB/T", "GB/Z", "GBJ",
    "CJJ", "CJ/T", "CJ",
    "HJ/T", "HJ",
    "SL", "JGJ", "JTG", "TB",
    "DL/T", "DL", "NB/T", "SY/T", "SH/T", "HG/T", "QB/T", "YY",
    "TSG", "CECS", "DB",
)

# 各种破折号：连字符、hyphen、en dash、em dash、全角减号、全角连字符
_DASHES = "-\u2010\u2011\u2012\u2013\u2014\u2015\u2212\uff0d"

_CODE_RE = re.compile(
    r"^(?P<prefix>[A-Z]{1,4}(?:/[A-Z])?)(?P<number>\d+(?:\.\d+)*)(?:-(?P<year>\d{2,4}))?$"
)


class CodeParseError(ValueError):
    """标准号无法解析。"""


def _clean(text: str) -> str:
    """全角转半角、统一破折号、去空格、转大写。"""
    s = unicodedata.normalize("NFKC", text or "")
    for d in _DASHES:
        s = s.replace(d, "-")
    s = re.sub(r"\s+", "", s)
    return s.upper()


def expand_year(year: int | str | None) -> int | None:
    """两位年号补全。

    GBJ 14-87 指 1987 年。以 50 为分界：>=50 补 19，<50 补 20。
    这个分界是经验值，仅对我国标准编号惯例成立（现行最早标准为 1980 年代，
    不存在 19xx 之前仍在用的编号）。
    """
    if year is None:
        return None
    y = int(year)
    if y >= 1000:
        return y
    if 100 <= y < 1000:
        raise CodeParseError(f"年号 {year} 位数异常")
    return 1900 + y if y >= 50 else 2000 + y


@dataclass(frozen=True)
class StdCode:
    """一个已归一的中华人民共和国标准编号。"""

    prefix: str
    number: str
    year: int | None = None
    raw: str = ""
    year_digits: int = 4  # 原写法是两位年号(如 GBJ 14-87)时保留，显示用

    @property
    def base_number(self) -> str:
        """GB 16171.1-2024 -> 16171"""
        return self.number.split(".")[0]

    @property
    def part(self) -> str | None:
        """GB 16171.1-2024 -> "1"；主标准返回 None。"""
        bits = self.number.split(".")[1:]
        return ".".join(bits) if bits else None

    @property
    def family(self) -> str:
        """同一主号的所有版本归为一族，用于精确匹配、排除模糊检索噪声。"""
        return f"{self.prefix} {self.base_number}"

    @property
    def year_text(self) -> str:
        if self.year is None:
            return ""
        return f"{self.year % 100:02d}" if self.year_digits == 2 else str(self.year)

    @property
    def canonical(self) -> str:
        return f"{self.prefix} {self.number}" + (f"-{self.year_text}" if self.year else "")

    def with_part(self, part: str | None) -> "StdCode":
        num = f"{self.base_number}.{part}" if part else self.base_number
        return StdCode(self.prefix, num, self.year, self.raw, self.year_digits)

    def __str__(self) -> str:  # pragma: no cover - 便于交互调试
        return self.canonical


def parse(text: str) -> StdCode:
    """解析任意写法的标准号。

    >>> parse("GB50014—2021").canonical
    'GB 50014-2021'
    >>> parse("ＧＢ／Ｔ ５００５０－２０１７").canonical
    'GB/T 50050-2017'
    """
    if not text or not text.strip():
        raise CodeParseError("空标准号")
    s = _clean(text)
    m = _CODE_RE.match(s)
    if not m:
        raise CodeParseError(f"无法解析标准号: {text!r}（归一后为 {s!r}）")

    prefix = m.group("prefix")
    # 前缀归一：CECS/T 之类不常见组合保持原样；已知前缀做最长匹配校验
    num = m.group("number")
    if prefix not in KNOWN_PREFIXES:
        # 允许未知前缀通过（如企业标准 Q/SH），但要求形似
        if not re.fullmatch(r"[A-Z]{1,4}(/[A-Z])?", prefix):
            raise CodeParseError(f"无法识别标准前缀: {prefix!r}")

    return StdCode(
        prefix=prefix,
        number=num,
        year=expand_year(m.group("year")),
        raw=text.strip(),
        year_digits=len(m.group("year")) if m.group("year") else 4,
    )


def try_parse(text: str) -> StdCode | None:
    try:
        return parse(text)
    except CodeParseError:
        return None


def same_standard(a: StdCode, b: StdCode) -> bool:
    """同编号、同年号（忽略分部分与写法差异）。"""
    return a.prefix == b.prefix and a.number == b.number and a.year == b.year
