from datetime import date

from stdradar.codes import parse
from stdradar.verdict import (
    Latest,
    Status,
    Verdict,
    build_plan,
    judge,
    replacement_evidenced,
)

TODAY = date(2026, 10, 29)


def latest(code, status, imp=None, pub=None, replaces=None):
    return Latest(
        code=parse(code),
        status=Status.parse(status),
        publish_date=pub,
        implement_date=imp,
        replaces=[parse(r) for r in (replaces or [])],
    )


def test_current():
    j = judge(parse("GB 50014-2021"),
              latest("GB 50014-2021", "现行", date(2022, 1, 1)), TODAY)
    assert j.verdict is Verdict.CURRENT
    assert not j.needs_work


def test_outdated_when_new_version_implemented():
    j = judge(parse("GB 50014-2006"),
              latest("GB 50014-2021", "现行", date(2022, 1, 1)), TODAY)
    assert j.verdict is Verdict.OUTDATED
    assert j.needs_work


def test_transition_when_not_yet_implemented():
    # 新版已发布、2026-12-01 才实施 —— 旧版此刻仍有完全效力，不能归档
    j = judge(parse("GB/T 18920-2005"),
              latest("GB/T 18920-2026", "即将实施",
                     imp=date(2026, 12, 1), pub=date(2026, 5, 25)), TODAY)
    assert j.verdict is Verdict.TRANSITION
    assert j.deadline == date(2026, 12, 1)


def test_transition_by_date_even_if_status_stale():
    # 状态字段可能滞后；实施日期才是硬判据
    j = judge(parse("GB/T 18920-2005"),
              latest("GB/T 18920-2026", "现行", imp=date(2026, 12, 1)), TODAY)
    assert j.verdict is Verdict.TRANSITION


def test_abolished_same_year():
    j = judge(parse("GB 50335-2002"),
              latest("GB 50335-2002", "废止"), TODAY)
    assert j.verdict is Verdict.ABOLISHED


def test_fuzzy_neighbour_is_not_an_alarm():
    # 陷阱 1：搜 GB 3838 会返回 GB 38383（洗碗机能效），绝不能当成新版
    j = judge(parse("GB 3838-2002"),
              latest("GB 38383-2019", "现行"), TODAY)
    assert j.verdict is Verdict.MISMATCH
    assert not j.needs_work


def test_part_standard_coexists():
    # 陷阱 2：GB 16171.1-2024 与 GB 16171-2012 并存，均现行
    j = judge(parse("GB 16171-2012"),
              latest("GB 16171.1-2024", "现行", date(2025, 5, 1)), TODAY)
    assert j.verdict is Verdict.PART_PARALLEL
    assert not j.needs_work


def test_same_part_still_compared_by_year():
    j = judge(parse("GB 16171.1-2012"),
              latest("GB 16171.1-2024", "现行", date(2025, 5, 1)), TODAY)
    assert j.verdict is Verdict.OUTDATED


def test_not_found_never_means_abolished():
    # 陷阱 3：工程建设标准与行业标准不在公开系统收录范围
    j = judge(parse("GB 50014-2006"), None, TODAY)
    assert j.verdict is Verdict.UNKNOWN
    assert not j.needs_work


def test_library_ahead_of_platform():
    j = judge(parse("GB 50014-2021"),
              latest("GB 50014-2006", "废止"), TODAY)
    assert j.verdict is Verdict.INCONSISTENT


def test_missing_year_is_not_outdated():
    # 只给主号不给年号时，绝不能默认「库内更旧」——那会把有效标准误标为过期
    j = judge(parse("GB 3838"), latest("GB 3838-2002", "现行", date(2002, 6, 1)), TODAY)
    assert j.verdict is Verdict.INCOMPLETE
    assert not j.needs_work
    assert "GB 3838-2002" in j.reason


def test_replacement_must_be_evidenced():
    new = latest("GB 50014-2021", "现行", date(2022, 1, 1),
                 replaces=["GB 50014-2006"])
    assert replacement_evidenced(parse("GB 50014-2006"), new)
    assert not replacement_evidenced(parse("GB 50014-1992"), new)
    # 编号递增但没有公告依据 —— 不能断言替代
    assert not replacement_evidenced(
        parse("GB 16171-2012"), latest("GB 16171-2024", "现行"))


def test_plan_counts():
    plan = build_plan([
        (parse("GB 50014-2006"), latest("GB 50014-2021", "现行", date(2022, 1, 1))),
        (parse("GB 50014-2021"), latest("GB 50014-2021", "现行", date(2022, 1, 1))),
        (parse("GB 50015-2019"), None),
    ], TODAY)
    c = plan.counts()
    assert c["outdated"] == 1 and c["current"] == 1 and c["unknown"] == 1
