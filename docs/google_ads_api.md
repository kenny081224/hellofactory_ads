# Google Ads API 연동 설정

한 번만 설정해두면 리포트를 매번 손으로 내려받을 필요 없이
`python3 scripts/fetch_ads.py` 한 줄로 최신 실적을 가져올 수 있습니다.

```bash
python3 scripts/fetch_ads.py --all-time   # 전체 기간 데이터 받기
python3 scripts/analyze.py                # 진단 리포트
python3 scripts/search_terms.py           # 제외/신규 키워드 후보
```

## 준비물 5가지

| 항목 | 어디서 | 소요 시간 |
| --- | --- | --- |
| 개발자 토큰 | Google Ads 관리자(MCC) 계정 → API 센터 | 신청 후 **최대 며칠** |
| OAuth 클라이언트 ID | Google Cloud Console | 10분 |
| OAuth 클라이언트 시크릿 | 위와 동일 | — |
| Refresh token | `scripts/get_refresh_token.py` | 2분 |
| 고객 ID | Google Ads 우측 상단 10자리 숫자 | 즉시 |

> ⚠️ 개발자 토큰의 **기본 액세스(Basic access)** 승인이 나기 전까지는
> 테스트 계정 데이터만 조회됩니다. 실제 계정을 읽으려면 신청과 승인이 필요하고
> 며칠 걸릴 수 있습니다. **그 사이에는** `data/raw/README.md` 대로 CSV를 손으로
> 내려받아 넣으면 분석 스크립트는 똑같이 동작합니다.

---

## 1단계 — 개발자 토큰 발급

1. [Google Ads](https://ads.google.com) 에 **관리자(MCC) 계정**으로 로그인
   (일반 광고 계정에는 API 센터 메뉴가 없습니다. MCC가 없으면
   [관리자 계정을 새로 만들고](https://ads.google.com/home/tools/manager-accounts/)
   기존 광고 계정을 연결하세요.)
2. 우측 상단 **도구 및 설정 → 설정 → API 센터**
3. 신청서 작성 후 제출 → 발급된 **개발자 토큰** 복사
4. 접근 수준이 `테스트 계정 전용`이면 같은 화면에서 **기본 액세스 신청**

## 2단계 — Google Cloud OAuth 클라이언트 만들기

1. [Google Cloud Console](https://console.cloud.google.com/) 에서 프로젝트 생성
2. **API 및 서비스 → 라이브러리** → `Google Ads API` 검색 → **사용 설정**
3. **API 및 서비스 → OAuth 동의 화면**
   - User Type: `외부`
   - 앱 이름·지원 이메일 입력 후 저장
   - **대상(테스트 사용자)** 에 본인 구글 계정을 추가
     (게시 상태가 '테스트'면 여기 등록된 계정만 인증됩니다)
   - 범위는 추가하지 않아도 됩니다 (스크립트가 요청함)
4. **API 및 서비스 → 사용자 인증 정보 → 사용자 인증 정보 만들기
   → OAuth 클라이언트 ID**
   - 애플리케이션 유형: **데스크톱 앱**
   - 생성 후 **클라이언트 ID**와 **클라이언트 보안 비밀** 복사

## 3단계 — Refresh token 발급

본인 PC에서 (브라우저가 열려야 합니다):

```bash
git clone https://github.com/kenny081224/hellofactory_ads
cd hellofactory_ads
pip install -r requirements.txt
python3 scripts/get_refresh_token.py
```

클라이언트 ID와 시크릿을 붙여넣으면 브라우저가 열립니다.
**광고 계정에 접근 권한이 있는 구글 계정**으로 로그인하고 동의하면
`config/credentials.env` 에 자동 저장됩니다.

> 이미 한 번 동의한 계정이라 refresh token 이 안 나오면
> [내 계정 → 앱 접근 권한](https://myaccount.google.com/permissions) 에서
> 해당 앱을 삭제하고 다시 실행하세요.

## 4단계 — 나머지 값 채우기

`config/credentials.env` 를 열어 아래를 추가합니다.

```
GOOGLE_ADS_DEVELOPER_TOKEN=여기에_개발자_토큰
GOOGLE_ADS_CUSTOMER_ID=1234567890
# MCC 를 통해 접근한다면 (권장)
GOOGLE_ADS_LOGIN_CUSTOMER_ID=9876543210
```

- `GOOGLE_ADS_CUSTOMER_ID` 는 **데이터를 읽을 광고 계정**의 10자리 숫자입니다.
  Google Ads 우측 상단에 `123-456-7890` 형태로 보이며, **하이픈은 빼고** 넣습니다.
- `GOOGLE_ADS_LOGIN_CUSTOMER_ID` 는 그 계정을 관리하는 **MCC 계정** ID입니다.
  MCC 아래에 광고 계정이 있다면 반드시 넣어야 권한 오류가 나지 않습니다.

이 파일은 `.gitignore` 에 등록되어 있어 커밋되지 않습니다.
**토큰을 코드나 커밋 메시지에 붙여넣지 마세요.**

## 5단계 — 확인

```bash
python3 scripts/fetch_ads.py --check
```

```
계정: 1234567890  API: v22
접근 확인됨: 헬로팩토리 (KRW, Asia/Seoul)
```

이렇게 나오면 끝입니다.

```bash
python3 scripts/fetch_ads.py --all-time
python3 scripts/analyze.py
python3 scripts/search_terms.py
```

---

## 가져오는 데이터

`scripts/fetch_ads.py` 는 GAQL 로 아래 5개 리소스를 조회해
`data/raw/` 에 한국어 컬럼 CSV로 저장합니다. 손으로 내려받은 파일과
형식이 같아서 이후 분석 스크립트는 구분 없이 동작합니다.

| 파일 | GAQL 리소스 |
| --- | --- |
| `캠페인_*.csv` | `campaign` (+ 노출 점유율·예산/순위 손실) |
| `광고그룹_*.csv` | `ad_group` |
| `키워드_*.csv` | `keyword_view` |
| `검색어_*.csv` | `search_term_view` |
| `광고실적_*.csv` | `ad_group_ad` |

## 자주 나오는 오류

| 증상 | 원인과 해결 |
| --- | --- |
| `액세스 토큰 발급 실패 (400) invalid_grant` | refresh token 만료. `get_refresh_token.py` 재실행 |
| `USER_PERMISSION_DENIED` | 로그인한 구글 계정에 해당 광고 계정 권한이 없음. 또는 `GOOGLE_ADS_LOGIN_CUSTOMER_ID` 누락 |
| `DEVELOPER_TOKEN_NOT_APPROVED` | 개발자 토큰이 아직 테스트 전용. 기본 액세스 승인 대기 |
| `CUSTOMER_NOT_FOUND` | 고객 ID에 하이픈이 들어갔거나 MCC ID를 잘못 넣음 |
| `API 버전 v22 을 찾을 수 없습니다 (404)` | 버전 종료. `GOOGLE_ADS_API_VERSION=v23` 처럼 환경변수로 상향 |

> Google Ads API 는 2026년부터 월 단위 릴리스이고 각 버전은 약 1년 뒤 종료됩니다.
> (v21은 2026-08-05 종료) 404가 뜨면 `GOOGLE_ADS_API_VERSION` 만 올리면 됩니다.
