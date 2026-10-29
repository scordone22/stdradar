"""版本判定：给定「库里有什么」和「官方最新是什么」，给出唯一处置动作。

判定逻辑不是靠年号大小拍脑袋，而是年号 + 官方状态 + 实施日期三者合成。
全部规则来自实际踩坑，每条都对应一个真实误判:

1. 模糊检索噪声 —— 搜 GB 3838 返回 GB 38383，若取首行当最新版，会凭空
   造出「库内件过时」的假警报。必须按完整主号精确过滤。
2. 分部分标准 —— GB 16171.1-2024 与 GB 16171-2012 并存且均现行，
   编号前缀相同不等于替代关系。
3. 查不到 ≠ 废止 —— 工程建设标准(GB 50xxx/51xxx/55xxx)与行业标准
   (HJ/CJ/CJJ/SL) 在国家标准全文公开系统里一律查不到。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .codes import StdCode


class Status(str, Enum):
    """官方平台的状态字段取值。"""

    IN_FORCE = "现行"
    PENDING = "即将实施"  # 已发布、未实施
    ABOLISHED = "废止"

    @classmethod
    def parse(cls, text: str) -> "Status | None":
        t = (text or "").strip()
        for s in cls:
            if s.value in t:
                return s
        return None


class Verdict(str, Enum):
    CURRENT = "current"                    # 现行最新，不动
    OUTDATED = "outdated"                  # 新版已实施，旧版应归档
    TRANSITION = "transition"              # 新版已发布未实施，新旧并行
    ABOLISHED = "abolished"                # 同版年号但官方已废止，无替代
    PART_PARALLEL = "part_parallel"        # 分部分标准与主标准并存
    UNKNOWN = "unknown"                    # 未命中，不可据此判废止
    INCONSISTENT = "inconsistent"          # 库内年号高于官方，多半是查错了
    MISMATCH = "mismatch"                  # 编号不一致，疑似模糊检索噪声
    INCOMPLETE = "incomplete"              # 库内条目缺年号，无法比较新旧


@dataclass
class Latest:
    """官方平台的查询结果。"""

    code: StdCode
    status: Status
    publish_date: date | None = None
    implement_date: date | None = None
    replaces: list[StdCode] = field(default_factory=list)
    name: str = ""
    source: str = "openstd.samr.gov.cn"


@dataclass
class Judgment:
    local: StdCode
    latest: Latest | None
    verdict: Verdict
    reason: str
    action: str
    deadline: date | None = None

    @property
    def needs_work(self) -> bool:
        return self.verdict in {
            Verdict.OUTDATED,
            Verdict.TRANSITION,
            Verdict.ABOLISHED,
            Verdict.INCONSISTENT,
        }


_ACTION = {
    Verdict.CURRENT: "保持现状，无需处理。",
    Verdict.OUTDATED: "旧版移入「已废止版本」目录并注明取代依据；新版归档到现行目录。",
    Verdict.TRANSITION: "旧版暂留现行目录；新版并行入库并标「过渡期」；到期日后再归档旧版。",
    Verdict.ABOLISHED: "移入「已废止版本」目录，注明「复审废止，无替代版本」。",
    Verdict.PART_PARALLEL: "两件并存，均按现行管理；替代关系需查详情页「全部代替」字段确认。",
    Verdict.UNKNOWN: "不改变现状。换数据源复核（住建部/生态环境部），不得判为废止。",
    Verdict.INCONSISTENT: "库内年号高于官方返回结果，先核对是否查到同号其它标准。",
    Verdict.MISMATCH: "编号不一致，丢弃此条结果，按完整主号重新精确检索。",
    Verdict.INCOMPLETE: "补全库内条目的年号后重新判定；缺年号时不要比对新旧。",
}


def judge(local: StdCode, latest: Latest | None, today: date | None = None) -> Judgment:
    """核心判定。`today` 可注入，便于测试与回溯历史时点。"""
    today = today or date.today()

    if latest is None:
        return Judgment(local, None, Verdict.UNKNOWN,
                        "官方渠道未返回该编号（行业标准/工程建设标准不在公开系统收录范围）",
                        _ACTION[Verdict.UNKNOWN])

    new = latest.code

    # 陷阱 1：编号必须完全同族，否则是模糊检索捞出来的邻号
    if local.family != new.family:
        return Judgment(local, latest, Verdict.MISMATCH,
                        f"主号不一致：库内 {local.family} vs 检索结果 {new.family}",
                        _ACTION[Verdict.MISMATCH])

    # 陷阱 2：一边带分部分号、一边不带 —— 并存关系，不是替代关系
    if bool(local.part) != bool(new.part):
        return Judgment(local, latest, Verdict.PART_PARALLEL,
                        f"{new.canonical} 属分部分标准，与主标准 {local.family} 并存",
                        _ACTION[Verdict.PART_PARALLEL])

    ly, ny = local.year, new.year
    if ly is None:
        # 没有年号就没有「新旧」可言。此处若默认取「更旧」分支，
        # 会把一批有效标准误标为过期——宁可报信息不全。
        return Judgment(local, latest, Verdict.INCOMPLETE,
                        f"库内条目未标年号；官方最新为 {new.canonical}（{latest.status.value}）",
                        _ACTION[Verdict.INCOMPLETE])
    if ny and ly > ny:
        return Judgment(local, latest, Verdict.INCONSISTENT,
                        f"库内年号 {ly} 晚于官方最新 {ny}",
                        _ACTION[Verdict.INCONSISTENT])

    if ny is None:
        return Judgment(local, latest, Verdict.INCOMPLETE,
                        f"检索结果未带年号（{new.canonical}），无法比对新旧",
                        _ACTION[Verdict.INCOMPLETE])

    if ly == ny:
        if latest.status is Status.ABOLISHED:
            return Judgment(local, latest, Verdict.ABOLISHED,
                            f"{new.canonical} 官方状态为废止（复审废止，无替代版本）",
                            _ACTION[Verdict.ABOLISHED])
        return Judgment(local, latest, Verdict.CURRENT,
                        f"库内即最新版 {new.canonical}，状态{latest.status.value}",
                        _ACTION[Verdict.CURRENT])

    # 库内年号更旧：能否归档，只看新版的实施日期
    if latest.status is Status.PENDING or (latest.implement_date and latest.implement_date > today):
        dl = latest.implement_date
        note = f"新版 {new.canonical} 将于 {dl} 实施" if dl else "新版尚未实施"
        return Judgment(local, latest, Verdict.TRANSITION,
                        f"{note}，其实施前旧版 {local.canonical} 仍具完全效力",
                        _ACTION[Verdict.TRANSITION], deadline=dl)

    return Judgment(local, latest, Verdict.OUTDATED,
                    f"新版 {new.canonical} 已实施"
                    + (f"（{latest.implement_date}）" if latest.implement_date else ""),
                    _ACTION[Verdict.OUTDATED])


def replacement_evidenced(local: StdCode, latest: Latest) -> bool:
    """替代关系是否有据可查。

    年号递增不等于替代：GB 50014-2006 被 GB 50014-2021 替代是明写在公告里的，
    而 GB 18918 出 2026 修订版时也可能只是新增而非替代旧版。判替代只能看
    公告 / 详情页「全部代替标准」字段，不能看编号。
    """
    return any(local.family == r.family and local.year == r.year for r in latest.replaces)


@dataclass
class Plan:
    judgments: list[Judgment]

    def of(self, *verdicts: Verdict) -> list[Judgment]:
        return [j for j in self.judgments if j.verdict in verdicts]

    def counts(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for j in self.judgments:
            out[j.verdict.value] = out.get(j.verdict.value, 0) + 1
        return out


def build_plan(pairs: list[tuple[StdCode, Latest | None]], today: date | None = None) -> Plan:
    return Plan([judge(c, l, today) for c, l in pairs])
