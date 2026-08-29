"""Google Ads API (REST) 최소 클라이언트.

무거운 google-ads 파이썬 패키지 대신 REST 엔드포인트를 직접 호출합니다.
필요한 외부 의존성은 requests 하나뿐입니다.

인증 정보는 아래 순서로 찾습니다.
    1. 환경변수
    2. config/credentials.env  (KEY=VALUE 형식, .gitignore 로 커밋 제외됨)

필요한 값:
    GOOGLE_ADS_CLIENT_ID
    GOOGLE_ADS_CLIENT_SECRET
    GOOGLE_ADS_REFRESH_TOKEN
    GOOGLE_ADS_DEVELOPER_TOKEN
    GOOGLE_ADS_CUSTOMER_ID          하이픈 없는 10자리 (광고 계정)
    GOOGLE_ADS_LOGIN_CUSTOMER_ID    (선택) MCC 를 통해 접근할 때만
    GOOGLE_ADS_API_VERSION          (선택) 기본값 v22
"""

from __future__ import annotations

import os

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, "config", "credentials.env")

TOKEN_URL = "https://oauth2.googleapis.com/token"
API_HOST = "https://googleads.googleapis.com"
# v21 은 2026-08-05 에 종료되었습니다. 더 최신 버전을 쓰려면
# GOOGLE_ADS_API_VERSION 환경변수로 지정하세요.
DEFAULT_VERSION = "v22"

REQUIRED = ["GOOGLE_ADS_CLIENT_ID", "GOOGLE_ADS_CLIENT_SECRET",
            "GOOGLE_ADS_REFRESH_TOKEN", "GOOGLE_ADS_DEVELOPER_TOKEN",
            "GOOGLE_ADS_CUSTOMER_ID"]


class CredentialsError(Exception):
    pass


class ApiError(Exception):
    pass


def load_env() -> dict:
    """환경변수 + config/credentials.env 를 합쳐서 반환 (환경변수 우선)."""
    values = {}
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                values[key.strip()] = val.strip().strip('"').strip("'")
    for key in list(values) + REQUIRED + ["GOOGLE_ADS_LOGIN_CUSTOMER_ID",
                                          "GOOGLE_ADS_API_VERSION"]:
        if os.environ.get(key):
            values[key] = os.environ[key]

    missing = [k for k in REQUIRED if not values.get(k)]
    if missing:
        raise CredentialsError(
            "다음 인증 정보가 없습니다: " + ", ".join(missing) + "\n"
            f"환경변수로 넣거나 {ENV_FILE} 파일에 KEY=VALUE 형식으로 저장하세요.\n"
            "발급 방법은 docs/google_ads_api.md 를 참고하세요.")
    return values


def digits(customer_id: str) -> str:
    return "".join(ch for ch in str(customer_id) if ch.isdigit())


class GoogleAdsClient:
    def __init__(self, env: dict | None = None):
        self.env = env or load_env()
        self.version = self.env.get("GOOGLE_ADS_API_VERSION") or DEFAULT_VERSION
        self.customer_id = digits(self.env["GOOGLE_ADS_CUSTOMER_ID"])
        login = self.env.get("GOOGLE_ADS_LOGIN_CUSTOMER_ID")
        self.login_customer_id = digits(login) if login else None
        self._token = None

    # ------------------------------------------------------------ 인증
    def access_token(self) -> str:
        if self._token:
            return self._token
        resp = requests.post(TOKEN_URL, data={
            "client_id": self.env["GOOGLE_ADS_CLIENT_ID"],
            "client_secret": self.env["GOOGLE_ADS_CLIENT_SECRET"],
            "refresh_token": self.env["GOOGLE_ADS_REFRESH_TOKEN"],
            "grant_type": "refresh_token",
        }, timeout=30)
        if resp.status_code != 200:
            raise CredentialsError(
                f"액세스 토큰 발급 실패 ({resp.status_code}): {resp.text[:500]}\n"
                "refresh token 이 만료되었거나 클라이언트 ID/시크릿이 다를 수 있습니다. "
                "python3 scripts/get_refresh_token.py 로 다시 발급하세요.")
        self._token = resp.json()["access_token"]
        return self._token

    def _headers(self) -> dict:
        h = {
            "Authorization": f"Bearer {self.access_token()}",
            "developer-token": self.env["GOOGLE_ADS_DEVELOPER_TOKEN"],
            "Content-Type": "application/json",
        }
        if self.login_customer_id:
            h["login-customer-id"] = self.login_customer_id
        return h

    # ------------------------------------------------------------ 조회
    def search(self, query: str) -> list[dict]:
        """GAQL 쿼리를 실행하고 결과 행 목록을 반환."""
        url = (f"{API_HOST}/{self.version}/customers/{self.customer_id}"
               f"/googleAds:searchStream")
        resp = requests.post(url, headers=self._headers(),
                             json={"query": query}, timeout=180)
        if resp.status_code == 404:
            raise ApiError(
                f"API 버전 {self.version} 을 찾을 수 없습니다 (404). "
                "해당 버전이 종료되었을 수 있습니다.\n"
                "GOOGLE_ADS_API_VERSION 환경변수로 최신 버전을 지정하세요 "
                "(예: v23, v24).")
        if resp.status_code != 200:
            raise ApiError(f"조회 실패 ({resp.status_code}): {resp.text[:1500]}")

        payload = resp.json()
        chunks = payload if isinstance(payload, list) else [payload]
        rows = []
        for chunk in chunks:
            rows.extend(chunk.get("results", []))
        return rows


# ------------------------------------------------------------ 응답 파싱

def _camel(snake: str) -> str:
    head, *rest = snake.split("_")
    return head + "".join(p.title() for p in rest)


def pick(row: dict, path: str):
    """'metrics.cost_micros' 같은 GAQL 경로로 응답 JSON에서 값을 꺼냅니다.

    응답은 camelCase 이므로 변환해서 접근합니다.
    """
    node = row
    for part in path.split("."):
        if not isinstance(node, dict):
            return None
        key = _camel(part)
        if key in node:
            node = node[key]
        elif part in node:
            node = node[part]
        else:
            return None
    return node


def micros(value) -> float:
    """cost_micros / average_cpc 등 마이크로 단위를 원 단위로."""
    try:
        return float(value) / 1_000_000.0
    except (TypeError, ValueError):
        return 0.0


def number(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


MATCH_TYPE_KO = {
    "EXACT": "정확 검색",
    "PHRASE": "구문 검색",
    "BROAD": "광범위 검색",
}

STATUS_KO = {
    "ENABLED": "사용 설정됨",
    "PAUSED": "일시중지됨",
    "REMOVED": "삭제됨",
}
