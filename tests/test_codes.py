import pytest

from stdradar.codes import CodeParseError, parse, same_standard


@pytest.mark.parametrize("raw,expect", [
    ("GB 50014-2021", "GB 50014-2021"),
    ("GB50014—2021", "GB 50014-2021"),          # 破折号 + 无空格
    ("gb 50014 - 2021", "GB 50014-2021"),        # 小写 + 多余空格
    ("ＧＢ　５００１４－２０２１", "GB 50014-2021"),   # 全角
    ("GB/T 50050-2017", "GB/T 50050-2017"),
    ("GB／T50050－2017", "GB/T 50050-2017"),     # 全角斜杠
    ("HJ 2044－2014", "HJ 2044-2014"),
    ("GB 18918-2002", "GB 18918-2002"),
    ("GB 16171.1-2024", "GB 16171.1-2024"),
    ("CJJ 60-2011", "CJJ 60-2011"),
])
def test_normalize(raw, expect):
    assert parse(raw).canonical == expect


def test_two_digit_year():
    # GBJ 14-87 指 1987 年，不是 2087；显示保留两位年号的官方写法
    assert parse("GBJ 14-87").year == 1987
    assert parse("GBJ 14-87").canonical == "GBJ 14-87"
    assert parse("GB 50014-01").year == 2001
    assert parse("GB 50014-01").canonical == "GB 50014-01"


def test_part_standard():
    c = parse("GB 16171.1-2024")
    assert c.part == "1"
    assert c.base_number == "16171"
    assert c.family == "GB 16171"


def test_prefix_not_confused():
    assert parse("GB/T 50050-2017").prefix == "GB/T"
    assert parse("GB 50050-2017").prefix == "GB"
    assert not same_standard(parse("GB/T 50050-2017"), parse("GB 50050-2017"))


def test_family_excludes_year():
    assert parse("GB 50014-2006").family == parse("GB 50014-2021").family


@pytest.mark.parametrize("bad", ["", "  ", "50014-2021", "GB", "污水处理标准"])
def test_reject_garbage(bad):
    with pytest.raises(CodeParseError):
        parse(bad)
