#!/usr/bin/env python3
"""월별 추이를 분석합니다 — "초기에 비용만 오르지 않았나"를 확인하는 용도.

전제: 리포트를 내려받을 때 **세그먼트 → 시간 → 월** 을 적용해야 합니다.
세그먼트 없이 받은 리포트는 기간이 '전체'로 합산되어 추이를 볼 수 없습니다.

사용법:
    python3 scripts/trend.py
    python3 scripts/trend.py --since 2024-09          # 최근 2년만
    python3 scripts/trend.py --split 6                # 초기/최근 6개월 비교
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adslib as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_periodic(directory: str) -> tuple[list[dict], str | None]:
    """기간 컬럼이 있는 리포트 중 가장 상위 단위(캠페인)를 골라 로드."""
    best, best_kind = [], None
    priority = ["campaign", "ad_group", "keyword", "search_term"]
    found: dict[str, list[dict]] = {}
    if not os.path.isdir(directory):
        return best, best_kind
    for fname in sorted(os.listdir(directory)):
        if not fname.lower().endswith((".csv", ".tsv")):
            continue
        path = os.path.join(directory, fname)
        kind = A.classify_report(path)
        if kind not in priority:
            continue
        try:
            rows = A.load_report(path)
        except ValueError:
            continue
        if not A.has_period(rows):
            continue
        found.setdefault(kind, []).extend(rows)
        print(f"  [읽음] {fname} → {A.KIND_PREFIX[kind]} ({len(rows)}행, 기간 있음)")
    for kind in priority:
        if found.get(kind):
            return found[kind], kind
    return best, best_kind


def bar(value: float, peak: float, width: int = 24) -> str:
    if peak <= 0:
        return ""
    n = max(1, round(value / peak * width)) if value > 0 else 0
    return "█" * n


def monthly(rows: list[dict]) -> dict:
    buckets: dict[str, dict] = {}
    for r in rows:
        p = A.row_period(r)
        if not p:
            continue
        b = buckets.setdefault(p, {"impressions": 0.0, "clicks": 0.0,
                                   "cost": 0.0, "conversions": 0.0,
                                   "conv_value": 0.0})
        for k in b:
            b[k] += r.get(k, 0.0)
    for b in buckets.values():
        A.derive(b)
    return dict(sorted(buckets.items()))


def summarize(months: dict, keys: list[str]) -> dict:
    t = {"impressions": 0.0, "clicks": 0.0, "cost": 0.0,
         "conversions": 0.0, "conv_value": 0.0}
    for k in keys:
        for m in t:
            t[m] += months[k][m]
    t["months"] = len(keys)
    return A.derive(t)


def delta(new: float, old: float) -> str:
    if old == 0:
        return "신규" if new else "—"
    pct = (new - old) / old * 100
    return f"{pct:+.0f}%"


def build(rows: list[dict], kind: str, split: int,
          since: str | None, until: str | None) -> str:
    rows = A.filter_period(rows, since, until)
    months = monthly(rows)
    if not months:
        return ""

    peak_cost = max(m["cost"] for m in months.values())
    peak_conv = max(m["conversions"] for m in months.values())
    keys = list(months)

    parts = [f"# 월별 추이 — {keys[0]} ~ {keys[-1]} ({len(keys)}개월)", "",
             f"기준 리포트: {A.KIND_PREFIX[kind]}", "",
             "## 1. 월별 실적", ""]
    body = []
    for k in keys:
        m = months[k]
        body.append([k, A.won(m["cost"]), A.num(m["clicks"]), A.pct(m["ctr"]),
                     A.won(m["avg_cpc"]), A.num(m["conversions"]),
                     A.won(m["cpa"]) if m["conversions"] else "—",
                     f"{m['roas']:.2f}" if m["cost"] else "—"])
    parts.append(A.md_table(
        ["월", "비용", "클릭", "CTR", "CPC", "전환", "CPA", "ROAS"],
        body, align_right={1, 2, 3, 4, 5, 6, 7}))
    parts += ["", "## 2. 비용 대비 전환 (막대: 왼쪽 비용 / 오른쪽 전환)", "",
              "```"]
    for k in keys:
        m = months[k]
        parts.append(f"{k}  {bar(m['cost'], peak_cost):24s} {m['cost']:>9,.0f}원  "
                     f"| {bar(m['conversions'], peak_conv, 14):14s} "
                     f"{m['conversions']:>7,.0f}건")
    parts += ["```", ""]

    # 초기 vs 최근 비교
    if len(keys) >= split * 2:
        early_keys, late_keys = keys[:split], keys[-split:]
        early, late = summarize(months, early_keys), summarize(months, late_keys)
        parts += [f"## 3. 초기 {split}개월 vs 최근 {split}개월", ""]
        rowsx = []
        for label, key, fmt in [
            ("비용", "cost", A.won), ("클릭", "clicks", A.num),
            ("CTR", "ctr", A.pct), ("평균 CPC", "avg_cpc", A.won),
            ("전환", "conversions", A.num),
            ("CPA", "cpa", lambda v: A.won(v) if v else "—"),
            ("전환가치", "conv_value", A.won),
            ("ROAS", "roas", lambda v: f"{v:.2f}"),
        ]:
            rowsx.append([label, fmt(early[key]), fmt(late[key]),
                          delta(late[key], early[key])])
        parts.append(A.md_table(
            [f"지표", f"초기 ({early_keys[0]}~{early_keys[-1]})",
             f"최근 ({late_keys[0]}~{late_keys[-1]})", "변화"],
            rowsx, align_right={1, 2, 3}))
        parts += ["", "### 판정", ""]
        cost_up = late["cost"] > early["cost"] * 1.1
        conv_up = late["conversions"] > early["conversions"] * 1.1
        cpa_worse = (early["cpa"] and late["cpa"] and
                     late["cpa"] > early["cpa"] * 1.1)
        if cost_up and not conv_up:
            parts.append("- **비용은 늘었는데 전환은 그만큼 늘지 않았습니다.** "
                         "예산 증액이 성과로 이어지지 않은 구간입니다.")
        elif not cost_up and conv_up:
            parts.append("- 비용은 비슷하거나 줄었는데 전환은 늘었습니다. "
                         "효율이 개선된 구간입니다.")
        elif cost_up and conv_up:
            parts.append("- 비용과 전환이 함께 늘었습니다. CPA 변화를 함께 보세요.")
        if cpa_worse:
            parts.append(f"- **CPA가 {delta(late['cpa'], early['cpa'])} 나빠졌습니다.** "
                         f"({A.won(early['cpa'])} → {A.won(late['cpa'])})")
        elif early["cpa"] and late["cpa"]:
            parts.append(f"- CPA {A.won(early['cpa'])} → {A.won(late['cpa'])} "
                         f"({delta(late['cpa'], early['cpa'])})")
        parts.append("")

    # 최악·최선의 달
    worst = max((m for m in months.values() if m["cost"] > 0),
                key=lambda m: m["cpa"] if m["conversions"] else float("inf"),
                default=None)
    parts += ["## 4. 눈에 띄는 달", ""]
    no_conv = [k for k in keys
               if months[k]["cost"] > 0 and months[k]["conversions"] == 0]
    if no_conv:
        wasted = sum(months[k]["cost"] for k in no_conv)
        parts.append(f"- **전환이 0건인 달이 {len(no_conv)}개월** "
                     f"({', '.join(no_conv)}) — 합계 {A.won(wasted)}")
    best = min((months[k] for k in keys if months[k]["conversions"] > 0),
               key=lambda m: m["cpa"], default=None)
    if best:
        bk = [k for k in keys if months[k] is best][0]
        parts.append(f"- 가장 효율이 좋았던 달: **{bk}** "
                     f"— CPA {A.won(best['cpa'])}, 전환 {A.num(best['conversions'])}건")
    if worst and worst["conversions"]:
        wk = [k for k in keys if months[k] is worst][0]
        parts.append(f"- 가장 나빴던 달: **{wk}** — CPA {A.won(worst['cpa'])}")
    parts.append("")
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="월별 추이 분석")
    ap.add_argument("--dir", default=os.path.join(ROOT, "data", "raw"))
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    ap.add_argument("--since", help="시작 월 YYYY-MM (예: 2024-09)")
    ap.add_argument("--until", help="종료 월 YYYY-MM")
    ap.add_argument("--split", type=int, default=6,
                    help="초기/최근 비교에 쓸 개월 수 (기본 6)")
    args = ap.parse_args()

    print(f"리포트 디렉터리: {args.dir}")
    rows, kind = load_periodic(args.dir)
    if not rows:
        print("\n기간(일/주/월) 컬럼이 있는 리포트를 찾지 못했습니다.\n"
              "Google Ads 에서 리포트를 내려받을 때 화면 위쪽 **세그먼트 → 시간 →\n"
              "월** 을 먼저 적용하세요. 세그먼트 없이 받으면 기간이 '전체'로\n"
              "합산되어 추이를 볼 수 없습니다.\n"
              "자세한 절차는 docs/browser_download.md 를 참고하세요.")
        return 1

    report = build(rows, kind, args.split, args.since, args.until)
    if not report:
        print("해당 기간에 데이터가 없습니다.")
        return 1

    os.makedirs(args.out, exist_ok=True)
    tag = f"{args.since or 'all'}_{args.until or 'now'}".replace("-", "")
    path = os.path.join(args.out, f"trend_{dt.date.today().isoformat()}_{tag}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\n생성됨: {path}\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
