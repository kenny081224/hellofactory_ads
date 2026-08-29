#!/usr/bin/env python3
"""브라우저로 내려받은 Google Ads 리포트 CSV를 data/raw/ 로 정리해 넣습니다.

파일 이름이 'report (3).csv' 처럼 무의미해도 **컬럼 구성을 읽어** 어떤 리포트인지
판별하고, 분석 스크립트가 인식하는 이름으로 바꿔 저장합니다.

사용법:
    python3 scripts/import_downloads.py                    # 다운로드 폴더에서 최근 파일
    python3 scripts/import_downloads.py ~/Downloads/*.csv  # 파일 직접 지정
    python3 scripts/import_downloads.py --hours 6          # 최근 6시간 내 파일만
    python3 scripts/import_downloads.py --move             # 복사가 아니라 이동
"""

from __future__ import annotations

import argparse
import datetime as dt
import glob
import os
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import adslib as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_download_dirs() -> list[str]:
    home = os.path.expanduser("~")
    candidates = [
        os.path.join(home, "Downloads"),
        os.path.join(home, "다운로드"),
        os.path.join(home, "Desktop"),
    ]
    return [d for d in candidates if os.path.isdir(d)]


def collect(args) -> list[str]:
    if args.paths:
        files = []
        for pattern in args.paths:
            files.extend(glob.glob(os.path.expanduser(pattern)))
        return sorted(set(files))

    cutoff = dt.datetime.now().timestamp() - args.hours * 3600
    files = []
    for d in default_download_dirs():
        for name in os.listdir(d):
            if not name.lower().endswith((".csv", ".tsv")):
                continue
            path = os.path.join(d, name)
            try:
                if os.path.getmtime(path) >= cutoff:
                    files.append(path)
            except OSError:
                continue
    return sorted(files, key=os.path.getmtime)


def main() -> int:
    ap = argparse.ArgumentParser(
        description="내려받은 Google Ads 리포트를 data/raw/ 로 정리")
    ap.add_argument("paths", nargs="*", help="파일 경로 또는 glob 패턴")
    ap.add_argument("--hours", type=float, default=24,
                    help="경로를 지정하지 않았을 때 검사할 최근 시간 (기본 24)")
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "raw"))
    ap.add_argument("--move", action="store_true", help="복사 대신 이동")
    ap.add_argument("--tag", help="파일명에 붙일 기간 태그 (기본: 오늘 날짜)")
    args = ap.parse_args()

    files = collect(args)
    if not files:
        where = ", ".join(default_download_dirs()) or "(다운로드 폴더 없음)"
        print(f"대상 파일이 없습니다. 검사 위치: {where}\n"
              f"파일 경로를 직접 넘겨도 됩니다: "
              f"python3 scripts/import_downloads.py ~/Downloads/*.csv")
        return 1

    os.makedirs(args.out, exist_ok=True)
    tag = args.tag or dt.date.today().strftime("%Y%m%d")
    seen: dict[str, int] = {}
    moved = 0

    for path in files:
        kind = A.classify_report(path)
        if kind is None:
            print(f"  [건너뜀] {os.path.basename(path)} — "
                  f"Google Ads 리포트로 보이지 않습니다")
            continue
        try:
            rows = A.load_report(path)
        except ValueError as exc:
            print(f"  [건너뜀] {os.path.basename(path)} — {exc}")
            continue

        seen[kind] = seen.get(kind, 0) + 1
        suffix = "" if seen[kind] == 1 else f"_{seen[kind]}"
        dest = os.path.join(args.out, f"{A.KIND_PREFIX[kind]}_{tag}{suffix}.csv")
        (shutil.move if args.move else shutil.copy2)(path, dest)
        moved += 1
        print(f"  {A.KIND_PREFIX[kind]:6s} {len(rows):5d}행  "
              f"{os.path.basename(path)}  →  {os.path.basename(dest)}")

    if not moved:
        print("\n옮긴 파일이 없습니다.")
        return 1

    missing = [A.KIND_PREFIX[k] for k in ("campaign", "keyword", "search_term")
               if k not in seen]
    print(f"\n{moved}개 파일을 {args.out} 에 넣었습니다.")
    if missing:
        print(f"아직 없는 리포트: {', '.join(missing)}  "
              f"(검색어 리포트가 없으면 제외 키워드 분석을 못 합니다)")
    print("\n이어서 실행하세요:")
    print("  python3 scripts/analyze.py")
    print("  python3 scripts/search_terms.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
