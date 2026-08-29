# hellobell.shop 제품별 전환 태그 설정

비상벨과 헬로클릭이 같은 자사몰(Cafe24)에 올라가 있으므로, **하나의 태그를 심되
전환 액션을 제품별로 나눠서** 기록합니다. 그래야 비상벨 캠페인은 비상벨 매출로,
헬로클릭 캠페인은 헬로클릭 매출로 각각 최적화됩니다.

> 자사몰로 통일하는 것의 의미: 스마트스토어와 달리 Cafe24 는 스크립트 삽입이
> 가능합니다. **실제 구매와 결제 금액이 그대로 전환·전환가치로 기록**되므로
> 타겟 ROAS 입찰까지 정상 작동합니다. (`docs/measurement.md` 의 A안)

## 1. 만들 전환 액션

Google Ads → 목표 → 전환 → **+ 새 전환 액션** → 웹사이트

| 전환 액션 이름 | 카테고리 | 값 | 주요 전환 | 집계 |
| --- | --- | --- | --- | --- |
| `구매_비상벨` | 구매 | 거래마다 다름 | ✅ | 모든 전환 |
| `구매_헬로클릭` | 구매 | 거래마다 다름 | ✅ | 모든 전환 |
| `문의_비상벨` | 문의 제출 | 고정 (아래 계산) | ✅ | 전환 1회 |
| `문의_헬로클릭` | 문의 제출 | 고정 (아래 계산) | ✅ | 전환 1회 |
| `전화클릭` | 전화 통화 | 고정 | ✅ | 전환 1회 |
| `장바구니담기` | 장바구니에 추가 | 값 없음 | ❌ (보조) | 전환 1회 |

각 전환 액션을 만들면 **전환 ID(`AW-XXXXXXXXX`)와 전환 라벨**이 나옵니다.
아래 스크립트의 `SEND_TO` 값에 넣습니다.

**문의 고정 가치 계산 예시**
```
문의 10건 중 3건 성사 × 평균 주문금액 90,000원 = 문의 1건당 27,000원
```
실제 성사율을 모르면 일단 넣고, 3개월 뒤 실제 값으로 고칩니다.
값이 0이면 캠페인 간 비교가 불가능하므로 **0으로 두지 마세요.**

## 2. 태그 설치 (Cafe24)

### 2-1. 전 페이지 공통 — Google 태그

Cafe24 관리자 → **디자인(웹) → 디자인 편집** → 사용 중인 스킨의
`레이아웃/기본 레이아웃` HTML 에서 `</head>` **바로 위**에 넣습니다.
PC/모바일 스킨을 따로 쓰면 **양쪽 모두** 넣어야 합니다.

```html
<!-- Google tag (gtag.js) -->
<script async src="https://www.googletagmanager.com/gtag/js?id=AW-XXXXXXXXX"></script>
<script>
  window.dataLayer = window.dataLayer || [];
  function gtag(){dataLayer.push(arguments);}
  gtag('js', new Date());
  gtag('config', 'AW-XXXXXXXXX');   // Google Ads 전환 ID
  gtag('config', 'G-YYYYYYYYYY');   // GA4 측정 ID (같이 쓰는 것을 권장)
</script>
```

> 태그 관리자(GTM)를 쓸 줄 알면 GTM 컨테이너 하나만 넣고 그 안에서 관리하는 편이
> 나중에 수정하기 훨씬 편합니다. 이 문서는 GTM 없이도 되도록 gtag 기준으로 씁니다.

### 2-2. 주문완료 페이지 — 제품별 구매 전환

Cafe24 관리자에서 **주문완료(결제완료) 페이지**에 삽입하는 스크립트 영역을 찾습니다.
(마케팅 관련 설정의 *전환 스크립트* 또는 *접속통계 스크립트* 항목. 스킨에 따라
`order/order_result.html` 을 직접 편집해도 됩니다.)

Cafe24 는 이 영역에서 **치환변수**로 주문 정보를 넘겨줍니다. 관리 화면에
안내된 변수명을 그대로 쓰세요. 아래는 그 값을 받아 제품을 판별하는 코드입니다.

```html
<script>
(function () {
  // ── 1) 제품 판별 규칙: 상품번호(product_no)를 제품에 매핑 ────────────
  //     Cafe24 관리자 > 상품관리에서 각 상품의 상품번호를 확인해 채우세요.
  var PRODUCT_MAP = {
    bisangbel:  [45, 46, 47, 48],   // ← 비상벨 계열 상품번호
    helloclick: [61, 62]            // ← 헬로클릭 계열 상품번호
  };
  // 상품번호를 못 넘기는 스킨이라면 상품명 키워드로 대체 판별합니다.
  var NAME_RULES = {
    bisangbel:  ['비상벨', '도움벨', '호출벨', '헬로벨'],
    helloclick: ['헬로클릭', '학생응답', '학생 응답']
  };

  // ── 2) 전환 액션별 send_to (Google Ads 전환 ID/라벨) ────────────────
  var SEND_TO = {
    bisangbel:  'AW-XXXXXXXXX/BELL_LABEL',
    helloclick: 'AW-XXXXXXXXX/CLICK_LABEL'
  };

  // ── 3) 주문 정보 — Cafe24 치환변수를 여기에 연결 ────────────────────
  //     관리 화면에 안내된 변수명을 그대로 넣으세요.
  var orderId = '[주문번호]';
  var items = [
    // 주문 상품이 여러 건이면 반복 출력되도록 스킨 반복문을 사용합니다.
    // { no: [상품번호], name: '[상품명]', amount: [상품별결제금액] }
  ];

  // ── 4) 제품별로 금액을 합산 ─────────────────────────────────────────
  function classify(item) {
    for (var key in PRODUCT_MAP) {
      if (PRODUCT_MAP[key].indexOf(Number(item.no)) !== -1) return key;
    }
    for (var k in NAME_RULES) {
      for (var i = 0; i < NAME_RULES[k].length; i++) {
        if ((item.name || '').indexOf(NAME_RULES[k][i]) !== -1) return k;
      }
    }
    return null;   // 어느 쪽도 아니면 전환을 보내지 않습니다
  }

  var totals = {};
  for (var i = 0; i < items.length; i++) {
    var key = classify(items[i]);
    if (!key) continue;
    totals[key] = (totals[key] || 0) + Number(items[i].amount || 0);
  }

  // ── 5) 제품별로 각각 전환 발화 ──────────────────────────────────────
  for (var key in totals) {
    if (!SEND_TO[key]) continue;
    gtag('event', 'conversion', {
      send_to: SEND_TO[key],
      value: totals[key],
      currency: 'KRW',
      transaction_id: orderId + '-' + key   // 중복 집계 방지
    });
  }
})();
</script>
```

**포인트 3가지**

- `transaction_id` 에 주문번호를 넣어야 새로고침으로 인한 중복 전환이 막힙니다.
  한 주문에 두 제품이 섞여 있으면 제품별로 다른 ID가 되도록 접미사를 붙였습니다.
- 한 주문에 비상벨과 헬로클릭이 같이 있으면 **각각 자기 금액만큼** 전환됩니다.
  주문 총액을 양쪽에 다 넣으면 매출이 두 배로 부풀려집니다.
- 어느 쪽에도 해당하지 않는 상품은 전환을 보내지 않습니다.
  새 제품을 올리면 `PRODUCT_MAP` 에 상품번호를 추가하세요.

### 2-3. 문의 전환

```html
<!-- 전화번호 링크에 -->
<a href="tel:0212345678"
   onclick="gtag('event','conversion',{send_to:'AW-XXXXXXXXX/PHONE_LABEL'});">
  전화 문의
</a>

<!-- 문의 등록 완료 페이지에 (비상벨 문의 게시판인 경우) -->
<script>
  gtag('event', 'conversion', {
    send_to: 'AW-XXXXXXXXX/BELL_LEAD_LABEL',
    value: 27000, currency: 'KRW'
  });
</script>
```

문의 게시판이 제품 공용이라면, 문의 폼에 **"문의 제품" 선택 항목**을 추가하고
그 값에 따라 `send_to` 를 분기하세요. 그래야 제품별 리드가 구분됩니다.

## 3. 캠페인별로 최적화할 전환 지정 ★ 가장 중요

전환 액션을 나눠도, 캠페인이 **모든 전환**을 보고 최적화하면 나눈 의미가 없습니다.
Google Ads 에서 캠페인마다 사용할 전환을 지정하세요.

**캠페인 → (해당 캠페인 선택) → 설정 → 전환 → "이 캠페인에 대해 전환 액션 선택"**

| 캠페인 | 선택할 전환 액션 |
| --- | --- |
| `[검색] 비상벨 \| 법정설치` | `구매_비상벨`, `문의_비상벨`, `전화클릭` |
| `[검색] 비상벨 \| 일반·시설별` | `구매_비상벨`, `문의_비상벨`, `전화클릭` |
| `[검색] 헬로클릭 \| 교육` | `구매_헬로클릭`, `문의_헬로클릭` |
| `[검색] 브랜드 \| 헬로벨·헬로클릭` | 전부 |

이 설정을 해야 헬로클릭 캠페인이 비상벨 매출을 자기 성과로 착각하지 않습니다.

## 4. 강화된 전환 (Enhanced Conversions)

주문완료 페이지에서 구매자 이메일/전화번호를 함께 넘기면 전환 측정 정확도가
올라갑니다. Google Ads → 목표 → 전환 → 설정 → **강화된 전환 사용** 을 켜고,
전환 스크립트에 아래를 추가합니다. (구글이 브라우저에서 해시 처리합니다)

```js
gtag('set', 'user_data', {
  email: '[주문자이메일]',
  phone_number: '[주문자연락처]'   // +82 형식 권장
});
```

개인정보처리방침에 광고 성과 측정 목적의 정보 활용이 고지되어 있어야 합니다.

## 5. 검증

설치 후 **반드시** 실제로 확인하세요. 태그가 안 붙은 채 몇 주를 흘려보내는 것이
가장 흔한 실패입니다.

- [ ] Chrome 확장 **Google Tag Assistant** 로 전 페이지에 태그 로드 확인
- [ ] 테스트 주문 1건 결제 → 주문완료 페이지에서 `conversion` 이벤트 발생 확인
- [ ] 비상벨 상품만 산 주문 → `구매_비상벨` 만 발화되는지
- [ ] 두 제품 섞인 주문 → 각각 자기 금액으로 발화되는지
- [ ] 3시간~하루 뒤 Google Ads → 목표 → 전환 에서 상태가 **"최근 전환 기록됨"** 인지
- [ ] 전환 값(금액)이 실제 결제 금액과 맞는지
- [ ] 새로고침해도 전환이 중복으로 늘지 않는지

## 6. 설치 후 반영할 것

1. `config/products.yaml` 의 `landing_urls` 에 실제 상품 페이지 URL 채우기
2. `python3 scripts/make_editor_csv.py` 재실행 → 광고그룹별 랜딩이 반영됨
3. 전환이 캠페인당 월 15건 이상 쌓이면 입찰을 **전환수 최대화 → 타겟 CPA**,
   전환가치가 안정되면 **타겟 ROAS** 로 올립니다
   (`campaigns/structure.md` 4번 참고)
