# 헬로팩토리 Google Ads 운영 저장소

비상벨 / 헬로클릭 두 제품의 Google Ads 캠페인을 **분석 → 재설계 → 지속 개선**
하기 위한 작업 저장소입니다. 스프레드시트 대신 이 저장소를 기준으로 운영하면
"무엇을 왜 바꿨는지"가 커밋 이력으로 남습니다.

## 빠르게 시작하기

```bash
# 0) 최초 1회: API 인증 설정 (docs/google_ads_api.md)
python3 scripts/get_refresh_token.py
python3 scripts/fetch_ads.py --check

# 1) 실적 데이터 받아서 분석
python3 scripts/fetch_ads.py --all-time
python3 scripts/analyze.py

# 2) 검색어에서 낭비 걸러내기 + 애셋 진단
python3 scripts/search_terms.py
python3 scripts/assets.py

# 2-1) 월별 추이 (리포트에 '세그먼트 → 시간 → 월' 이 적용되어 있어야 함)
python3 scripts/trend.py
python3 scripts/analyze.py --since 2024-09      # 기간을 잘라서 재분석

# 3) 새 캠페인 업로드 파일 만들기
python3 scripts/make_editor_csv.py
```

API 설정은 [`docs/google_ads_api.md`](docs/google_ads_api.md) 에 있습니다.
개발자 토큰 승인 대기 중이라면 브라우저로 내려받으세요 —
`python3 scripts/browser_download.py` 를 켜 두면 크롬에서 받는 즉시 파일을
판별해 `data/raw/` 로 정리합니다 ([`docs/browser_download.md`](docs/browser_download.md)).
데이터가 없어도 예시로 동작을 볼 수 있습니다.

```bash
python3 scripts/analyze.py --dir data/sample --out /tmp
```

## 실적 진단 결과

**현재 기준: [`docs/findings_recent2y.md`](docs/findings_recent2y.md)** (최근 2년, 2024.09~2026.08)

- 1년차가 3년 총비용의 **70.1%**(8,226,655원)를 소진 — 초기 과지출 가설 확인
- 1년차 CPA 1,554원 vs 최근 2년 121,173원. **저가치 전환이 사라진 뒤 24개월간
  전환 29건뿐**이고, 25개월 중 17개월이 전환 0
- 최근 2년 낭비: 투표 키워드 766,191원 · 전환0 키워드 608,379원 ·
  경쟁사 148,101원 = **1,522,671원(43.3%)**
- 최근 2년 최고 효율: **노인 안심벨 CPA 7,042원 / 노인 비상벨 CPA 14,848원**
- RSA 1개가 25개월째 그대로, 여전히 스마트스토어로 송출, CTR 2.90%→0.61%

참고(1년차 포함 3년 전체): [`docs/findings_2026-08.md`](docs/findings_2026-08.md)
— 단 '무선 호출벨이 최고 효율'이라는 결론은 1년차 저가치 전환 때문이며
최근 2년 기준으로는 전환 0입니다. 정정 내용은 최근 2년 문서 4번 참고.

## 신규 캠페인 설정안 (제안 단계, 미적용)

- **[`docs/campaign_setup_spec.md`](docs/campaign_setup_spec.md)** — 실행용 설정서 (**v5 최종**)
  캠페인 4 / 광고그룹 9 / 키워드 51 / 제외 키워드 130 / RSA 9세트(헤드라인 100)
  승인 상한 20만원 / 활성 18만원 / 예비 2만원
- **[`docs/final_review_v4.md`](docs/final_review_v4.md)** — v4 검토 의견과 진행 전 확인 사항
- **[`docs/plan_comparison.md`](docs/plan_comparison.md)** — 초기 두 분석안 비교

세 차례 교차 검토를 거쳤습니다. v3(검색량 검증) → v4(예산·효율) → v5(최종).
진행 전 필수 조치 3가지는 `final_review_v4.md` 3장을 보세요.
`campaigns/spec/*.yaml` 을 고치고 `python3 scripts/gen_setup_spec.py` 로 재생성합니다.
생성할 때마다 글자 수(전각 2/반각 1), **제품 자료로 확인되지 않은 사양 표현**
(방수·배터리 2년·A/S·납품 실적·세금계산서), 안전 관련 금지 표현, 제외 키워드와
타겟 키워드의 충돌을 자동 검사합니다.

## 재설계 배경 (제안 단계, 미적용)

제품 소개서를 반영한 전면 재설계안: **[`docs/redesign_proposal.md`](docs/redesign_proposal.md)**

- 헬로벨을 '무선벨'이 아니라 **메시지·수신자 지정 + 처리 상태 공유 + 배터리 원격 확인**
  플랫폼으로 재정의 → 지자체·돌봄(B2G) 세그먼트 신규 개척
- 헬로클릭을 '학생응답시스템'에서 **행사·총회용 무선투표기 렌탈**로 이동
- 투표 키워드는 전면 제외가 아니라 **'대여/렌탈/장비'가 붙은 것만 살리고
  광의 단독어는 정확일치 제외**로 분리
- 월 예산 현실화 필요 (설정 1,500,000원 vs 실제 146,417원)

> 계정과 저장소 설정은 아직 바꾸지 않았습니다.

## 진행 순서

| 순서 | 할 일 | 문서 |
| --- | --- | --- |
| 0 | **전환 추적부터 고치기** — hellobell.shop 제품별 태그 | [`docs/tagging_hellobell.md`](docs/tagging_hellobell.md) · [`배경`](docs/measurement.md) |
| 0-1 | Google Ads API 연동 (승인 전엔 브라우저) | [`google_ads_api.md`](docs/google_ads_api.md) · [`browser_download.md`](docs/browser_download.md) |
| 1 | 지금까지의 실적 분석 | `python3 scripts/fetch_ads.py` → `analyze.py` |
| 2 | 검색어 정리 (제외 키워드 / 신규 키워드) | `python3 scripts/search_terms.py` |
| 2-1 | 애셋 진단·보강 | `python3 scripts/assets.py` · [`docs/assets.md`](docs/assets.md) |
| 3 | 새 캠페인 구조 확인·수정 | [`campaigns/structure.md`](campaigns/structure.md) |
| 4 | Editor 업로드 파일 생성 | `python3 scripts/make_editor_csv.py` |
| 5 | 주간·월간 개선 루틴 | [`docs/weekly_optimization.md`](docs/weekly_optimization.md) |

> **0번을 건너뛰지 마세요.** 지금처럼 광고 도착지가 네이버 스마트스토어이면
> Google Ads 전환 태그를 심을 수 없어 실제 구매가 전환으로 기록되지 않습니다.
> 계정에 보이는 "전환 가치"는 실제 매출이 아닐 가능성이 높고, 그 위에서 스마트
> 입찰을 돌리면 잘못된 근거로 예산이 배분됩니다.
> 두 제품 모두 자사몰 hellobell.shop 에 있으므로 도착지를 자사몰로 옮기고
> `구매_비상벨` / `구매_헬로클릭` 처럼 전환을 제품별로 분리합니다.

## 폴더 구조

```
config/products.yaml       제품 정보, 랜딩 URL, 목표 CPA/ROAS, 예산 — 판단의 기준값
config/credentials.env     Google Ads API 인증 정보 (커밋 제외, .example 참고)
campaigns/plan.yaml        새 캠페인·광고그룹·키워드·제외 키워드 설계 (정답 소스)
campaigns/ads.yaml         반응형 검색광고 문안 (한국어 글자 수 자동 검사)
campaigns/assets.yaml      사이트링크·콜아웃·스니펫 등 애셋 문안
campaigns/structure.md     구조를 왜 이렇게 바꾸는지에 대한 설명
campaigns/editor/          Google Ads Editor 업로드용 CSV (생성물, 커밋됨)
campaigns/generated/       검색어 분석이 만든 제외/신규 키워드 CSV (커밋 제외)
data/raw/                  Google Ads 리포트 CSV를 넣는 곳 (커밋 제외)
data/sample/               동작 확인용 가짜 예시 데이터
docs/measurement.md        전환 추적 문제와 해결책
docs/weekly_optimization.md  지속 개선 루틴
reports/                   분석 결과 (커밋 제외)
docs/google_ads_api.md     API 연동 설정 절차
docs/browser_download.md   브라우저 다운로드 자동 정리
docs/assets.md             애셋 전략·이미지 규격·전달 방법
assets/current, assets/new 이미지 애셋 (규격 검사: check_images.py)
docs/tagging_hellobell.md  자사몰 제품별 전환 태그 설치
scripts/fetch_ads.py       Google Ads API 로 실적 리포트 자동 수집
scripts/browser_download.py  크롬 다운로드를 감시해 data/raw/ 로 자동 정리
scripts/import_downloads.py  이미 받아둔 CSV를 판별해 정리
scripts/assets.py          애셋 실적 진단 (RSA 등급 + 확장 애셋 커버리지)
scripts/trend.py           월별 추이 (초기 vs 최근 비교, 전환 0인 달 탐지)
scripts/check_images.py    이미지 애셋 규격 검사
scripts/get_refresh_token.py  OAuth refresh token 발급 도우미
scripts/                   그 외 분석·생성 스크립트
```

## 설계 요약

**비상벨**과 **헬로클릭**은 구매자가 완전히 다릅니다.
비상벨은 법정 설치 의무를 진 시설 담당자(관공서·학교·병원)의 B2B/B2G 수요이고,
헬로클릭은 교사·학교의 교육 기자재 수요입니다. 예산·입찰·문안을 분리합니다.

```
[검색] 비상벨 | 법정설치       45%   장애인화장실 / 공중화장실 / 설치기준
[검색] 비상벨 | 일반·시설별     25%   무선비상벨 / 시설별 / 가정케어 / 스마트폰수신
[검색] 브랜드 | 헬로벨·헬로클릭  5%   브랜드 방어
[검색] 헬로클릭 | 교육          15%   학생응답시스템 / 수업참여 / 퀴즈버저 / 학교도입
(예비)                        10%   4주 뒤 성과 좋은 쪽에 투입
```

예산 비율과 목표는 `config/products.yaml` 과 `campaigns/plan.yaml` 에서 바꾸면
생성물에 그대로 반영됩니다.

## 요구 사항

Python 3.9+ / PyYAML / requests.

```bash
pip install -r requirements.txt
```
