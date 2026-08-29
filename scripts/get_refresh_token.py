#!/usr/bin/env python3
"""Google Ads API 용 refresh token 을 발급받습니다.

이 스크립트는 **본인 PC에서** 실행하세요. 브라우저가 열려 구글 로그인 후
동의하면 refresh token 이 발급되고 config/credentials.env 에 저장됩니다.

사전 준비 (docs/google_ads_api.md 참고):
    Google Cloud Console 에서 'OAuth 클라이언트 ID' 를 '데스크톱 앱' 유형으로
    만들어 클라이언트 ID와 시크릿을 준비하세요.

사용법:
    python3 scripts/get_refresh_token.py
    python3 scripts/get_refresh_token.py --client-id XXX --client-secret YYY
"""

from __future__ import annotations

import argparse
import http.server
import os
import secrets
import socket
import sys
import threading
import urllib.parse
import webbrowser

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, "config", "credentials.env")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/adwords"

_result: dict = {}


class Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _result.update({k: v[0] for k, v in params.items()})
        body = ("<html><head><meta charset='utf-8'></head><body "
                "style='font-family:sans-serif;padding:40px'>"
                "<h2>인증이 완료되었습니다.</h2>"
                "<p>이 창을 닫고 터미널로 돌아가세요.</p></body></html>")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(body.encode("utf-8"))

    def log_message(self, *args):
        pass


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def save_env(values: dict) -> None:
    existing = {}
    if os.path.isfile(ENV_FILE):
        with open(ENV_FILE, encoding="utf-8") as fh:
            for line in fh:
                if "=" in line and not line.strip().startswith("#"):
                    k, _, v = line.partition("=")
                    existing[k.strip()] = v.strip()
    existing.update(values)
    os.makedirs(os.path.dirname(ENV_FILE), exist_ok=True)
    with open(ENV_FILE, "w", encoding="utf-8") as fh:
        fh.write("# Google Ads API 인증 정보 — 절대 커밋하지 마세요\n")
        fh.write("# (.gitignore 에 등록되어 있습니다)\n")
        for k, v in existing.items():
            fh.write(f"{k}={v}\n")
    os.chmod(ENV_FILE, 0o600)


def main() -> int:
    ap = argparse.ArgumentParser(description="Google Ads refresh token 발급")
    ap.add_argument("--client-id")
    ap.add_argument("--client-secret")
    ap.add_argument("--no-browser", action="store_true",
                    help="브라우저를 자동으로 열지 않고 URL만 출력")
    args = ap.parse_args()

    client_id = args.client_id or os.environ.get("GOOGLE_ADS_CLIENT_ID") \
        or input("OAuth 클라이언트 ID: ").strip()
    client_secret = args.client_secret or os.environ.get("GOOGLE_ADS_CLIENT_SECRET") \
        or input("OAuth 클라이언트 시크릿: ").strip()
    if not client_id or not client_secret:
        print("클라이언트 ID와 시크릿이 필요합니다.", file=sys.stderr)
        return 1

    port = free_port()
    redirect_uri = f"http://localhost:{port}"
    state = secrets.token_urlsafe(16)

    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",       # refresh token 을 확실히 받기 위해 필요
        "state": state,
    })

    server = http.server.HTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.handle_request, daemon=True).start()

    print("\n아래 주소를 브라우저에서 열고 광고 계정에 접근 권한이 있는 "
          "구글 계정으로 로그인하세요.\n")
    print(url + "\n")
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    print("브라우저에서 동의가 끝나기를 기다리는 중...")

    server.socket.settimeout(300)
    for _ in range(300):
        if _result:
            break
        threading.Event().wait(1)

    if "error" in _result:
        print(f"\n인증 거부됨: {_result['error']}", file=sys.stderr)
        return 1
    if "code" not in _result:
        print("\n제한 시간 안에 인증이 완료되지 않았습니다.", file=sys.stderr)
        return 1
    if _result.get("state") != state:
        print("\nstate 값이 일치하지 않습니다. 다시 시도하세요.", file=sys.stderr)
        return 1

    resp = requests.post(TOKEN_URL, data={
        "code": _result["code"],
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }, timeout=30)
    if resp.status_code != 200:
        print(f"\n토큰 교환 실패 ({resp.status_code}): {resp.text[:500]}",
              file=sys.stderr)
        return 1

    token = resp.json().get("refresh_token")
    if not token:
        print("\nrefresh token 이 응답에 없습니다. 이미 동의한 적이 있는 "
              "계정이라면 https://myaccount.google.com/permissions 에서 "
              "앱 접근 권한을 삭제한 뒤 다시 실행하세요.", file=sys.stderr)
        return 1

    save_env({
        "GOOGLE_ADS_CLIENT_ID": client_id,
        "GOOGLE_ADS_CLIENT_SECRET": client_secret,
        "GOOGLE_ADS_REFRESH_TOKEN": token,
    })
    print(f"\nrefresh token 발급 완료 → {ENV_FILE}")
    print("\n남은 항목을 같은 파일에 추가하세요.")
    print("  GOOGLE_ADS_DEVELOPER_TOKEN=...      (Google Ads > 도구 > API 센터)")
    print("  GOOGLE_ADS_CUSTOMER_ID=1234567890   (하이픈 없이)")
    print("  GOOGLE_ADS_LOGIN_CUSTOMER_ID=...    (MCC 로 접근할 때만)")
    print("\n그다음: python3 scripts/fetch_ads.py --check")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
