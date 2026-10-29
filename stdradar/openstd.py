"""国家标准全文公开系统的查询与结果解析。

设计原则：
- 解析函数是纯函数，可离线用 HTML 快照测试，不依赖网络。
- 抓取函数限速、限页、带 UA，默认单次查询，不做批量扫站。
- 站点结构随时可能变，解析按「单元格内容语义」识别，不绑定列序号，
  这样官方调整列顺序时不会整体失效。
"""

from __future__ import annotations

import html as htmllib
import re
import time
import urllib.parse
import urllib.request
from datetime import date

from .codes import StdCode, try_parse
from .verdict import Latest, Status

BASE = "https://openstd.samr.gov.cn/bzgk/gb/std_list"
# HTTP 头只能 latin-1 编码，中文会直接抛 UnicodeEncodeError，别往里放汉字
USER_AGENT = "Mozilla/5.0 (compatible; stdradar/0.1; +https://github.com/scordone22/stdradar)"

_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")
_DATE_RE = re.compile(r"(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})")


def _text(fragment: str) -> str:
    return htmllib.unescape(_TAG_RE.sub("", fragment)).replace("\xa0", " ").strip()


def _date(cell: str) -> date | None:
    m = _DATE_RE.search(cell)
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def parse_rows(page: str) -> list[Latest]:
    """从 std_list 结果页解析出标准记录。"""
    out: list[Latest] = []
    for tr in _TR_RE.findall(page):
        cells = [_text(td) for td in _TD_RE.findall(tr)]
        if len(cells) < 4:
            continue

        code: StdCode | None = None
        for c in cells:
            code = try_parse(c)
            if code is not None:
                break
        if code is None:
            continue

        status = None
        for c in cells:
            status = Status.parse(c)
            if status is not None:
                break
        if status is None:
            continue

        dates = [d for d in (_date(c) for c in cells) if d is not None]
        # 名称：排除编号/状态/日期后最长的一段
        names = [c for c in cells if c
                 and try_parse(c) is None
                 and Status.parse(c) is None
                 and _date(c) is None]
        name = max(names, key=len) if names else ""

        publish = dates[0] if dates else None
        implement = dates[1] if len(dates) > 1 else None
        out.append(Latest(code=code, status=status, publish_date=publish,
                          implement_date=implement, name=name))
    return out


def query(code: StdCode | str, *, timeout: float = 20.0, sleep: float = 0.3,
          want_pages: int = 1) -> list[Latest]:
    """按标准号查询官方平台。

    官方是模糊检索，返回结果里必然混入邻号；调用方应使用 verdict.judge
    做家族校验，不要直接取首行。
    """
    key = code.canonical if isinstance(code, StdCode) else str(code)
    results: list[Latest] = []
    for page in range(1, max(1, want_pages) + 1):
        params = {
            "p.p1": "0",
            "p.p90": "circulation_date",
            "p.p91": "desc",
            "p.p2": key,
        }
        if page > 1:
            params["page"] = str(page)
        url = BASE + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "zh-CN,zh;q=0.9",
        })
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = r.read().decode("utf-8", "ignore")
        results.extend(parse_rows(body))
        if page < want_pages:
            time.sleep(max(0.25, sleep))
    return results


def best_match(code: StdCode, results: list[Latest]) -> Latest | None:
    """在同族同号的结果里取年号最大的一条，没有则返回 None。"""
    fam = [r for r in results
           if r.code.family == code.family and bool(r.code.part) == bool(code.part)]
    if not fam:
        return None
    return max(fam, key=lambda r: r.code.year or 0)
