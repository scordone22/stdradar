"""标准库版本体检：判定、核查与批处理。

开源核心只做「判定」这一件事，不做条文库与审查规则包。
"""

__version__ = "0.1.0"

from .codes import CodeParseError, StdCode, parse, try_parse  # noqa: F401
from .verdict import (  # noqa: F401
    Judgment,
    Latest,
    Plan,
    Status,
    Verdict,
    build_plan,
    judge,
    replacement_evidenced,
)
