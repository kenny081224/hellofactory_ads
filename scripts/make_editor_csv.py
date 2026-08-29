#!/usr/bin/env python3
"""campaigns/plan.yaml + campaigns/ads.yaml -> Google Ads Editor 업로드용 CSV.

사용법:
    python3 scripts/make_editor_csv.py
    python3 scripts/make_editor_csv.py --out campaigns/editor

생성 파일 (Google Ads Editor > 계정 > 가져오기 > 파일에서 가져오기 순서대로):
    01_campaigns.csv      캠페인 + 예산 + 입찰 전략
    02_ad_groups.csv      광고그룹 + 기본 입찰가
    03_keywords.csv       키워드 (일치 유형별)
    04_negative_keywords.csv  제외 키워드 (캠페인 단위)
    05_responsive_search_ads.csv  반응형 검색광고

한국어는 전각 문자로 계산되므로 헤드라인 15자 / 설명 45자 / 경로 7자 제한을
넘으면 오류를 내고 중단합니다.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import unicodedata

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Google Ads 글자 수는 '영문 기준' 한도를 쓰고, 한글·한자·가나 같은 전각 문자를
# 2자로 계산합니다. 공백·영문·숫자는 1자입니다.
#   예) "원격 수신 가능한 스마트 비상벨" = 한글 13자×2 + 공백 4자×1 = 30  → 딱 한도
# 단순히 len() 으로 15자를 재면 공백이 든 문구를 억울하게 잘라내게 되므로
# 아래 width() 로 정확히 계산합니다.
HEADLINE_MAX = 30
DESCRIPTION_MAX = 90
PATH_MAX = 15
SITELINK_TEXT_MAX = 25
SITELINK_DESC_MAX = 35
CALLOUT_MAX = 25
SNIPPET_VALUE_MAX = 25
SNIPPET_MIN_VALUES = 4


def width(text: str) -> int:
    """Google Ads 기준 글자 수. 전각 문자는 2, 나머지는 1."""
    return sum(2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
               for ch in text or "")
RSA_MIN_HEADLINES = 8  # Google 권장: 최소 8개 이상, 가능하면 15개


class PlanError(Exception):
    pass


def load_yaml(path: str) -> dict:
    with open(path, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def validate_assets(assets: dict, plan: dict) -> list[str]:
    """애셋 글자 수와 캠페인 참조를 검사."""
    errs = []
    if not assets:
        return errs
    camp_ids = {c["id"] for c in plan["campaigns"]}
    for group, ids in (assets.get("groups") or {}).items():
        for cid in ids:
            if cid not in camp_ids:
                errs.append(f"[애셋 groups.{group}] 캠페인 id '{cid}' 가 "
                            f"plan.yaml 에 없습니다.")

    for group, items in (assets.get("sitelinks") or {}).items():
        for it in items:
            for key, lim in (("text", SITELINK_TEXT_MAX),
                             ("desc1", SITELINK_DESC_MAX),
                             ("desc2", SITELINK_DESC_MAX)):
                val = it.get(key, "")
                if width(val) > lim:
                    errs.append(f"[사이트링크 {group}] {key} '{val}' "
                                f"{width(val)}자 — 최대 {lim}자")
    for group, items in (assets.get("callouts") or {}).items():
        for c in items:
            if width(c) > CALLOUT_MAX:
                errs.append(f"[콜아웃 {group}] '{c}' {width(c)}자 — "
                            f"최대 {CALLOUT_MAX}자")
    for group, items in (assets.get("snippets") or {}).items():
        for sn in items:
            vals = sn.get("values", [])
            if len(vals) < SNIPPET_MIN_VALUES:
                errs.append(f"[스니펫 {group}/{sn.get('header')}] 값 {len(vals)}개 "
                            f"— 최소 {SNIPPET_MIN_VALUES}개 필요")
            for v in vals:
                if width(v) > SNIPPET_VALUE_MAX:
                    errs.append(f"[스니펫 {group}] '{v}' {width(v)}자 — "
                                f"최대 {SNIPPET_VALUE_MAX}자")
    return errs


def validate(plan: dict, ads: dict) -> list[str]:
    """설계안의 글자 수 / 참조 무결성을 검사. 오류 목록을 반환."""
    errs = []
    share = sum(c["budget_share"] for c in plan["campaigns"]) + plan.get("reserve_share", 0)
    if abs(share - 1.0) > 0.001:
        errs.append(f"budget_share 합계가 {share:.3f} 입니다. 예비분 포함 1.0 이어야 합니다.")

    for camp in plan["campaigns"]:
        for ag in camp["ad_groups"]:
            for field in ("path1", "path2"):
                val = ag.get(field, "")
                if width(val) > PATH_MAX:
                    errs.append(f"[{camp['id']}/{ag['id']}] {field} '{val}' "
                                f"{width(val)}자 — 최대 {PATH_MAX}자")
            key = ag.get("rsa")
            if key not in ads:
                errs.append(f"[{camp['id']}/{ag['id']}] RSA '{key}' 를 "
                            f"campaigns/ads.yaml 에서 찾을 수 없습니다.")
                continue
            rsa = ads[key]
            heads, descs = rsa["headlines"], rsa["descriptions"]
            if len(heads) < RSA_MIN_HEADLINES:
                errs.append(f"[{key}] 헤드라인 {len(heads)}개 — "
                            f"최소 {RSA_MIN_HEADLINES}개를 권장합니다.")
            if len(heads) > 15:
                errs.append(f"[{key}] 헤드라인 {len(heads)}개 — 최대 15개입니다.")
            if not 2 <= len(descs) <= 4:
                errs.append(f"[{key}] 설명 {len(descs)}개 — 2~4개여야 합니다.")
            for h in heads:
                if width(h) > HEADLINE_MAX:
                    errs.append(f"[{key}] 헤드라인 '{h}' {width(h)}자 — "
                                f"최대 {HEADLINE_MAX}자")
            for d in descs:
                if width(d) > DESCRIPTION_MAX:
                    errs.append(f"[{key}] 설명 '{d}' {width(d)}자 — "
                                f"최대 {DESCRIPTION_MAX}자")
            if len(set(heads)) != len(heads):
                errs.append(f"[{key}] 중복된 헤드라인이 있습니다.")
    return errs


def write_csv(path: str, header: list[str], rows: list[list]) -> None:
    with open(path, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(rows)
    print(f"  {os.path.basename(path):32s} {len(rows):4d}행")


def build_assets(assets: dict, plan: dict, cfg: dict, resolve_url,
                 out_dir: str, status: str) -> None:
    """사이트링크 / 콜아웃 / 구조화된 스니펫을 캠페인 단위 CSV로 생성."""
    if not assets:
        return
    by_id = {c["id"]: c for c in plan["campaigns"]}
    groups = assets.get("groups") or {}

    sl_rows, co_rows, sn_rows = [], [], []
    for group, camp_ids in groups.items():
        for cid in camp_ids:
            camp = by_id.get(cid)
            if not camp:
                continue
            name = camp["name"]
            product = camp["product"]
            for it in (assets.get("sitelinks") or {}).get(group, []):
                sl_rows.append([name, "", it["text"], it.get("desc1", ""),
                                it.get("desc2", ""),
                                resolve_url(product, it.get("landing")), status])
            for c in (assets.get("callouts") or {}).get(group, []):
                co_rows.append([name, c, status])
            for sn in (assets.get("snippets") or {}).get(group, []):
                sn_rows.append([name, sn["header"],
                                ";".join(sn.get("values", [])), status])

    # 브랜드 캠페인처럼 두 그룹에 모두 속하면 중복이 생기므로 제거
    def dedupe(rows):
        seen, out = set(), []
        for r in rows:
            key = tuple(r)
            if key not in seen:
                seen.add(key)
                out.append(r)
        return out

    write_csv(os.path.join(out_dir, "06_sitelinks.csv"),
              ["Campaign", "Ad Group", "Sitelink Text", "Description Line 1",
               "Description Line 2", "Final URL", "Status"], dedupe(sl_rows))
    write_csv(os.path.join(out_dir, "07_callouts.csv"),
              ["Campaign", "Callout Text", "Status"], dedupe(co_rows))
    write_csv(os.path.join(out_dir, "08_structured_snippets.csv"),
              ["Campaign", "Header", "Values", "Status"], dedupe(sn_rows))


def build(plan: dict, ads: dict, cfg: dict, out_dir: str, status: str,
          assets: dict | None = None) -> None:
    d = plan["defaults"]
    monthly = cfg["account"]["monthly_budget"]
    def resolve_url(product: str, landing: str | None) -> str:
        """제품 기본 URL, 또는 landing_urls 에 지정된 세부 페이지 URL."""
        prod = cfg["products"][product]
        if landing:
            specific = (prod.get("landing_urls") or {}).get(landing)
            if specific:
                return specific
        return prod.get("landing_url") or ""

    missing = [k for k, v in cfg["products"].items() if not v.get("landing_url")]
    if missing:
        raise PlanError(f"config/products.yaml 에 {missing} 의 landing_url 이 없습니다.")

    camp_rows, ag_rows, kw_rows, neg_rows, ad_rows = [], [], [], [], []
    fallback: list[str] = []   # 세부 랜딩 URL이 비어 기본 URL로 떨어진 광고그룹

    for camp in plan["campaigns"]:
        daily = round(monthly * camp["budget_share"] / 30.4, -2)  # 100원 단위
        strategy = camp.get("bid_strategy", d["start_bid_strategy"])
        camp_rows.append([
            camp["name"], "Search", status, f"{daily:.0f}", "Daily",
            d["networks"], d["languages"], d["locations"], strategy,
            d["ad_rotation"],
        ])

        # 제외 키워드: 공통 + 제품별
        product = camp["product"]
        negatives = list(plan["negatives"]["general"]) + \
            list(plan["negatives"].get(product, []))
        for term in dict.fromkeys(negatives):           # 중복 제거, 순서 유지
            neg_rows.append([camp["name"], "", term, "Campaign Negative Phrase"])

        for ag in camp["ad_groups"]:
            max_cpc = ag.get("max_cpc", d["start_max_cpc"])
            ag_rows.append([camp["name"], ag["name"], status, f"{max_cpc}"])

            for crit, kws in ag.get("keywords", {}).items():
                crit_type = {"exact": "Exact", "phrase": "Phrase",
                             "broad": "Broad"}[crit]
                for kw in kws:
                    kw_rows.append([camp["name"], ag["name"], kw, crit_type,
                                    f"{max_cpc}", status])

            rsa = ads[ag["rsa"]]
            product = ag.get("final_url") or camp["product"]
            landing = ag.get("landing")
            url = resolve_url(product, landing)
            if landing and not (cfg["products"][product].get("landing_urls") or {}
                                ).get(landing):
                fallback.append(f"{camp['name']} / {ag['name']} "
                                f"(landing: {landing})")
            row = [camp["name"], ag["name"], "Responsive search ad", status]
            heads = rsa["headlines"]
            row += list(heads) + [""] * (15 - len(heads))
            row += ["1" if rsa.get("pin_h1") else ""]
            descs = rsa["descriptions"]
            row += list(descs) + [""] * (4 - len(descs))
            row += [url, ag.get("path1", ""), ag.get("path2", "")]
            ad_rows.append(row)

    os.makedirs(out_dir, exist_ok=True)
    print(f"\n생성 위치: {out_dir}")
    write_csv(os.path.join(out_dir, "01_campaigns.csv"),
              ["Campaign", "Campaign Type", "Status", "Campaign Daily Budget",
               "Budget Type", "Networks", "Languages", "Locations",
               "Bid Strategy Type", "Ad Rotation"], camp_rows)
    write_csv(os.path.join(out_dir, "02_ad_groups.csv"),
              ["Campaign", "Ad Group", "Status", "Max CPC"], ag_rows)
    write_csv(os.path.join(out_dir, "03_keywords.csv"),
              ["Campaign", "Ad Group", "Keyword", "Criterion Type", "Max CPC",
               "Status"], kw_rows)
    write_csv(os.path.join(out_dir, "04_negative_keywords.csv"),
              ["Campaign", "Ad Group", "Keyword", "Criterion Type"], neg_rows)
    write_csv(os.path.join(out_dir, "05_responsive_search_ads.csv"),
              ["Campaign", "Ad Group", "Ad type", "Status"]
              + [f"Headline {i}" for i in range(1, 16)]
              + ["Headline 1 position"]
              + [f"Description {i}" for i in range(1, 5)]
              + ["Final URL", "Path 1", "Path 2"], ad_rows)

    if fallback:
        print(f"\n[주의] 아래 {len(fallback)}개 광고그룹은 세부 랜딩 URL이 비어 있어 "
              f"제품 기본 URL로 설정되었습니다.")
        print("       config/products.yaml 의 landing_urls 를 채우면 "
              "광고그룹별 페이지로 연결됩니다.")
        for item in fallback:
            print(f"       - {item}")

    build_assets(assets, plan, cfg, resolve_url, out_dir, status)

    # 예산 요약
    print("\n[예산 배분]")
    total_daily = 0.0
    for camp in plan["campaigns"]:
        daily = round(monthly * camp["budget_share"] / 30.4, -2)
        total_daily += daily
        print(f"  {camp['name']:34s} {camp['budget_share'] * 100:5.1f}%  "
              f"일 {daily:,.0f}원  월 {monthly * camp['budget_share']:,.0f}원")
    reserve = plan.get("reserve_share", 0)
    print(f"  {'(예비 — 집행 안 함)':34s} {reserve * 100:5.1f}%  "
          f"       월 {monthly * reserve:,.0f}원")
    print(f"  {'합계 (집행분)':34s}         일 {total_daily:,.0f}원")


def main() -> int:
    ap = argparse.ArgumentParser(description="Google Ads Editor 업로드 CSV 생성")
    ap.add_argument("--plan", default=os.path.join(ROOT, "campaigns", "plan.yaml"))
    ap.add_argument("--ads", default=os.path.join(ROOT, "campaigns", "ads.yaml"))
    ap.add_argument("--assets", default=os.path.join(ROOT, "campaigns", "assets.yaml"))
    ap.add_argument("--config", default=os.path.join(ROOT, "config", "products.yaml"))
    ap.add_argument("--out", default=os.path.join(ROOT, "campaigns", "editor"))
    ap.add_argument("--status", default="Paused",
                    choices=["Paused", "Enabled"],
                    help="업로드 직후 상태. 검수를 위해 기본값은 Paused 입니다.")
    args = ap.parse_args()

    plan = load_yaml(args.plan)
    ads = load_yaml(args.ads)
    cfg = load_yaml(args.config)
    assets = load_yaml(args.assets) if os.path.isfile(args.assets) else {}

    errs = validate(plan, ads) + validate_assets(assets, plan)
    if errs:
        print("설계안 검사 실패:", file=sys.stderr)
        for e in errs:
            print(f"  - {e}", file=sys.stderr)
        return 1
    print("설계안 검사 통과 (글자 수 / 참조 무결성)")

    try:
        build(plan, ads, cfg, args.out, args.status, assets)
    except PlanError as exc:
        print(f"\n오류: {exc}", file=sys.stderr)
        return 1

    print("\n다음 단계: Google Ads Editor > 계정 > 가져오기 > 파일에서 가져오기")
    print("           01 → 02 → ... → 08 순서로 하나씩 가져온 뒤 '변경사항 게시'")
    print("           (06~08 애셋은 열 이름이 다르면 가져오기 대화상자에서 직접 매핑)")
    print(f"           업로드 상태: {args.status} "
          f"(검수 후 직접 '사용 설정'으로 바꾸세요)")
    print("\n주의: 'Target impression share'(노출 점유율 타겟) 전략을 쓰는 캠페인은")
    print("      Editor 가져오기 후 목표 위치(검색 페이지 상단)와 목표 비율(90%),")
    print("      상한 CPC 를 화면에서 직접 지정해야 게시됩니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
