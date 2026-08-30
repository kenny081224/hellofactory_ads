# 신규 캠페인 설정서 소스

`docs/campaign_setup_spec.md` 는 이 폴더의 YAML에서 자동 생성됩니다.
**md 를 직접 고치지 마세요.** 여기를 고치고 다시 생성하면 글자 수와 개수가
자동으로 다시 계산됩니다.

```bash
python3 scripts/gen_setup_spec.py
```

| 파일 | 내용 |
| --- | --- |
| `setup.yaml` | 캠페인·광고그룹·키워드·예산·입찰가 |
| `rsa.yaml` | 반응형 검색광고 헤드라인·설명 |
| `neg.yaml` | 제외 키워드 (계정 / 헬로벨 / 헬로클릭) |

글자 수는 Google 실제 규칙(전각 2 / 반각 1, 헤드라인 30 · 설명 90)으로
생성 시 검증됩니다. 한도를 넘으면 md 에 표시된 숫자로 바로 확인됩니다.

## 확정 후

이 내용을 `campaigns/plan.yaml` / `ads.yaml` / `assets.yaml` 에 반영하면
`python3 scripts/make_editor_csv.py` 로 Google Ads Editor 업로드용 CSV가
생성됩니다. 지금은 **제안 단계라 반영하지 않았습니다.**
