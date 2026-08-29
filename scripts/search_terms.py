#!/usr/bin/env python3
"""검색어 리포트를 분석해 제외 키워드 후보와 신규 키워드 후보를 뽑습니다.

사용법:
    python3 scripts/search_terms.py
    python3 scripts/search_terms.py --dir data/sample

산출물:
    reports/search_terms_<날짜>.md              사람이 읽는 리포트
    campaigns/generated/negatives_to_add.csv     Editor 로 바로 올리는 제외 키워드
    campaigns/generated/keywords_to_add.csv      정확일치로 승격할 키워드
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import csv  # noqa: E402

import yaml  # noqa: E402

import adslib as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_search_terms(directory: str) -> list[dict]:
    rows = []
    for fname in sorted(os.listdir(directory)) if os.path.isdir(directory) else []:
        low = fname.lower()
        if not low.endswith((".csv", ".tsv")):
            continue
        if not any(p in low for p in ("searchterm", "search_term", "검색어")):
            continue
        try:
            rows.extend(A.load_report(os.path.join(directory, fname)))
        except ValueError as exc:
            print(f"  [오류] {exc}")
    return rows


def blocked_by_rule(term: str, rules: list[str]) -> str | None:
    low = term.lower()
    for token in rules:
        token = str(token)
        if token.lower() in low:
            return token
    return None


def classify(rows: list[dict], plan: dict, cfg: dict) -> dict:
    tg = cfg["targets"]
    all_rules = list(plan["negatives"]["general"])
    for key in plan["negatives"]:
        if key != "general":
            all_rules += list(plan["negatives"][key])

    agg = A.aggregate(rows, "search_term", "campaign")
    rule_hits, waste, winners, watch = [], [], [], []

    # 목표 CPA: 제품별 목표의 평균 (캠페인-제품 매핑이 없을 수 있으므로)
    cpas = [p["target_cpa"] for p in cfg["products"].values()]
    target_cpa = sum(cpas) / len(cpas) if cpas else 0

    for b in agg.values():
        term = b.get("search_term", "")
        if not term:
            continue
        hit = blocked_by_rule(term, all_rules)
        if hit and b["conversions"] == 0:
            b["_rule"] = hit
            rule_hits.append(b)
            continue
        if b["conversions"] > 0:
            b["_ok"] = target_cpa == 0 or b["cpa"] <= target_cpa
            winners.append(b)
        elif b["clicks"] >= tg["wasted_spend_click_threshold"]:
            waste.append(b)
        elif b["clicks"] >= 5:
            watch.append(b)

    for lst in (rule_hits, waste, watch):
        lst.sort(key=lambda b: -b["cost"])
    winners.sort(key=lambda b: -b["conversions"])
    return {"rule": rule_hits, "waste": waste, "winners": winners, "watch": watch}


def table(rows: list[dict], extra: str = "") -> str:
    header = ["검색어", "캠페인", "비용", "클릭", "CTR", "전환", "CPA"]
    if extra:
        header.append(extra)
    body = []
    for b in rows[:40]:
        line = [b.get("search_term", "")[:44],
                b.get("campaign", "")[:24],
                A.won(b["cost"]), A.num(b["clicks"]), A.pct(b["ctr"]),
                A.num(b["conversions"]),
                A.won(b["cpa"]) if b["conversions"] else "—"]
        if extra:
            line.append(b.get("_rule", "") if extra == "매칭 규칙"
                        else ("목표 이내" if b.get("_ok") else "목표 초과"))
        body.append(line)
    return A.md_table(header, body, align_right={2, 3, 4, 5, 6})


def main() -> int:
    ap = argparse.ArgumentParser(description="검색어 분석 → 제외/신규 키워드 후보")
    ap.add_argument("--dir", default=os.path.join(ROOT, "data", "raw"))
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    ap.add_argument("--gen", default=os.path.join(ROOT, "campaigns", "generated"))
    ap.add_argument("--plan", default=os.path.join(ROOT, "campaigns", "plan.yaml"))
    ap.add_argument("--config", default=os.path.join(ROOT, "config", "products.yaml"))
    args = ap.parse_args()

    with open(args.plan, encoding="utf-8") as fh:
        plan = yaml.safe_load(fh)
    with open(args.config, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    rows = load_search_terms(args.dir)
    if not rows:
        print(f"{args.dir} 에서 검색어 리포트를 찾지 못했습니다.\n"
              f"파일명에 '검색어' 또는 'searchterm' 이 들어가야 합니다. "
              f"내보내는 방법은 data/raw/README.md 참고.")
        return 1
    print(f"검색어 {len(rows)}행 로드")

    g = classify(rows, plan, cfg)
    today = dt.date.today().isoformat()

    wasted_cost = sum(b["cost"] for b in g["rule"]) + sum(b["cost"] for b in g["waste"])
    parts = [f"# 검색어 분석 — {today}", "",
             f"제외 후보로 걸러낸 지출: **{A.won(wasted_cost)}**", "",
             "## 1. 제외 키워드 규칙에 걸린 검색어 (즉시 제외)", ""]
    parts.append(table(g["rule"], "매칭 규칙") if g["rule"] else "_해당 없음_")
    parts += ["", "## 2. 전환 없이 클릭만 소진한 검색어 (제외 검토)", ""]
    parts.append(table(g["waste"]) if g["waste"] else "_해당 없음_")
    parts += ["", "## 3. 전환이 발생한 검색어 (정확일치로 승격)", ""]
    parts.append(table(g["winners"], "목표 대비") if g["winners"] else "_해당 없음_")
    parts += ["", "## 4. 관찰 대상 (클릭 5회 이상, 아직 판단 불가)", ""]
    parts.append(table(g["watch"]) if g["watch"] else "_해당 없음_")
    parts += ["", "## 적용 방법", "",
              "1. `campaigns/generated/negatives_to_add.csv` 를 Google Ads Editor 로 가져오기",
              "2. `campaigns/generated/keywords_to_add.csv` 의 키워드를 해당 광고그룹에 "
              "정확일치로 추가",
              "3. 2번에서 추가한 키워드는 기존 광범위/구문 키워드와 겹치므로, "
              "검색어 리포트를 다시 보고 중복 노출을 확인하세요.", ""]

    os.makedirs(args.out, exist_ok=True)
    rp = os.path.join(args.out, f"search_terms_{today}.md")
    with open(rp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    print(f"리포트: {rp}")

    os.makedirs(args.gen, exist_ok=True)
    neg_path = os.path.join(args.gen, "negatives_to_add.csv")
    with open(neg_path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Campaign", "Ad Group", "Keyword", "Criterion Type"])
        for b in g["rule"] + g["waste"]:
            w.writerow([b.get("campaign", ""), "", b["search_term"],
                        "Campaign Negative Exact"])
    print(f"제외 키워드: {neg_path} ({len(g['rule']) + len(g['waste'])}개)")

    kw_path = os.path.join(args.gen, "keywords_to_add.csv")
    promote = [b for b in g["winners"] if b.get("_ok")]
    with open(kw_path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["Campaign", "Ad Group", "Keyword", "Criterion Type", "Status"])
        for b in promote:
            w.writerow([b.get("campaign", ""), b.get("ad_group", ""),
                        b["search_term"], "Exact", "Enabled"])
    print(f"신규 키워드: {kw_path} ({len(promote)}개) "
          f"— Ad Group 열은 비어 있을 수 있으니 채운 뒤 업로드하세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
