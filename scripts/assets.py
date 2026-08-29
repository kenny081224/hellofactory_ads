#!/usr/bin/env python3
"""광고 애셋(구 광고 확장) 실적을 분석하고 개선안을 만듭니다.

사용법:
    python3 scripts/assets.py
    python3 scripts/assets.py --dir data/sample

두 가지를 봅니다.
    1) RSA 애셋 — 헤드라인·설명별 실적 등급(최우수/양호/낮음/학습 중)
       → '낮음' 은 교체 대상, '최우수' 는 유지하고 비슷한 결로 확장
    2) 확장 애셋 커버리지 — 사이트링크·콜아웃·스니펫·전화·이미지가
       캠페인마다 최소 개수를 갖췄는지

산출물: reports/assets_<날짜>.md
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

# 애셋 유형 문자열 → 커버리지 항목 키
TYPE_KEYS = {
    "sitelink": ["사이트링크", "sitelink"],
    "callout": ["콜아웃", "callout"],
    "snippet": ["구조화된 스니펫", "스니펫", "structured snippet", "snippet"],
    "call": ["전화", "통화", "call"],
    "image": ["이미지", "image"],
    "location": ["위치", "location"],
    "price": ["가격", "price"],
    "promotion": ["프로모션", "promotion"],
    "lead_form": ["리드 양식", "리드양식", "lead form"],
}
COVERAGE_LABEL = {
    "sitelink": "사이트링크", "callout": "콜아웃", "snippet": "구조화된 스니펫",
    "call": "전화", "image": "이미지", "location": "위치",
    "price": "가격", "promotion": "프로모션", "lead_form": "리드 양식",
}


def load_assets(directory: str) -> list[dict]:
    rows = []
    if not os.path.isdir(directory):
        return rows
    for fname in sorted(os.listdir(directory)):
        if not fname.lower().endswith((".csv", ".tsv")):
            continue
        path = os.path.join(directory, fname)
        if A.classify_report(path) != "asset":
            continue
        try:
            rows.extend(A.load_report(path))
            print(f"  [읽음] {fname} ({len(rows)}행 누적)")
        except ValueError as exc:
            print(f"  [오류] {exc}")
    return rows


def grade(value: str, labels: dict) -> str:
    """리포트의 '실적' 값을 best/good/low/learning/none 으로 정규화."""
    v = (value or "").strip()
    for key, names in labels.items():
        for name in names:
            if name is None:
                continue
            if v == str(name) or (v and str(name) and v.startswith(str(name))):
                return key
    return "none"


def type_key(value: str) -> str | None:
    v = (value or "").strip().lower()
    for key, names in TYPE_KEYS.items():
        if any(n.lower() in v for n in names):
            return key
    return None


def rsa_section(rows: list[dict], labels: dict, pool: dict) -> list[str]:
    """헤드라인·설명 애셋 등급 분석."""
    field_rows = [r for r in rows if r.get("field_type")]
    if not field_rows:
        return ["_헤드라인·설명 애셋 리포트가 없습니다. "
                "Google Ads → 광고 → 애셋 화면에서 내려받아 넣으세요._"]

    out = []
    buckets: dict[str, list[dict]] = {}
    for r in field_rows:
        g = grade(r.get("performance", ""), labels)
        r["_grade"] = g
        buckets.setdefault(g, []).append(r)

    counts = {k: len(v) for k, v in buckets.items()}
    total = len(field_rows)
    out.append(A.md_table(
        ["등급", "개수", "비중"],
        [[{"best": "최우수", "good": "양호", "low": "낮음",
           "learning": "학습 중", "none": "평가 없음"}[k],
          str(counts.get(k, 0)),
          A.pct(counts.get(k, 0) / total) if total else "-"]
         for k in ("best", "good", "low", "learning", "none")],
        align_right={1, 2}))
    out.append("")

    low = sorted(buckets.get("low", []), key=lambda r: -r.get("cost", 0))
    if low:
        out.append(f"### 교체 대상 — '낮음' 등급 {len(low)}개")
        out.append("")
        out.append(A.md_table(
            ["애셋", "필드", "광고그룹", "노출", "클릭", "CTR"],
            [[r.get("asset", "")[:34], r.get("field_type", ""),
              r.get("ad_group", "")[:20], A.num(r.get("impressions", 0)),
              A.num(r.get("clicks", 0)), A.pct(r.get("ctr", 0))]
             for r in low[:25]], align_right={3, 4, 5}))
        out.append("")
        out.append("한 번에 2~3개씩만 바꾸세요. 전부 갈아엎으면 무엇이 "
                   "효과였는지 알 수 없고 학습도 초기화됩니다.")
        out.append("")
        used = {r.get("asset", "").strip() for r in field_rows}
        spare = [h for h in pool.get("headlines", []) if h not in used]
        if spare:
            out.append("**저장소에 있는 미사용 헤드라인 후보** "
                       "(`campaigns/ads.yaml`)")
            out.append("")
            out.append("\n".join(f"- {h}" for h in spare[:15]))
            out.append("")

    best = sorted(buckets.get("best", []), key=lambda r: -r.get("clicks", 0))
    if best:
        out.append(f"### 유지·확장 대상 — '최우수' {len(best)}개")
        out.append("")
        out.append(A.md_table(
            ["애셋", "필드", "노출", "클릭", "CTR"],
            [[r.get("asset", "")[:34], r.get("field_type", ""),
              A.num(r.get("impressions", 0)), A.num(r.get("clicks", 0)),
              A.pct(r.get("ctr", 0))] for r in best[:15]],
            align_right={2, 3, 4}))
        out.append("")
        out.append("이 문구들이 통한 이유(가격 언급? 법규? 속도?)를 뽑아 "
                   "같은 결의 헤드라인을 2~3개 더 만드세요.")
        out.append("")

    if counts.get("learning", 0) > total * 0.5:
        out.append("> 절반 이상이 '학습 중'입니다. 노출이 더 쌓여야 등급이 "
                   "나오므로 지금 바꾸면 판단할 기회를 잃습니다. 2주 더 두세요.")
        out.append("")
    return out


def coverage_section(rows: list[dict], minimum: dict) -> list[str]:
    """캠페인별 확장 애셋 보유 현황."""
    ext_rows = [r for r in rows if not r.get("field_type")]
    if not ext_rows:
        return ["_확장 애셋 리포트가 없습니다. Google Ads → 캠페인 → 애셋 "
                "화면에서 내려받아 넣으세요._"]

    by_camp: dict[str, dict[str, int]] = {}
    perf: dict[tuple, dict] = {}
    for r in ext_rows:
        key = type_key(r.get("asset_type", ""))
        if key is None:
            continue
        camp = r.get("campaign", "") or "(계정 공통)"
        by_camp.setdefault(camp, {}).setdefault(key, 0)
        by_camp[camp][key] += 1
        p = perf.setdefault((camp, key), {"impressions": 0.0, "clicks": 0.0,
                                          "cost": 0.0, "conversions": 0.0,
                                          "conv_value": 0.0})
        for m in p:
            p[m] += r.get(m, 0.0)

    out = []
    order = ["sitelink", "callout", "snippet", "call", "image",
             "location", "price", "promotion", "lead_form"]
    headers = ["캠페인"] + [COVERAGE_LABEL[k] for k in order]
    body = []
    gaps = []
    for camp, counts in sorted(by_camp.items()):
        line = [camp[:30]]
        for k in order:
            n = counts.get(k, 0)
            need = minimum.get(k, 0)
            if need and n < need:
                line.append(f"**{n}/{need}**")
                gaps.append((camp, k, COVERAGE_LABEL[k], n, need))
            else:
                line.append(str(n) if n else "—")
        body.append(line)
    out.append(A.md_table(headers, body,
                          align_right=set(range(1, len(headers)))))
    out.append("")

    if gaps:
        BULK = {"sitelink", "callout", "snippet"}
        out.append("### 부족한 애셋")
        out.append("")
        for camp, key, label, n, need in gaps:
            if key in BULK:
                how = ("`campaigns/assets.yaml` 에 문안이 준비되어 있습니다 "
                       "— Editor 로 업로드")
            else:
                how = "Google Ads 화면에서 직접 설정 (`docs/assets.md`)"
            out.append(f"- **{camp}** — {label} {n}개 (최소 {need}개). {how}")
        out.append("")
        out.append("`python3 scripts/make_editor_csv.py` 로 생성되는 "
                   "`06_sitelinks.csv` / `07_callouts.csv` / "
                   "`08_structured_snippets.csv` 를 올리면 텍스트 애셋은 채워집니다. "
                   "전화·이미지·리드 양식은 화면에서만 설정할 수 있습니다.")
        out.append("")
    else:
        out.append("최소 기준은 모두 충족했습니다. 다음은 개수가 아니라 "
                   "품질입니다 — 아래 실적표에서 클릭이 안 나오는 애셋을 교체하세요.")
        out.append("")

    rank = sorted(perf.items(), key=lambda kv: -kv[1]["clicks"])[:20]
    if rank:
        out.append("### 애셋 유형별 실적")
        out.append("")
        out.append(A.md_table(
            ["캠페인", "유형", "노출", "클릭", "CTR", "전환"],
            [[c[:26], COVERAGE_LABEL[k],
              A.num(m["impressions"]), A.num(m["clicks"]),
              A.pct(m["clicks"] / m["impressions"]) if m["impressions"] else "-",
              A.num(m["conversions"])]
             for (c, k), m in rank], align_right={2, 3, 4, 5}))
        out.append("")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="애셋 실적 분석")
    ap.add_argument("--dir", default=os.path.join(ROOT, "data", "raw"))
    ap.add_argument("--out", default=os.path.join(ROOT, "reports"))
    ap.add_argument("--assets", default=os.path.join(ROOT, "campaigns", "assets.yaml"))
    ap.add_argument("--ads", default=os.path.join(ROOT, "campaigns", "ads.yaml"))
    args = ap.parse_args()

    with open(args.assets, encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    with open(args.ads, encoding="utf-8") as fh:
        ads = yaml.safe_load(fh)

    # ads.yaml 전체 헤드라인 풀 (교체 후보 제안용)
    pool = {"headlines": []}
    for rsa in ads.values():
        pool["headlines"].extend(rsa.get("headlines", []))
    pool["headlines"] = list(dict.fromkeys(pool["headlines"]))

    rows = load_assets(args.dir)
    today = dt.date.today().isoformat()

    if not rows:
        print(f"\n{args.dir} 에 애셋 리포트가 없습니다.\n"
              "Google Ads 에서 두 가지를 내려받아 넣으세요.\n"
              "  1) 캠페인 → 애셋      (사이트링크·콜아웃·스니펫·전화·이미지)\n"
              "  2) 광고 → 애셋        (헤드라인·설명별 실적 등급)\n"
              "자세한 내용은 docs/assets.md 참고.")
        return 1

    parts = [f"# 애셋 진단 — {today}", "",
             "## 1. RSA 애셋 (헤드라인·설명)", ""]
    parts += rsa_section(rows, spec.get("performance_labels", {}), pool)
    parts += ["## 2. 확장 애셋 커버리지", ""]
    parts += coverage_section(rows, spec.get("coverage_minimum", {}))
    parts += ["## 3. 다음 액션", "",
              "1. '낮음' 등급 헤드라인을 2~3개만 교체하고 `campaigns/ads.yaml` 에도 반영",
              "2. 부족한 확장 애셋을 `make_editor_csv.py` 생성물로 채우기",
              "3. 전화·리드 양식·이미지 애셋은 화면에서 직접 설정 "
              "(`campaigns/assets.yaml` 의 manual 항목)",
              "4. 2주 뒤 다시 실행해 등급 변화 확인", ""]

    os.makedirs(args.out, exist_ok=True)
    path = os.path.join(args.out, f"assets_{today}.md")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(parts))
    print(f"\n생성됨: {path}\n")
    print("\n".join(parts))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
