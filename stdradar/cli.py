"""命令行入口。"""

from __future__ import annotations

import argparse
import csv
import sys
from datetime import date, datetime

from .codes import CodeParseError, parse
from .openstd import best_match, query
from .verdict import Latest, Status, Verdict, build_plan, judge

VERDICT_MARK = {
    Verdict.CURRENT: "OK",
    Verdict.OUTDATED: "过期",
    Verdict.TRANSITION: "过渡",
    Verdict.ABOLISHED: "废止",
    Verdict.PART_PARALLEL: "并存",
    Verdict.UNKNOWN: "未知",
    Verdict.INCONSISTENT: "异常",
    Verdict.MISMATCH: "不匹配",
    Verdict.INCOMPLETE: "缺年号",
}


def _d(s: str | None) -> date | None:
    if not s:
        return None
    return datetime.strptime(s.strip(), "%Y-%m-%d").date()


def cmd_normalize(args) -> int:
    for raw in args.codes:
        try:
            c = parse(raw)
        except CodeParseError as e:
            print(f"{raw!r:32}  ->  ERR  {e}")
            continue
        part = f"  分部分={c.part}" if c.part else ""
        print(f"{raw!r:32}  ->  {c.canonical:<20} 家族={c.family}{part}")
    return 0


def cmd_judge(args) -> int:
    local = parse(args.local)
    latest = None
    if args.latest:
        latest = Latest(
            code=parse(args.latest),
            status=Status.parse(args.status or "现行") or Status.IN_FORCE,
            implement_date=_d(args.implement),
            publish_date=_d(args.publish),
        )
    j = judge(local, latest, _d(args.today))
    print(f"库内  : {local.canonical}")
    print(f"官方  : {latest.code.canonical if latest else '未提供'}")
    print(f"判定  : {VERDICT_MARK[j.verdict]}  ({j.verdict.value})")
    print(f"依据  : {j.reason}")
    print(f"处置  : {j.action}")
    if j.deadline:
        print(f"到期  : {j.deadline}")
    return 0


def cmd_query(args) -> int:
    code = parse(args.code)
    results = query(code, timeout=args.timeout, want_pages=args.pages)
    if not results:
        print("官方未返回结果。注意：工程建设标准(GB 50xxx/55xxx)与行业标准"
              "(HJ/CJ/CJJ/SL)不在该平台收录范围，查不到不代表废止。")
        return 0
    print(f"{'标准号':<24}{'状态':<10}{'实施日期':<14}名称")
    for r in results:
        name = getattr(r, "name", "")
        print(f"{r.code.canonical:<24}{r.status.value:<10}"
              f"{(str(r.implement_date) if r.implement_date else '-'):<14}{name}")
    match = best_match(code, results)
    if match:
        j = judge(code, match)
        print(f"\n-> 判定 {VERDICT_MARK[j.verdict]}：{j.reason}")
    return 0


def cmd_check(args) -> int:
    """批量体检。CSV 列：code,latest,status,implement_date"""
    with open(args.csv, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    pairs = []
    for r in rows:
        local = parse(r["code"])
        latest = None
        if r.get("latest"):
            latest = Latest(
                code=parse(r["latest"]),
                status=Status.parse(r.get("status") or "现行") or Status.IN_FORCE,
                implement_date=_d(r.get("implement_date")),
            )
        pairs.append((local, latest))

    plan = build_plan(pairs, _d(args.today))
    print("| 库内版本 | 官方版本 | 判定 | 依据 |")
    print("|---|---|---|---|")
    for j in plan.judgments:
        print(f"| {j.local.canonical} | "
              f"{j.latest.code.canonical if j.latest else '-'} | "
              f"{VERDICT_MARK[j.verdict]} | {j.reason} |")
    print()
    for k, v in sorted(plan.counts().items(), key=lambda kv: -kv[1]):
        print(f"  {k:<12}{v}")
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("| 库内版本 | 官方版本 | 判定 | 依据 | 处置 |\n|---|---|---|---|---|\n")
            for j in plan.judgments:
                f.write(f"| {j.local.canonical} | "
                        f"{j.latest.code.canonical if j.latest else '-'} | "
                        f"{VERDICT_MARK[j.verdict]} | {j.reason} | {j.action} |\n")
        print(f"\n报告已写入 {args.out}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="stdradar",
        description="中国标准版本体检：判定库里每一件是现行、过期、过渡还是废止。",
    )
    p.add_argument("--version", action="version", version="stdradar 0.1.0")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("normalize", help="归一标准号写法")
    s.add_argument("codes", nargs="+")
    s.set_defaults(func=cmd_normalize)

    s = sub.add_parser("judge", help="单件判定")
    s.add_argument("local", help="库内版本，如 'GB 50014-2006'")
    s.add_argument("--latest", help="官方最新版本号")
    s.add_argument("--status", help="现行 / 即将实施 / 废止")
    s.add_argument("--publish", help="发布日期 YYYY-MM-DD")
    s.add_argument("--implement", help="实施日期 YYYY-MM-DD")
    s.add_argument("--today", help="以指定日期为判定基准，便于回溯核查")
    s.set_defaults(func=cmd_judge)

    s = sub.add_parser("query", help="联网查询官方平台")
    s.add_argument("code")
    s.add_argument("--pages", type=int, default=1)
    s.add_argument("--timeout", type=float, default=20.0)
    s.set_defaults(func=cmd_query)

    s = sub.add_parser("check", help="批量体检 CSV")
    s.add_argument("csv")
    s.add_argument("--out", help="输出 Markdown 报告路径")
    s.add_argument("--today")
    s.set_defaults(func=cmd_check)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CodeParseError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
