from datetime import date

from stdradar.codes import parse
from stdradar.openstd import best_match, parse_rows
from stdradar.verdict import Status

# 依真实页面结构精简：9 列，第 2 列是带 showInfo 链接的标准号
PAGE = """
<table class="td_list">
<tr><th>序号</th><th>标准号</th><th></th><th></th><th>标准名称</th>
    <th>标准性质</th><th>状态</th><th>发布日期</th><th>实施日期</th></tr>
<tr>
  <td>1</td>
  <td><a href="javascript:showInfo('A1B2C3D4E5F60718293A4B5C6D7E8F90');">GB 38383-2019</a></td>
  <td></td><td></td>
  <td>洗碗机能效限定值及能效等级</td>
  <td>国家标准</td><td>现行</td>
  <td>2019-09-01 00:00:00.0</td><td>2020-05-01 00:00:00.0</td>
</tr>
<tr>
  <td>2</td>
  <td><a href="javascript:showInfo('B1B2C3D4E5F60718293A4B5C6D7E8F90');">GB/T 18920-2026</a></td>
  <td></td><td></td>
  <td>城市污水再生利用 城市杂用水水质</td>
  <td>推荐性国家标准</td><td>即将实施</td>
  <td>2026-05-25 00:00:00.0</td><td>2026-12-01 00:00:00.0</td>
</tr>
</table>
"""


def test_parse_rows():
    rows = parse_rows(PAGE)
    assert len(rows) == 2
    a, b = rows
    assert a.code.canonical == "GB 38383-2019"
    assert a.status is Status.IN_FORCE
    assert a.implement_date == date(2020, 5, 1)
    assert a.name.startswith("洗碗机")
    assert b.status is Status.PENDING
    assert b.publish_date == date(2026, 5, 25)


def test_table_without_results():
    assert parse_rows("<table><tr><td>没有查询到数据</td></tr></table>") == []


def test_best_match_ignores_neighbour():
    rows = parse_rows(PAGE)
    # 查 GB 3838，平台因模糊检索返回了 GB 38383
    assert best_match(parse("GB 3838-2002"), rows) is None
    # 查 GB/T 18920 则能命中
    m = best_match(parse("GB/T 18920-2005"), rows)
    assert m is not None and m.code.canonical == "GB/T 18920-2026"


def test_best_match_picks_newest():
    rows = parse_rows("""
    <table>
    <tr><td>1</td><td>GB 50014-2006</td><td></td><td></td><td>A</td>
        <td>国家标准</td><td>废止</td><td>2006-01-01</td><td>2006-06-01</td></tr>
    <tr><td>2</td><td>GB 50014-2021</td><td></td><td></td><td>B</td>
        <td>国家标准</td><td>现行</td><td>2021-05-01</td><td>2022-01-01</td></tr>
    </table>""")
    m = best_match(parse("GB 50014-2006"), rows)
    assert m is not None and m.code.year == 2021
