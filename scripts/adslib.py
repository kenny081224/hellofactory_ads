"""Google Ads 리포트 CSV 로더 + 지표 계산 (표준 라이브러리만 사용).

Google Ads UI에서 내려받은 CSV는 보통 다음 형태입니다.
    1행: 리포트 이름 (예: "캠페인")
    2행: 기간 (예: "2026. 1. 1.~2026. 8. 28.")
    3행: 실제 컬럼 헤더
    ...데이터...
    마지막: "총계: ..." 요약 행

이 모듈은 헤더 행을 자동 탐지하고, 한국어/영어 컬럼명을 공통 키로 정규화하며,
"1,234" / "₩12,345" / "3.21%" / "--" 같은 값을 숫자로 변환합니다.
"""

from __future__ import annotations

import csv
import io
import os
import re
import unicodedata

# ---------------------------------------------------------------- 컬럼 정규화

# 공통 키 -> 리포트에 등장할 수 있는 컬럼명들(한국어/영어)
COLUMN_ALIASES = {
    "campaign":      ["캠페인", "campaign"],
    "ad_group":      ["광고그룹", "광고 그룹", "ad group"],
    "keyword":       ["검색 키워드", "키워드", "keyword", "search keyword"],
    "search_term":   ["검색어", "검색 유형", "search term", "search terms"],
    "match_type":    ["일치검색유형", "일치 검색 유형", "매치 유형", "검색 유형",
                      "match type", "keyword match type"],
    "ad_id":         ["광고 id", "ad id"],
    "status":        ["캠페인 상태", "광고그룹 상태", "키워드 상태", "상태", "status"],
    "device":        ["기기", "device"],
    "day_of_week":   ["요일", "day of week"],
    "hour":          ["시간대", "hour of day"],
    "placement":     ["게재위치 url", "게재위치url", "placement", "placement url"],
    "landing_page":  ["방문 페이지", "방문페이지", "landing page"],
    "location":      ["일치하는 위치", "matched location"],
    "negative_keyword": ["제외 키워드", "제외키워드", "negative keyword"],
    "ad_headline":   ["광고 제목 1", "headline 1"],
    "asset_group":   ["애셋 그룹", "asset group"],
    # 아래는 접두사가 겹쳐 오인식되기 쉬운 컬럼들 — 반드시 명시해야 합니다
    "campaign_type": ["캠페인 유형", "campaign type"],
    "ad_group_type": ["광고그룹 유형", "ad group type"],
    "keyword_type":  ["키워드 또는 목록"],
    "budget":        ["예산", "budget"],
    "budget_name":   ["예산 이름", "budget name"],
    "budget_type":   ["예산 유형", "budget type"],
    "bid_strategy":  ["입찰 전략 유형", "bid strategy type"],
    "opt_score":     ["최적화 점수", "optimization score"],
    "status_reason": ["상태 이유", "status reason"],
    "final_url":     ["최종 url", "final url"],
    "currency":      ["통화 코드", "currency code"],
    "avg_cost":      ["평균 비용", "avg. cost"],
    "level":         ["수준", "level"],
    "source":        ["출처", "source"],
    "last_updated":  ["최종 업데이트", "last updated"],
    "added_excluded":["추가됨/제외됨", "added/excluded"],
    "orig_conv_value": ["원래 전환 가치", "original conv. value"],
    "date":          ["일", "날짜", "day", "date"],
    "week":          ["주", "week"],
    "month":         ["월", "month"],
    "impressions":   ["노출수", "노출 수", "impr.", "impressions", "impr"],
    "clicks":        ["클릭수", "클릭 수", "clicks"],
    "cost":          ["비용", "cost"],
    "conversions":   ["전환수", "전환 수", "conversions", "conv."],
    "conv_value":    ["전환 가치", "전환가치", "conv. value", "conversion value",
                      "all conv. value"],
    "ctr":           ["ctr", "클릭률", "상호작용 발생률", "상호작용발생률"],
    "interactions":  ["상호작용 수", "상호작용수", "interactions"],
    "value_per_cost":["비용당 전환 가치", "conv. value / cost"],
    "avg_cpc":       ["평균 cpc", "avg. cpc", "avg cpc"],
    "conv_rate":     ["전환율", "conv. rate"],
    "cost_per_conv": ["전환당비용", "전환당 비용", "cost / conv.", "cost per conv."],
    "asset":         ["애셋", "asset", "에셋", "확장 소재", "확장소재"],
    "asset_type":    ["애셋 유형", "애셋유형", "asset type", "에셋 유형"],
    "field_type":    ["필드 유형", "필드유형", "field type"],
    "performance":   ["실적", "애셋 실적", "performance", "performance label",
                      "asset performance"],
    "impr_share":    ["검색 노출 점유율", "검색노출점유율", "search impr. share"],
    "lost_is_rank":  ["검색 손실 노출 점유율(순위)", "search lost is (rank)"],
    "lost_is_budget":["검색 손실 노출 점유율(예산)", "search lost is (budget)"],
    "top_is":        ["검색 페이지 상단 노출 점유율", "search top is"],
}

# 숫자로 변환할 공통 키
NUMERIC_KEYS = {
    "impressions", "clicks", "cost", "conversions", "conv_value", "ctr",
    "interactions", "value_per_cost",
    "avg_cpc", "conv_rate", "cost_per_conv", "impr_share", "lost_is_rank",
    "lost_is_budget", "top_is",
}

_ALIAS_LOOKUP = {}
for _key, _names in COLUMN_ALIASES.items():
    for _n in _names:
        _ALIAS_LOOKUP[_n] = _key


def _norm_header(text: str) -> str:
    """헤더 문자열을 비교 가능한 형태로 정리."""
    text = unicodedata.normalize("NFKC", text or "")
    text = text.replace("﻿", "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    return text


# 접두사 일치는 긴 별칭부터 검사해야 "캠페인 유형"이 "캠페인"으로 새지 않습니다.
_ALIASES_BY_LENGTH = sorted(_ALIAS_LOOKUP.items(), key=lambda kv: -len(kv[0]))


def normalize_column(name: str) -> str:
    """리포트 컬럼명을 공통 키로. 매칭 실패 시 정리된 원본을 반환."""
    n = _norm_header(name)
    if n in _ALIAS_LOOKUP:
        return _ALIAS_LOOKUP[n]
    # 부분 일치 (예: "전환수 (모든 전환)" -> conversions)
    for alias, key in _ALIASES_BY_LENGTH:
        if n.startswith(alias) and len(alias) >= 3:
            return key
    return n


# ------------------------------------------------------------------ 값 파싱

_NUM_RE = re.compile(r"-?[\d.]+")


def parse_number(raw) -> float:
    """'1,234' / '₩12,345' / '3.21%' / '--' / '' -> float."""
    if raw is None:
        return 0.0
    if isinstance(raw, (int, float)):
        return float(raw)
    s = unicodedata.normalize("NFKC", str(raw)).strip()
    if s in ("", "--", "-", "—", "없음", "N/A", "n/a"):
        return 0.0
    is_pct = "%" in s
    s = s.replace(",", "").replace("₩", "").replace("KRW", "").replace("%", "")
    s = s.replace("원", "").strip()
    m = _NUM_RE.search(s)
    if not m:
        return 0.0
    val = float(m.group(0))
    return val / 100.0 if is_pct else val


# ------------------------------------------------------------------ 파일 읽기

def _read_text(path: str) -> str:
    """Google Ads CSV는 UTF-8-BOM 또는 UTF-16(탭 구분)일 수 있음."""
    with open(path, "rb") as fh:
        raw = fh.read()
    for enc in ("utf-8-sig", "utf-16", "cp949"):
        try:
            text = raw.decode(enc)
        except (UnicodeDecodeError, UnicodeError):
            continue
        if "\x00" in text:
            continue
        return text
    return raw.decode("utf-8", errors="replace")


def _sniff_delimiter(sample: str) -> str:
    first = sample.splitlines()[0] if sample.splitlines() else ""
    return "\t" if first.count("\t") > first.count(",") else ","


def _looks_like_header(row) -> bool:
    """알려진 지표 컬럼이 2개 이상 있으면 헤더 행으로 간주."""
    keys = {normalize_column(c) for c in row}
    known = keys & (NUMERIC_KEYS | {"campaign", "ad_group", "keyword", "search_term"})
    return len(known) >= 2


def load_report(path: str) -> list[dict]:
    """Google Ads 리포트 CSV -> 정규화된 dict 리스트."""
    text = _read_text(path)
    delim = _sniff_delimiter(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))

    header_idx = None
    for i, row in enumerate(rows[:12]):
        if _looks_like_header(row):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError(f"{path}: 컬럼 헤더를 찾지 못했습니다. "
                         f"Google Ads에서 내려받은 원본 CSV인지 확인하세요.")

    header = [normalize_column(c) for c in rows[header_idx]]
    out = []
    for row in rows[header_idx + 1:]:
        if not any(str(c).strip() for c in row):
            continue
        # "총계: 계정" / "전체: 캠페인" 같은 요약 행 제외.
        # 요약 라벨이 첫 칸이 아닌 리포트(기기 등)도 있어 앞쪽 칸을 함께 봅니다.
        head_cells = [_norm_header(c) for c in row[:6]]
        if any(c.startswith("총계") or c.startswith("전체:") or c.startswith("전체 :")
               or c.startswith("total") for c in head_cells):
            continue
        rec = {}
        for key, val in zip(header, row):
            rec[key] = parse_number(val) if key in NUMERIC_KEYS else str(val).strip()
        for key in NUMERIC_KEYS:
            rec.setdefault(key, 0.0)
        out.append(rec)
    return out


def load_dir(directory: str, pattern: str) -> list[dict]:
    """디렉터리에서 파일명에 pattern이 포함된 모든 CSV를 합쳐서 로드."""
    if not os.path.isdir(directory):
        return []
    merged = []
    for fname in sorted(os.listdir(directory)):
        if not fname.lower().endswith((".csv", ".tsv")):
            continue
        if pattern.lower() not in fname.lower():
            continue
        merged.extend(load_report(os.path.join(directory, fname)))
    return merged


# -------------------------------------------------------------- 지표 계산

def aggregate(rows: list[dict], *keys: str) -> dict:
    """지정한 키 조합으로 지표를 합산."""
    buckets: dict = {}
    for r in rows:
        k = tuple(r.get(key, "") for key in keys)
        b = buckets.setdefault(k, {
            "impressions": 0.0, "clicks": 0.0, "cost": 0.0,
            "conversions": 0.0, "conv_value": 0.0,
        })
        for metric in b:
            b[metric] += r.get(metric, 0.0)
    for k, b in buckets.items():
        for name, key in zip(keys, k):
            b[name] = key
        derive(b)
    return buckets


def derive(m: dict) -> dict:
    """합산된 원지표에서 파생지표(CTR/CPC/CVR/CPA/ROAS)를 계산."""
    impr = m.get("impressions", 0.0)
    clicks = m.get("clicks", 0.0)
    cost = m.get("cost", 0.0)
    conv = m.get("conversions", 0.0)
    value = m.get("conv_value", 0.0)
    m["ctr"] = clicks / impr if impr else 0.0
    m["avg_cpc"] = cost / clicks if clicks else 0.0
    m["conv_rate"] = conv / clicks if clicks else 0.0
    m["cpa"] = cost / conv if conv else 0.0
    m["roas"] = value / cost if cost else 0.0
    m["value_per_click"] = value / clicks if clicks else 0.0
    return m


# ------------------------------------------------------------------ 출력 보조

def won(v: float) -> str:
    return f"{v:,.0f}원"


def pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def num(v: float) -> str:
    return f"{v:,.0f}" if abs(v - round(v)) < 1e-9 else f"{v:,.1f}"


def md_table(headers: list[str], rows: list[list[str]], align_right=None) -> str:
    align_right = align_right or set()
    sep = ["---:" if i in align_right else "---" for i in range(len(headers))]
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join(sep) + " |"]
    for r in rows:
        lines.append("| " + " | ".join(str(c) for c in r) + " |")
    return "\n".join(lines)


# ------------------------------------------------------------ 기간 파싱

_DATE_RE = re.compile(r"(\d{4})\s*[-./년]\s*(\d{1,2})(?:\s*[-./월]\s*(\d{1,2}))?")


def parse_period(value) -> str | None:
    """리포트의 날짜/월 값을 'YYYY-MM' 로 정규화.

    Google Ads 는 설정에 따라 '2024. 1. 19.', '2024-01-19', '2024년 1월',
    '2024/01' 등 여러 형태로 내려줍니다.
    """
    if value is None:
        return None
    text = unicodedata.normalize("NFKC", str(value)).strip()
    if not text or text in ("--", "-"):
        return None
    m = _DATE_RE.search(text)
    if not m:
        return None
    year, month = int(m.group(1)), int(m.group(2))
    if not 1 <= month <= 12:
        return None
    return f"{year:04d}-{month:02d}"


def row_period(row: dict) -> str | None:
    """행에서 기간(YYYY-MM)을 찾습니다. 일 > 주 > 월 순."""
    for key in ("date", "week", "month"):
        period = parse_period(row.get(key))
        if period:
            return period
    return None


def has_period(rows: list[dict]) -> bool:
    return any(row_period(r) for r in rows)


def filter_period(rows: list[dict], since: str | None,
                  until: str | None) -> list[dict]:
    """'YYYY-MM' 기준으로 행을 걸러냅니다. 날짜가 없는 행은 그대로 통과."""
    if not since and not until:
        return rows
    out = []
    for r in rows:
        p = row_period(r)
        if p is None:
            out.append(r)
            continue
        if since and p < since[:7]:
            continue
        if until and p > until[:7]:
            continue
        out.append(r)
    return out


# -------------------------------------------------- 리포트 종류 자동 판별

# 실적 집계에 쓰는 리포트
REPORT_KINDS = ("search_term", "keyword", "asset", "asset_group", "ad",
                "ad_group", "campaign")
# 세그먼트/참고 리포트 — 합산하면 중복 집계가 되므로 따로 다룹니다
SEGMENT_KINDS = ("device", "schedule", "placement", "landing_page",
                 "location", "negative")
ALL_KINDS = REPORT_KINDS + SEGMENT_KINDS

# 파일명으로 판별할 때 쓰는 단어 (구체적인 것부터 검사)
FILENAME_PATTERNS = {
    "negative":     ["제외 키워드", "제외키워드", "negative"],
    "landing_page": ["방문 페이지", "방문페이지", "landing page"],
    "location":     ["일치하는 위치", "위치 보고서", "location"],
    "placement":    ["게재위치", "placement"],
    "schedule":     ["광고 일정", "일일 및 시간", "ad schedule", "hour"],
    "device":       ["기기 보고서", "device"],
    "search_term":  ["searchterm", "search_term", "search-term", "검색어"],
    "asset_group":  ["애셋 그룹", "애셋그룹", "asset group"],
    "asset":        ["애셋", "asset", "에셋", "확장 소재", "확장소재", "extension"],
    "ad_group":     ["adgroup", "ad_group", "ad-group", "광고그룹"],
    "keyword":      ["keyword", "키워드"],
    "campaign":     ["campaign", "캠페인"],
    "ad":           ["광고 보고서", "광고실적", "rsa", "responsive", "ads_", "_ads"],
}

# 파일명 검사 순서 (구체적인 것부터)
_FILENAME_ORDER = ["negative", "landing_page", "placement", "location",
                   "schedule", "device", "search_term", "asset_group", "asset",
                   "ad_group", "keyword", "campaign", "ad"]


def kind_from_filename(fname: str) -> str | None:
    low = os.path.basename(fname).lower()
    for kind in _FILENAME_ORDER:
        if any(p in low for p in FILENAME_PATTERNS[kind]):
            return kind
    return None


def kind_from_columns(path: str) -> str | None:
    """파일 내용(컬럼 구성)으로 리포트 종류를 판별.

    파일명이 'report.csv' 처럼 무의미해도 동작하므로, 브라우저에서 막 내려받은
    파일을 분류할 때 사용합니다.
    """
    try:
        text = _read_text(path)
    except OSError:
        return None
    delim = _sniff_delimiter(text)
    rows = list(csv.reader(io.StringIO(text), delimiter=delim))
    for row in rows[:12]:
        if not _looks_like_header(row):
            continue
        cols = {normalize_column(c) for c in row}
        if not cols & set(NUMERIC_KEYS):
            continue
        # 세그먼트/참고 리포트를 먼저 걸러냅니다 (합산하면 중복 집계)
        if "negative_keyword" in cols:
            return "negative"
        if "landing_page" in cols:
            return "landing_page"
        if "location" in cols:
            return "location"
        if "placement" in cols:
            return "placement"
        if "day_of_week" in cols or "hour" in cols:
            return "schedule"
        if "device" in cols:
            return "device"
        if "search_term" in cols:
            return "search_term"
        if "keyword" in cols:
            return "keyword"
        if "asset_group" in cols:
            return "asset_group"
        if "asset" in cols or "asset_type" in cols:
            return "asset"
        if "ad_headline" in cols or "ad_id" in cols:
            return "ad"
        if "ad_group" in cols:
            return "ad_group"
        if "campaign" in cols:
            return "campaign"
        return None
    return None


def classify_report(path: str) -> str | None:
    """파일명 → 내용 순으로 리포트 종류를 판별."""
    return kind_from_filename(path) or kind_from_columns(path)


# 종류별 한국어 파일명 접두사 (fetch_ads.py 가 만드는 이름과 동일)
KIND_PREFIX = {
    "campaign": "캠페인",
    "ad_group": "광고그룹",
    "keyword": "키워드",
    "search_term": "검색어",
    "ad": "광고",
    "asset": "애셋",
    "asset_group": "애셋그룹",
    "device": "기기",
    "schedule": "광고일정",
    "placement": "게재위치",
    "landing_page": "방문페이지",
    "location": "위치",
    "negative": "제외키워드",
}
