#!/usr/bin/env python3
"""Google Ads API 로 실적 리포트를 받아 data/raw/ 에 CSV 로 저장합니다.

사용법:
    python3 scripts/fetch_ads.py                    # 최근 90일
    python3 scripts/fetch_ads.py --days 30
    python3 scripts/fetch_ads.py --since 2026-01-01 --until 2026-08-28
    python3 scripts/fetch_ads.py --all-time         # 계정 개설 이후 전체
    python3 scripts/fetch_ads.py --check            # 인증만 확인하고 종료

저장되는 파일은 scripts/analyze.py 와 scripts/search_terms.py 가 그대로 읽는
한국어 컬럼 형식입니다. 받은 뒤 이어서 실행하세요.

    python3 scripts/fetch_ads.py && python3 scripts/analyze.py && python3 scripts/search_terms.py

인증 정보 발급은 docs/google_ads_api.md 참고.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from gads_api import (  # noqa: E402
    MATCH_TYPE_KO, STATUS_KO, ApiError, CredentialsError, GoogleAdsClient,
    micros, number, pick,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 모든 리포트에 공통으로 붙는 지표
METRIC_FIELDS = [
    "metrics.cost_micros",
    "metrics.impressions",
    "metrics.clicks",
    "metrics.ctr",
    "metrics.average_cpc",
    "metrics.conversions",
    "metrics.conversions_value",
]
METRIC_HEADERS = ["비용", "노출수", "클릭수", "CTR", "평균 CPC", "전환수", "전환 가치"]


def metric_values(row: dict) -> list:
    return [
        f"{micros(pick(row, 'metrics.cost_micros')):.0f}",
        f"{number(pick(row, 'metrics.impressions')):.0f}",
        f"{number(pick(row, 'metrics.clicks')):.0f}",
        f"{number(pick(row, 'metrics.ctr')) * 100:.2f}%",
        f"{micros(pick(row, 'metrics.average_cpc')):.0f}",
        f"{number(pick(row, 'metrics.conversions')):.2f}",
        f"{number(pick(row, 'metrics.conversions_value')):.0f}",
    ]


# 리포트 정의: (파일명 접두사, FROM 리소스, 추가 SELECT 필드, 추가 헤더, 값 추출 함수)
def _campaign_extra(row):
    return [
        pick(row, "campaign.name") or "",
        STATUS_KO.get(pick(row, "campaign.status"), pick(row, "campaign.status") or ""),
    ]


def _campaign_tail(row):
    return [
        f"{number(pick(row, 'metrics.search_impression_share')) * 100:.2f}%",
        f"{number(pick(row, 'metrics.search_budget_lost_impression_share')) * 100:.2f}%",
        f"{number(pick(row, 'metrics.search_rank_lost_impression_share')) * 100:.2f}%",
    ]


REPORTS = [
    {
        "name": "캠페인",
        "resource": "campaign",
        "select": ["campaign.name", "campaign.status"] + METRIC_FIELDS + [
            "metrics.search_impression_share",
            "metrics.search_budget_lost_impression_share",
            "metrics.search_rank_lost_impression_share",
        ],
        "headers": ["캠페인", "캠페인 상태"] + METRIC_HEADERS + [
            "검색 노출 점유율", "검색 손실 노출 점유율(예산)", "검색 손실 노출 점유율(순위)",
        ],
        "row": lambda r: _campaign_extra(r) + metric_values(r) + _campaign_tail(r),
        "where": "campaign.status != 'REMOVED'",
    },
    {
        "name": "광고그룹",
        "resource": "ad_group",
        "select": ["campaign.name", "ad_group.name", "ad_group.status"] + METRIC_FIELDS,
        "headers": ["캠페인", "광고그룹", "광고그룹 상태"] + METRIC_HEADERS,
        "row": lambda r: [
            pick(r, "campaign.name") or "",
            pick(r, "ad_group.name") or "",
            STATUS_KO.get(pick(r, "ad_group.status"), pick(r, "ad_group.status") or ""),
        ] + metric_values(r),
        "where": "ad_group.status != 'REMOVED'",
    },
    {
        "name": "키워드",
        "resource": "keyword_view",
        "select": [
            "campaign.name", "ad_group.name",
            "ad_group_criterion.keyword.text",
            "ad_group_criterion.keyword.match_type",
            "ad_group_criterion.status",
        ] + METRIC_FIELDS,
        "headers": ["검색 키워드", "일치검색유형", "캠페인", "광고그룹", "키워드 상태"]
                   + METRIC_HEADERS,
        "row": lambda r: [
            pick(r, "ad_group_criterion.keyword.text") or "",
            MATCH_TYPE_KO.get(pick(r, "ad_group_criterion.keyword.match_type"), ""),
            pick(r, "campaign.name") or "",
            pick(r, "ad_group.name") or "",
            STATUS_KO.get(pick(r, "ad_group_criterion.status"),
                          pick(r, "ad_group_criterion.status") or ""),
        ] + metric_values(r),
        "where": "ad_group_criterion.status != 'REMOVED'",
    },
    {
        "name": "검색어",
        "resource": "search_term_view",
        "select": [
            "campaign.name", "ad_group.name",
            "search_term_view.search_term",
            "segments.search_term_match_type",
        ] + METRIC_FIELDS,
        "headers": ["검색어", "일치검색유형", "캠페인", "광고그룹"] + METRIC_HEADERS,
        "row": lambda r: [
            pick(r, "search_term_view.search_term") or "",
            MATCH_TYPE_KO.get(pick(r, "segments.search_term_match_type"),
                              pick(r, "segments.search_term_match_type") or ""),
            pick(r, "campaign.name") or "",
            pick(r, "ad_group.name") or "",
        ] + metric_values(r),
        "where": None,
    },
    {
        "name": "광고실적",
        "resource": "ad_group_ad",
        "select": [
            "campaign.name", "ad_group.name",
            "ad_group_ad.ad.id", "ad_group_ad.ad.type", "ad_group_ad.status",
        ] + METRIC_FIELDS,
        "headers": ["캠페인", "광고그룹", "광고 ID", "광고 유형", "광고 상태"]
                   + METRIC_HEADERS,
        "row": lambda r: [
            pick(r, "campaign.name") or "",
            pick(r, "ad_group.name") or "",
            str(pick(r, "ad_group_ad.ad.id") or ""),
            pick(r, "ad_group_ad.ad.type") or "",
            STATUS_KO.get(pick(r, "ad_group_ad.status"),
                          pick(r, "ad_group_ad.status") or ""),
        ] + metric_values(r),
        "where": "ad_group_ad.status != 'REMOVED'",
    },
]


def build_query(spec: dict, since: str, until: str,
                by_month: bool = False) -> str:
    select = list(spec["select"])
    if by_month:
        # 월 세그먼트를 넣으면 한 파일에 월별 추이가 담깁니다 (scripts/trend.py)
        select.insert(0, "segments.month")
    where = [f"segments.date BETWEEN '{since}' AND '{until}'"]
    if spec["where"]:
        where.append(spec["where"])
    return (f"SELECT {', '.join(select)} "
            f"FROM {spec['resource']} "
            f"WHERE {' AND '.join(where)}")


def resolve_dates(args) -> tuple[str, str]:
    today = dt.date.today()
    until = args.until or (today - dt.timedelta(days=1)).isoformat()
    if args.all_time:
        # Google Ads 는 2000년 이전 데이터를 반환하지 않으므로 넉넉히 잡습니다.
        since = "2015-01-01"
    elif args.since:
        since = args.since
    else:
        since = (dt.date.fromisoformat(until)
                 - dt.timedelta(days=args.days - 1)).isoformat()
    return since, until


def main() -> int:
    ap = argparse.ArgumentParser(description="Google Ads API 실적 리포트 다운로드")
    ap.add_argument("--days", type=int, default=90, help="최근 N일 (기본 90)")
    ap.add_argument("--since", help="시작일 YYYY-MM-DD")
    ap.add_argument("--until", help="종료일 YYYY-MM-DD (기본: 어제)")
    ap.add_argument("--all-time", action="store_true", help="계정 전체 기간")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "raw"))
    ap.add_argument("--check", action="store_true",
                    help="인증과 계정 접근만 확인하고 종료")
    ap.add_argument("--by-month", action="store_true",
                    help="월 세그먼트를 넣어 월별 추이까지 받습니다 "
                         "(scripts/trend.py 로 분석)")
    args = ap.parse_args()

    try:
        client = GoogleAdsClient()
    except CredentialsError as exc:
        print(f"인증 정보 오류\n{exc}", file=sys.stderr)
        return 1

    print(f"계정: {client.customer_id}  API: {client.version}")
    if client.login_customer_id:
        print(f"MCC : {client.login_customer_id}")

    if args.check:
        try:
            rows = client.search(
                "SELECT customer.id, customer.descriptive_name, "
                "customer.currency_code, customer.time_zone FROM customer LIMIT 1")
        except (CredentialsError, ApiError) as exc:
            print(f"\n접근 실패\n{exc}", file=sys.stderr)
            return 1
        if not rows:
            print("응답이 비어 있습니다. 고객 ID를 확인하세요.", file=sys.stderr)
            return 1
        r = rows[0]
        print(f"\n접근 확인됨: {pick(r, 'customer.descriptive_name')} "
              f"({pick(r, 'customer.currency_code')}, "
              f"{pick(r, 'customer.time_zone')})")
        return 0

    since, until = resolve_dates(args)
    print(f"기간: {since} ~ {until}\n")

    os.makedirs(args.out, exist_ok=True)
    tag = f"{since.replace('-', '')}-{until.replace('-', '')}"
    total = 0

    for spec in REPORTS:
        query = build_query(spec, since, until, args.by_month)
        try:
            rows = client.search(query)
        except (CredentialsError, ApiError) as exc:
            print(f"  [{spec['name']}] 실패: {exc}", file=sys.stderr)
            return 1

        headers = (["월"] + spec["headers"]) if args.by_month else spec["headers"]
        path = os.path.join(args.out, f"{spec['name']}_{tag}.csv")
        with open(path, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(headers)
            for row in rows:
                line = spec["row"](row)
                if args.by_month:
                    line = [pick(row, "segments.month") or ""] + line
                w.writerow(line)
        total += len(rows)
        print(f"  {spec['name']:8s} {len(rows):6d}행  →  {os.path.basename(path)}")

    print(f"\n총 {total}행 저장. 이어서 실행하세요:")
    print("  python3 scripts/analyze.py")
    print("  python3 scripts/search_terms.py")
    if args.by_month:
        print("  python3 scripts/trend.py            # 월별 추이")
        print("  python3 scripts/analyze.py --since 2024-09   # 기간 한정 분석")
    else:
        print("\n월별 추이를 보려면 --by-month 를 붙여 다시 받으세요.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
