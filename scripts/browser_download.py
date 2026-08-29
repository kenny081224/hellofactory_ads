#!/usr/bin/env python3
"""브라우저에서 내려받는 Google Ads 리포트를 자동으로 data/raw/ 에 정리합니다.

**본인 PC에서 실행하세요.** 이미 로그인된 크롬을 그대로 사용합니다.

두 가지 모드가 있습니다.

  1) 감시 모드 (기본, 의존성 없음) — 권장
     스크립트가 다운로드 폴더를 지켜보다가, 크롬에서 리포트를 내려받는 즉시
     종류를 판별해 data/raw/ 로 옮기고 "남은 리포트"를 알려줍니다.
     Google Ads 화면이 바뀌어도 절대 깨지지 않습니다.

         python3 scripts/browser_download.py

  2) 자동 모드 (Playwright 필요) — 클릭까지 대신
     이미 켜져 있는 크롬에 붙어서 리포트 화면으로 이동하고 다운로드 버튼까지
     눌러봅니다. Google Ads UI 는 자주 바뀌므로 **베스트 에포트**입니다.
     실패하면 그 화면에서 직접 누르시면 되고, 파일은 감시 모드가 받아냅니다.

         # 크롬을 디버깅 포트와 함께 실행한 뒤 (docs/browser_download.md 참고)
         python3 scripts/browser_download.py --auto

자세한 준비 절차는 docs/browser_download.md 를 보세요.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import shutil
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adslib as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

WANTED = ["campaign", "ad_group", "keyword", "search_term", "ad"]

# Google Ads 리포트 화면. UI 개편으로 경로가 바뀌면 --url 로 덮어쓰거나
# 이 표를 고치세요. 못 찾으면 계정 선택 화면으로 떨어지므로 한 번만 고르면 됩니다.
REPORT_URLS = {
    "campaign":    "https://ads.google.com/aw/campaigns",
    "ad_group":    "https://ads.google.com/aw/adgroups",
    "keyword":     "https://ads.google.com/aw/keywords/search",
    "search_term": "https://ads.google.com/aw/keywords/searchterms",
    "ad":          "https://ads.google.com/aw/ads",
}

# 다운로드 버튼 / CSV 메뉴 항목 후보 (한국어·영어 UI 모두 대응)
DOWNLOAD_BUTTON_HINTS = ["다운로드", "Download"]
CSV_ITEM_HINTS = [".csv", "CSV", "쉼표로 구분된 값"]


def download_dirs(extra: list[str] | None = None) -> list[str]:
    home = os.path.expanduser("~")
    dirs = list(extra or [])
    dirs += [os.path.join(home, "Downloads"), os.path.join(home, "다운로드")]
    return [d for d in dict.fromkeys(dirs) if os.path.isdir(d)]


def snapshot(dirs: list[str]) -> set[str]:
    out = set()
    for d in dirs:
        try:
            for name in os.listdir(d):
                out.add(os.path.join(d, name))
        except OSError:
            continue
    return out


def settled(path: str, wait: float = 1.0) -> bool:
    """파일 크기가 더 이상 변하지 않으면 다운로드 완료로 간주."""
    if path.endswith((".crdownload", ".part", ".tmp")):
        return False
    try:
        size1 = os.path.getsize(path)
        time.sleep(wait)
        return size1 > 0 and os.path.getsize(path) == size1
    except OSError:
        return False


class Collector:
    """새로 생긴 CSV 를 판별해 data/raw/ 로 옮기고 진행 상황을 관리."""

    def __init__(self, out_dir: str, tag: str, move: bool):
        self.out_dir = out_dir
        self.tag = tag
        self.move = move
        self.got: dict[str, str] = {}
        os.makedirs(out_dir, exist_ok=True)

    def offer(self, path: str) -> str | None:
        if not path.lower().endswith((".csv", ".tsv")):
            return None
        if not settled(path):
            return None
        kind = A.classify_report(path)
        if kind is None:
            return None
        try:
            rows = A.load_report(path)
        except (ValueError, OSError):
            return None

        dest = os.path.join(self.out_dir, f"{A.KIND_PREFIX[kind]}_{self.tag}.csv")
        if kind in self.got:
            print(f"    ↻ {A.KIND_PREFIX[kind]} 리포트를 새 파일로 교체합니다")
        (shutil.move if self.move else shutil.copy2)(path, dest)
        self.got[kind] = dest
        print(f"    ✓ {A.KIND_PREFIX[kind]:6s} {len(rows):6d}행  →  "
              f"{os.path.basename(dest)}")
        return kind

    def missing(self) -> list[str]:
        return [k for k in WANTED if k not in self.got]

    def status(self) -> str:
        done = " ".join(A.KIND_PREFIX[k] for k in WANTED if k in self.got) or "없음"
        left = " ".join(A.KIND_PREFIX[k] for k in self.missing()) or "없음"
        return f"  받은 것: {done}\n  남은 것: {left}"


def watch(collector: Collector, dirs: list[str], timeout: float,
          required: list[str]) -> None:
    print(f"\n다운로드 폴더를 지켜봅니다: {', '.join(dirs)}")
    print("크롬에서 리포트를 내려받으세요. 다 받으면 자동으로 끝납니다. "
          "(중단: Ctrl+C)\n")
    print(collector.status())

    before = snapshot(dirs)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(1.5)
        now = snapshot(dirs)
        for path in sorted(now - before):
            if collector.offer(path):
                print(collector.status())
                deadline = time.time() + timeout   # 하나 받을 때마다 시간 연장
        before = now
        if not [k for k in required if k not in collector.got]:
            print("\n필요한 리포트를 모두 받았습니다.")
            return
    print("\n제한 시간이 지나 감시를 종료합니다.")


def run_auto(collector: Collector, dirs: list[str], cdp: str,
             kinds: list[str]) -> bool:
    """이미 열려 있는 크롬에 붙어 리포트 화면으로 이동하고 다운로드를 시도."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("자동 모드에는 Playwright 가 필요합니다:\n"
              "  pip install playwright && playwright install chromium\n"
              "설치 없이 쓰려면 감시 모드(기본)를 사용하세요.", file=sys.stderr)
        return False

    with sync_playwright() as pw:
        try:
            browser = pw.chromium.connect_over_cdp(cdp)
        except Exception as exc:
            print(f"크롬에 연결하지 못했습니다 ({cdp}): {exc}\n"
                  "크롬을 --remote-debugging-port=9222 옵션으로 실행했는지 "
                  "확인하세요. docs/browser_download.md 참고", file=sys.stderr)
            return False

        contexts = browser.contexts
        if not contexts:
            print("열려 있는 크롬 창을 찾지 못했습니다.", file=sys.stderr)
            return False
        ctx = contexts[0]
        page = ctx.pages[0] if ctx.pages else ctx.new_page()

        for kind in kinds:
            url = REPORT_URLS.get(kind)
            if not url:
                continue
            print(f"\n[{A.KIND_PREFIX[kind]}] {url}")
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(4000)
            except Exception as exc:
                print(f"  이동 실패: {exc}")
                continue

            if "signin" in page.url or "accounts.google" in page.url:
                print("  로그인 화면입니다. 크롬에서 로그인한 뒤 다시 실행하세요.")
                return False

            if not click_download(page):
                print("  다운로드 버튼을 찾지 못했습니다. "
                      "이 화면에서 직접 내려받으세요 (감시 모드가 파일을 받습니다).")
            page.wait_for_timeout(3000)
            for path in sorted(snapshot(dirs)):
                collector.offer(path)
    return True


def click_download(page) -> bool:
    """다운로드 버튼 → CSV 메뉴 항목을 눌러봅니다. 성공하면 True."""
    for hint in DOWNLOAD_BUTTON_HINTS:
        for locator in (page.get_by_role("button", name=hint),
                        page.locator(f"[aria-label*='{hint}']")):
            try:
                if locator.count() == 0:
                    continue
                locator.first.click(timeout=5000)
                page.wait_for_timeout(1200)
            except Exception:
                continue
            for item in CSV_ITEM_HINTS:
                try:
                    entry = page.get_by_text(item, exact=False)
                    if entry.count() == 0:
                        continue
                    entry.first.click(timeout=5000)
                    print(f"  다운로드 클릭됨 ({hint} → {item})")
                    return True
                except Exception:
                    continue
    return False


def main() -> int:
    ap = argparse.ArgumentParser(
        description="브라우저 다운로드를 data/raw/ 로 자동 정리")
    ap.add_argument("--auto", action="store_true",
                    help="Playwright 로 크롬을 조작해 다운로드까지 시도")
    ap.add_argument("--cdp", default="http://localhost:9222",
                    help="크롬 원격 디버깅 주소 (기본 http://localhost:9222)")
    ap.add_argument("--dir", action="append", default=[],
                    help="감시할 다운로드 폴더 (여러 번 지정 가능)")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "raw"))
    ap.add_argument("--timeout", type=float, default=600,
                    help="새 파일이 없을 때 기다리는 시간(초). 기본 600")
    ap.add_argument("--move", action="store_true", help="복사 대신 이동")
    ap.add_argument("--tag", help="파일명 기간 태그 (기본: 오늘 날짜)")
    ap.add_argument("--only", nargs="*", choices=WANTED,
                    help="이 리포트만 대상으로 (기본: 전부)")
    args = ap.parse_args()

    dirs = download_dirs(args.dir)
    if not dirs:
        print("다운로드 폴더를 찾지 못했습니다. --dir 로 지정하세요.",
              file=sys.stderr)
        return 1

    kinds = args.only or WANTED
    # 광고실적은 없어도 분석이 되므로 필수에서 제외
    required = [k for k in kinds if k != "ad"]
    tag = args.tag or dt.date.today().strftime("%Y%m%d")
    collector = Collector(args.out, tag, args.move)

    if args.auto:
        run_auto(collector, dirs, args.cdp, kinds)

    try:
        watch(collector, dirs, args.timeout, required)
    except KeyboardInterrupt:
        print("\n중단했습니다.")

    print("\n" + collector.status())
    if collector.got:
        print("\n이어서 실행하세요:")
        print("  python3 scripts/analyze.py")
        print("  python3 scripts/search_terms.py")
        return 0
    print("\n받은 파일이 없습니다.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
