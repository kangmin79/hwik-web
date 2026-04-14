# SEO 다음 할 일

## 진행 중
- sync-trades 수동 실행 중 — 이메일 결과 확인
  - 빌드 성공 여부
  - 메타 디스크립션 데이터 기반으로 바뀌었는지
  - 단지 집계 몇 개 처리됐는지

## 남은 작업
- twitter:card: generate_page()에 summary_large_image 적용 확인
- 신규 지역 OG 이미지 생성 (`python build_og_images.py`)
- 월별 신규 단지 수집 자동화 (collect_complexes → pyeongs → match_apt_seq)
- 랭킹 도 단위 탭 추가 여부 기획 결정

## 현재 상태
- 전국 17개 광역시도 배포 완료
- trade_raw_v2: 7,725,639건 (전국 5년치)
- HTML: danji 18,891 / dong 1,533 / gu 232 / ranking 37 / sitemap 20,690
- GitHub Actions: 매일 새벽 1시 KST / --months 3 / --changed-only --hours 24
