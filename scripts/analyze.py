#!/usr/bin/env python3
"""현재까지의 Google Ads 캠페인 실적을 분석하고 진단 리포트를 생성합니다.

사용법:
    python3 scripts/analyze.py                 # data/raw 의 CSV를 모두 읽어 분석
    python3 scripts/analyze.py --dir data/raw --out reports/

data/raw 에 넣어야 할 파일은 data/raw/README.md 를 참고하세요.
파일명에 다음 단어가 포함되어 있으면 자동 인식됩니다.
    campaign / 캠페인, adgroup / 광고그룹, keyword / 키워드,
    searchterm / 검색어, ad / 광고
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import yaml  # noqa: E402

import adslib as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def load_all(directory: str) -> dict:
    """디렉터리의 CSV들을 리포트 종류별로 분류해 로드.

    종류는 파일명으로 먼저 판별하고, 알 수 없으면 컬럼 구성으로 판별합니다.
    (브라우저에서 막 내려받아 이름이 무의미한 파일도 처리하기 위함)
    """
    found = {k: [] for k in A.REPORT_KINDS}
    if not os.path.isdir(directory):
        return found
    for fname in sorted(os.listdir(directory)):
        if not fname.lower().endswith((".csv", ".tsv")):
            continue
        path = os.path.join(directory, fname)
        kind = A.classify_report(path)
        if kind is None:
            print(f"  [건너뜀] {fname} — 리포트 종류를 알 수 없습니다.")
            continue
        try:
            rows = A.load_report(path)
        except ValueError as exc:
            print(f"  [오류] {exc}")
            continue
        found[kind].extend(rows)
        print(f"  [읽음] {fname} → {A.KIND_PREFIX[kind]} ({len(rows)}행)")
    return found


def totals(rows: list[dict]) -> dict:
    t = {"impressions": 0.0, "clicks": 0.0, "cost": 0.0,
         "conversions": 0.0, "conv_value": 0.0}
    for r in rows:
        for k in t:
            t[k] += r.get(k, 0.0)
    return A.derive(t)


def summary_block(t: dict) -> str:
    return A.md_table(
        ["지표", "값"],
        [["비용", A.won(t["cost"])],
         ["노출수", A.num(t["impressions"])],
         ["클릭수", A.num(t["clicks"])],
         ["CTR", A.pct(t["ctr"])],
         ["평균 CPC", A.won(t["avg_cpc"])],
         ["전환수", A.num(t["conversions"])],
         ["전환율", A.pct(t["conv_rate"])],
         ["전환당 비용 (CPA)", A.won(t["cpa"]) if t["conversions"] else "전환 없음"],
         ["전환 가치", A.won(t["conv_value"])],
         ["ROAS (전환가치/비용)", f"{t['roas']:.2f}" if t["cost"] else "-"]],
        align_right={1},
    )


def perf_table(buckets: dict, label: str, limit: int = 30) -> str:
    rows = sorted(buckets.values(), key=lambda b: -b["cost"])[:limit]
    body = []
    for b in rows:
        body.append([
            b.get(label, "")[:40] or "(없음)",
            A.won(b["cost"]),
            A.num(b["impressions"]),
            A.num(b["clicks"]),
            A.pct(b["ctr"]),
            A.won(b["avg_cpc"]),
            A.num(b["conversions"]),
            A.won(b["cpa"]) if b["conversions"] else "—",
            f"{b['roas']:.2f}" if b["cost"] else "—",
        ])
    return A.md_table(
        [label, "비용", "노출", "클릭", "CTR", "CPC", "전환", "CPA", "ROAS"],
        body, align_right={1, 2, 3, 4, 5, 6, 7, 8})


def diagnose(t: dict, cfg: dict, campaigns: dict, keywords: list[dict]) -> list[str]:
    """숫자를 근거로 한 자동 진단 문장들."""
    tg = cfg["targets"]
    out = []

    if t["cost"] == 0:
        return ["- 비용 데이터가 0입니다. 리포트 기간과 파일을 확인하세요."]

    # 1) 전환 측정 자체가 되고 있는가
    if t["conversions"] == 0:
        out.append(
            "- **전환이 0건입니다.** 광고비는 집행됐는데 전환이 잡히지 않는다면 "
            "① 전환 추적이 설치되지 않았거나 ② 스마트스토어로 연결돼 태그를 심을 수 없는 "
            "구조일 가능성이 큽니다. `docs/measurement.md` 를 먼저 해결해야 "
            "이후 모든 최적화가 의미를 갖습니다.")
    elif t["conv_value"] == 0:
        out.append(
            "- **전환은 잡히는데 전환 가치가 0원입니다.** 가치 기반 입찰(타겟 ROAS, "
            "전환가치 극대화)을 쓸 수 없는 상태입니다. 전환별 매출액을 넘기거나, "
            "최소한 전환 액션에 고정 가치를 지정하세요.")
    else:
        cpa = t["cpa"]
        roas = t["roas"]
        goals = [p.get("target_cpa", 0) for p in cfg["products"].values()]
        avg_target_cpa = sum(goals) / len(goals) if goals else 0
        if avg_target_cpa and cpa > avg_target_cpa * 1.2:
            out.append(f"- **CPA {A.won(cpa)}** 로 목표({A.won(avg_target_cpa)}) 대비 "
                       f"{cpa / avg_target_cpa:.1f}배입니다. 입찰·키워드 정리가 필요합니다.")
        elif avg_target_cpa:
            out.append(f"- CPA {A.won(cpa)} 로 목표({A.won(avg_target_cpa)}) 이내입니다. "
                       f"예산 증액 여지가 있습니다.")
        out.append(f"- ROAS {roas:.2f} — 광고비 1원당 전환가치 {roas:.2f}원.")

    # 2) CTR
    if t["ctr"] < tg["ctr_floor"] and t["impressions"] >= tg["min_impressions_for_judgement"]:
        out.append(
            f"- **CTR {A.pct(t['ctr'])}** 로 기준선({A.pct(tg['ctr_floor'])}) 아래입니다. "
            "검색 캠페인에서 CTR이 낮다는 건 키워드-광고문안-랜딩의 일치도가 떨어진다는 "
            "신호입니다. 광고그룹을 주제별로 잘게 쪼개고 RSA 헤드라인에 키워드를 넣으세요.")

    # 3) 캠페인 간 편차
    if len(campaigns) >= 2:
        ranked = sorted(campaigns.values(), key=lambda b: -b["cost"])
        top, bottom = ranked[0], ranked[-1]
        if top["cost"] > 0 and bottom["cost"] > 0:
            if top["conversions"] and not bottom["conversions"]:
                out.append(
                    f"- **'{bottom['campaign']}'** 캠페인은 {A.won(bottom['cost'])} 를 쓰고 "
                    f"전환이 0건인 반면, **'{top['campaign']}'** 는 전환이 발생합니다. "
                    "예산을 성과 캠페인으로 옮기는 것이 1순위 조치입니다.")

    # 4) 낭비 키워드
    waste = [k for k in keywords
             if k.get("conversions", 0) == 0
             and k.get("clicks", 0) >= tg["wasted_spend_click_threshold"]]
    if waste:
        wasted_cost = sum(k["cost"] for k in waste)
        share = wasted_cost / t["cost"] if t["cost"] else 0
        out.append(
            f"- **낭비 지출 {A.won(wasted_cost)} ({A.pct(share)})** — 클릭 "
            f"{tg['wasted_spend_click_threshold']}회 이상 받고 전환이 0인 키워드가 "
            f"{len(waste)}개입니다. 즉시 일시중지 또는 입찰 하향 대상입니다.")

    # 5) 노출 점유율 손실
    lost_budget = [c for c in campaigns.values() if c.get("lost_is_budget", 0) > 0.1]
    if lost_budget:
        out.append("- 예산 부족으로 노출을 잃고 있는 캠페인이 있습니다 "
                   "(검색 손실 노출 점유율(예산) > 10%). 성과가 좋은 쪽이라면 증액하세요.")

    return out


def budget_recommendation(campaigns: dict, cfg: dict) -> str:
    """성과 기반 예산 재배분 권고."""
    if not campaigns:
        return "_캠페인 리포트가 없어 예산 권고를 생성하지 못했습니다._"
    total_cost = sum(c["cost"] for c in campaigns.values())
    if total_cost == 0:
        return "_비용이 0이라 예산 권고를 생성하지 못했습니다._"

    # 효율 점수: 전환가치 우선, 없으면 전환수, 그것도 없으면 CTR
    use_value = any(c["conv_value"] > 0 for c in campaigns.values())
    use_conv = any(c["conversions"] > 0 for c in campaigns.values())

    scored = []
    for c in campaigns.values():
        if use_value:
            score = c["conv_value"]
            basis = "전환가치"
        elif use_conv:
            score = c["conversions"]
            basis = "전환수"
        else:
            score = c["clicks"] * c["ctr"]
            basis = "CTR×클릭 (전환 데이터 없음 — 참고용)"
        scored.append((c, score, basis))

    total_score = sum(s for _, s, _ in scored)
    body = []
    for c, score, basis in sorted(scored, key=lambda x: -x[1]):
        cur_share = c["cost"] / total_cost
        rec_share = (score / total_score) if total_score else cur_share
        # 급격한 변동 방지: 현재 배분과 권고 배분을 7:3 이 아닌 4:6 으로 섞음
        blended = cur_share * 0.4 + rec_share * 0.6
        delta = blended - cur_share
        arrow = "▲ 증액" if delta > 0.03 else ("▼ 감액" if delta < -0.03 else "= 유지")
        body.append([c["campaign"][:36], A.pct(cur_share), A.pct(blended),
                     f"{arrow} ({delta * 100:+.1f}%p)"])
    basis = scored[0][2] if scored else ""
    table = A.md_table(["캠페인", "현재 비용 비중", "권고 비중", "조치"],
                       body, align_right={1, 2})
    return f"판단 기준: **{basis}**\n\n{table}"


def build_report(data: dict, cfg: dict) -> str:
    today = dt.date.today().isoformat()
    parts = [f"# 헬로팩토리 Google Ads 실적 진단 — {today}", ""]

    base = data["campaign"] or data["ad_group"] or data["keyword"]
    if not base:
        return ("# 분석할 데이터가 없습니다\n\n"
                "`data/raw/` 에 Google Ads 리포트 CSV를 넣고 다시 실행하세요. "
                "내보내는 방법은 `data/raw/README.md` 에 있습니다.\n")

    t = totals(base)
    parts += ["## 1. 계정 전체 요약", "", summary_block(t), ""]

    campaigns = A.aggregate(data["campaign"], "campaign") if data["campaign"] else {}
    if campaigns:
        parts += ["## 2. 캠페인별 성과", "", perf_table(campaigns, "campaign"), ""]

    if data["ad_group"]:
        ags = A.aggregate(data["ad_group"], "ad_group")
        parts += ["## 3. 광고그룹별 성과", "", perf_table(ags, "ad_group"), ""]

    kws = data["keyword"]
    if kws:
        agg = A.aggregate(kws, "keyword")
        winners = [b for b in agg.values() if b["conversions"] > 0]
        winners.sort(key=lambda b: -b["conversions"])
        losers = [b for b in agg.values()
                  if b["conversions"] == 0
                  and b["clicks"] >= cfg["targets"]["wasted_spend_click_threshold"]]
        losers.sort(key=lambda b: -b["cost"])
        parts += ["## 4. 키워드 성과", ""]
        if winners:
            parts += ["### 4-1. 전환이 발생한 키워드 (확장 대상)", "",
                      perf_table({i: w for i, w in enumerate(winners)}, "keyword", 25), ""]
        else:
            parts += ["### 4-1. 전환이 발생한 키워드", "",
                      "_전환이 발생한 키워드가 없습니다._", ""]
        if losers:
            wasted = sum(b["cost"] for b in losers)
            parts += [f"### 4-2. 낭비 키워드 (전환 0 · 클릭 "
                      f"{cfg['targets']['wasted_spend_click_threshold']}회 이상) — "
                      f"합계 {A.won(wasted)}", "",
                      perf_table({i: l for i, l in enumerate(losers)}, "keyword", 25), ""]

    parts += ["## 5. 진단", ""]
    parts += diagnose(t, cfg, campaigns, kws) or ["- 특이사항 없음"]
    parts += ["", "## 6. 예산 재배분 권고", "", budget_recommendation(campaigns, cfg), ""]

    parts += ["## 7. 다음 액션", "",
              "1. `docs/measurement.md` — 전환 추적부터 정상화 (이게 안 되면 아래는 무의미)",
              "2. `python3 scripts/search_terms.py` — 제외 키워드 후보 뽑아 즉시 적용",
              "3. `campaigns/structure.md` — 새 캠페인 구조로 재편",
              "4. `python3 scripts/make_editor_csv.py` — Google Ads Editor 업로드 파일 생성",
              "5. `docs/weekly_optimization.md` — 주간 루틴으로 지속 개선", ""]
    return "\n".join(parts)


def main() -> int:
    ap = argparse.ArgumentParser(description="Google Ads 실적 분석")
    ap.add_argument("--dir", default=os.path.join(ROOT, "data", "raw"))
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    ap.add_argument("--config", default=os.path.join(ROOT, "config", "products.yaml"))
    args = ap.parse_args()

    with open(args.config, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    print(f"리포트 디렉터리: {args.dir}")
    data = load_all(args.dir)
    report = build_report(data, cfg)
    if "sample" in os.path.abspath(args.dir).lower():
        report = ("> ⚠️ **주의: 이 리포트는 `data/sample/` 의 가짜 예시 데이터로 만들어졌습니다.**\n"
                  "> 실제 계정 숫자가 아닙니다. `data/raw/` 에 실제 리포트를 넣고 다시 실행하세요.\n\n"
                  + report)

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"analysis_{dt.date.today().isoformat()}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report)
    print(f"\n생성됨: {path}\n")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
