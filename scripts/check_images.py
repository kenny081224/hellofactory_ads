#!/usr/bin/env python3
"""이미지 애셋이 Google Ads 규격에 맞는지 검사합니다.

외부 라이브러리 없이 파일 헤더에서 크기를 직접 읽습니다 (PNG/JPEG/GIF/WebP).

사용법:
    python3 scripts/check_images.py
    python3 scripts/check_images.py assets/new
    python3 scripts/check_images.py ~/사진/*.jpg
"""

from __future__ import annotations

import argparse
import glob
import os
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAX_BYTES = 5120 * 1024          # 5120KB
RATIOS = [
    ("1:1 정사각형", 1.0, (300, 300), (1200, 1200)),
    ("1.91:1 가로형", 1.91, (600, 314), (1200, 628)),
    ("4:5 세로형", 0.8, (480, 600), (960, 1200)),
]
RATIO_TOLERANCE = 0.03           # 3% 오차까지 허용


# ------------------------------------------------------------ 크기 읽기

def png_size(head: bytes):
    if head[:8] == b"\x89PNG\r\n\x1a\n" and head[12:16] == b"IHDR":
        return struct.unpack(">II", head[16:24])
    return None


def gif_size(head: bytes):
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return struct.unpack("<HH", head[6:10])
    return None


def webp_size(head: bytes):
    if head[:4] != b"RIFF" or head[8:12] != b"WEBP":
        return None
    fmt = head[12:16]
    if fmt == b"VP8X":
        w = int.from_bytes(head[24:27], "little") + 1
        h = int.from_bytes(head[27:30], "little") + 1
        return w, h
    if fmt == b"VP8 ":
        return struct.unpack("<HH", head[26:30])
    if fmt == b"VP8L":
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def jpeg_size(path: str):
    with open(path, "rb") as fh:
        if fh.read(2) != b"\xff\xd8":
            return None
        while True:
            byte = fh.read(1)
            while byte and byte != b"\xff":
                byte = fh.read(1)
            marker = fh.read(1)
            while marker == b"\xff":
                marker = fh.read(1)
            if not marker:
                return None
            code = marker[0]
            if code in (0xD8, 0xD9) or 0xD0 <= code <= 0xD7:
                continue
            length = fh.read(2)
            if len(length) < 2:
                return None
            size = struct.unpack(">H", length)[0]
            # SOF0~SOF15 (DHT/JPG/DAC 제외)
            if 0xC0 <= code <= 0xCF and code not in (0xC4, 0xC8, 0xCC):
                data = fh.read(5)
                if len(data) < 5:
                    return None
                h, w = struct.unpack(">HH", data[1:5])
                return w, h
            fh.seek(size - 2, os.SEEK_CUR)


def image_size(path: str):
    try:
        with open(path, "rb") as fh:
            head = fh.read(32)
    except OSError:
        return None
    for reader in (png_size, gif_size, webp_size):
        size = reader(head)
        if size:
            return size
    if head[:2] == b"\xff\xd8":
        return jpeg_size(path)
    return None


# ------------------------------------------------------------ 검사

def match_ratio(w: int, h: int):
    actual = w / h if h else 0
    for name, target, min_wh, rec_wh in RATIOS:
        if abs(actual - target) / target <= RATIO_TOLERANCE:
            return name, min_wh, rec_wh
    return None, None, None


def check(path: str) -> tuple[str, list[str]]:
    problems = []
    size = image_size(path)
    if not size:
        return "unknown", ["이미지 크기를 읽지 못했습니다 "
                           "(JPG/PNG/GIF/WebP 만 지원)"]
    w, h = size
    bytes_ = os.path.getsize(path)
    if bytes_ > MAX_BYTES:
        problems.append(f"용량 {bytes_ / 1024:,.0f}KB — 최대 5,120KB")

    name, min_wh, rec_wh = match_ratio(w, h)
    if name is None:
        problems.append(f"{w}×{h} — 지원 비율(1:1, 1.91:1, 4:5)이 아닙니다. "
                        f"해당 비율로 잘라서 올리세요")
        return f"{w}×{h}", problems
    if w < min_wh[0] or h < min_wh[1]:
        problems.append(f"{w}×{h} — {name} 최소 크기 "
                        f"{min_wh[0]}×{min_wh[1]} 미만이라 거부됩니다")
    elif w < rec_wh[0] or h < rec_wh[1]:
        problems.append(f"{w}×{h} — 업로드는 되지만 권장 크기 "
                        f"{rec_wh[0]}×{rec_wh[1]} 보다 작습니다")
    return f"{name} {w}×{h}", problems


def main() -> int:
    ap = argparse.ArgumentParser(description="이미지 애셋 규격 검사")
    ap.add_argument("paths", nargs="*",
                    default=[os.path.join(ROOT, "assets")],
                    help="검사할 폴더 또는 파일 (기본: assets/)")
    args = ap.parse_args()

    files = []
    for p in args.paths:
        p = os.path.expanduser(p)
        if os.path.isdir(p):
            for root, _dirs, names in os.walk(p):
                files += [os.path.join(root, n) for n in names
                          if n.lower().endswith((".jpg", ".jpeg", ".png",
                                                 ".gif", ".webp"))]
        else:
            files += glob.glob(p)
    files = sorted(set(files))

    if not files:
        print("검사할 이미지가 없습니다.\n"
              "assets/current/ 에 지금 쓰는 이미지를, assets/new/ 에 새 이미지를 "
              "넣고 다시 실행하세요.\n규격은 docs/assets.md 3번 참고.")
        return 1

    ok = 0
    found_ratios = set()
    for path in files:
        rel = os.path.relpath(path, ROOT)
        desc, problems = check(path)
        if not problems:
            ok += 1
            found_ratios.add(desc.split()[0])
            print(f"  OK    {desc:22s} {rel}")
        else:
            print(f"  문제  {desc:22s} {rel}")
            for msg in problems:
                print(f"        - {msg}")

    print(f"\n{len(files)}개 중 {ok}개 통과")
    missing = {"1:1", "1.91:1"} - {r.split()[0] for r in found_ratios}
    if missing:
        print(f"권장: {', '.join(sorted(missing))} 비율 이미지도 준비하세요. "
              f"두 비율을 모두 올려야 노출 지면이 넓어집니다.")
    print("촬영 가이드(어떤 컷이 잘 먹히는지)는 docs/assets.md 3번을 보세요.")
    return 0 if ok == len(files) else 1


if __name__ == "__main__":
    raise SystemExit(main())
