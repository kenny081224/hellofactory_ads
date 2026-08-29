# 브라우저로 리포트 받기

Google Ads API 개발자 토큰 승인이 나기 전까지는 화면에서 리포트를 내려받아야
합니다. 이때 파일 이름이 `report (3).csv` 처럼 나와서 매번 손으로 정리하게 되는데,
그 부분을 스크립트가 대신합니다.

> **먼저 알아둘 것:** 이 저장소의 작업 세션은 클라우드 컨테이너에서 돌기 때문에
> 여러분 PC에 열려 있는 크롬을 직접 조작할 수 없습니다. 아래 스크립트는
> **여러분 PC에서 실행**해서, 이미 로그인된 크롬을 그대로 활용하는 방식입니다.

## 방법 1 — 감시 모드 (권장, 준비물 없음)

터미널에서 이것부터 켜 둡니다.

```bash
cd hellofactory_ads
python3 scripts/browser_download.py
```

```
다운로드 폴더를 지켜봅니다: /Users/you/Downloads
크롬에서 리포트를 내려받으세요. 다 받으면 자동으로 끝납니다. (중단: Ctrl+C)

  받은 것: 없음
  남은 것: 캠페인 광고그룹 키워드 검색어 광고실적
```

이 상태로 두고 크롬에서 평소처럼 리포트를 내려받으면, 파일이 생기는 즉시
**내용을 읽어 어떤 리포트인지 판별**하고 `data/raw/` 로 옮깁니다.
필요한 걸 다 받으면 스스로 종료합니다.

```
    ✓ 캠페인          412행  →  캠페인_20260829.csv
  받은 것: 캠페인
  남은 것: 광고그룹 키워드 검색어 광고실적
```

Google Ads 화면이 개편돼도 깨지지 않는 방식이라 이쪽을 권합니다.

### 크롬에서 내려받는 순서

**기간과 세그먼트를 먼저 맞추세요.** 한 번 설정하면 다른 화면에도 유지됩니다.

1. Google Ads 접속 → 우측 상단 **기간 선택**
   - 전체 흐름을 볼 때: 캠페인 시작일 ~ 어제
   - 최근 성과만 볼 때: 예) 2024. 9. 1. ~ 어제
2. 표 위쪽 **세그먼트 → 시간 → 월** ← **이걸 빼면 추이 분석이 불가능합니다**
   - 세그먼트 없이 받으면 파일의 기간이 '전체'로 합산되어, 나중에
     `--since` 로 잘라내는 것도 안 됩니다. 어느 달에 돈이 샜는지 알 수 없습니다.
   - 월 세그먼트를 넣으면 한 파일 안에 월별 행이 들어와
     `python3 scripts/trend.py` 로 추이를 볼 수 있습니다.
3. 아래 5개 화면에서 각각 우측 상단 **다운로드 아이콘 → .csv**

| 화면 | 경로 |
| --- | --- |
| 캠페인 | 캠페인 → 캠페인 |
| 광고그룹 | 캠페인 → 광고그룹 |
| 키워드 | 캠페인 → 검색 키워드 |
| **검색어** | 캠페인 → 검색 키워드 → **검색어** ← 가장 중요 |
| 광고 | 캠페인 → 광고 |

3. 내려받기 전에 **열(컬럼)** 버튼으로 아래를 추가해 두세요.
   - 비용, 노출수, 클릭수, CTR, 평균 CPC
   - 전환수, 전환 가치, 전환당비용, 전환율
   - (캠페인 화면에만) 검색 노출 점유율, 검색 손실 노출 점유율(예산/순위)

## 방법 2 — 자동 모드 (Playwright, 클릭까지 대신)

리포트 화면 이동과 다운로드 버튼 클릭까지 스크립트가 시도합니다.
**Google Ads UI 는 자주 바뀌므로 베스트 에포트**입니다. 클릭에 실패해도
감시 기능은 계속 돌기 때문에 그 화면에서 직접 누르면 됩니다.

### 준비

```bash
pip install playwright
playwright install chromium
```

크롬을 **원격 디버깅 포트와 함께** 실행합니다.

> ⚠️ 크롬 136 버전부터 보안상 **기본 프로필에는 원격 디버깅이 걸리지 않습니다.**
> 아래처럼 별도 프로필 폴더를 지정해야 하고, **그 프로필에서 구글 계정으로
> 한 번 로그인**해야 합니다. (한 번 로그인하면 계속 유지됩니다)

**macOS**
```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/chrome-ads-profile"
```

**Windows (PowerShell)**
```powershell
& "C:\Program Files\Google\Chrome\Application\chrome.exe" `
  --remote-debugging-port=9222 `
  --user-data-dir="$env:USERPROFILE\chrome-ads-profile"
```

열린 창에서 Google Ads 에 로그인한 뒤:

```bash
python3 scripts/browser_download.py --auto
```

### 자동 모드가 하는 일

1. `http://localhost:9222` 로 이미 떠 있는 크롬에 연결
2. 리포트 화면으로 차례로 이동
3. 다운로드 버튼(한국어 `다운로드` / 영어 `Download`)을 찾아 클릭 →
   메뉴에서 `.csv` 선택
4. 새로 생긴 파일을 판별해 `data/raw/` 로 정리

버튼을 못 찾으면 그 화면에 멈춰서 알려주고, 직접 누르면 파일은 그대로 받아냅니다.
UI 경로가 바뀌었다면 `scripts/browser_download.py` 의 `REPORT_URLS` 를 고치세요.

## 방법 3 — 이미 받아둔 파일만 정리

크롬에서 이미 다 받아 놨다면:

```bash
python3 scripts/import_downloads.py                    # 다운로드 폴더에서 최근 24시간
python3 scripts/import_downloads.py ~/Downloads/*.csv  # 직접 지정
```

## 받은 다음

```bash
python3 scripts/analyze.py        # 실적 진단 리포트
python3 scripts/search_terms.py   # 제외 / 신규 키워드 후보
```

## 자주 묻는 것

**Q. 파일 이름이 `report (3).csv` 인데 괜찮나요?**
네. 이름이 아니라 **컬럼 구성을 읽어서** 판별하므로 그대로 두면 됩니다.

**Q. 같은 리포트를 두 번 받으면?**
나중 파일로 교체됩니다. 기간을 바꿔 다시 받았을 때 의도대로 동작합니다.

**Q. 기간을 나눠서 여러 번 받고 싶은데요.**
받을 때 **세그먼트 → 시간 → 월** 을 넣으면 한 번만 받아도 됩니다.
그다음 `--since` / `--until` 로 원하는 구간을 잘라 보세요.

```bash
python3 scripts/trend.py                        # 전체 월별 추이
python3 scripts/trend.py --since 2024-09        # 최근 2년만
python3 scripts/analyze.py --since 2024-09      # 최근 2년 실적 진단
python3 scripts/search_terms.py --since 2024-09 # 최근 2년 검색어
```

여러 번 나눠 받아야 한다면 `--tag` 로 파일을 구분하세요.
`python3 scripts/browser_download.py --tag 2026H1`

**Q. 다운로드 폴더가 다른 곳입니다.**
`--dir "D:\내려받기"` 처럼 지정하세요. 여러 번 쓸 수 있습니다.

**Q. 결국 API 를 쓰는 게 낫지 않나요?**
맞습니다. 개발자 토큰이 승인되면 `python3 scripts/fetch_ads.py --all-time` 한 줄로
끝납니다. 이 문서는 그전까지의 방법입니다. ([`google_ads_api.md`](google_ads_api.md))
