# 다음 세션 할 일 (2026-04-13 저녁 저장)

## 1. 전국 확장 단지 수집 이어서 (collect_complexes.py)
완료: 세종 211 + 충북 789 + 충남 989 + 전북 881 + 전남 782 = **3,652개**
남은 것:
- `python collect_complexes.py --region gyeongbuk`
- `python collect_complexes.py --region gyeongnam`
- `python collect_complexes.py --region gangwon`
- `python collect_complexes.py --region jeju`

## 2. collect_pyeongs_v2.py (공급면적 수집)
단지 수집 완료 후:
`python collect_pyeongs_v2.py --region all`

## 3. GitHub Actions --init 실행
실거래 첫 수집 (새 지역 9개):
Actions → 실거래가 동기화 → mode: init, region: 비워두기

## 4. match_apt_seq.py (apt_seq 매칭)
실거래 수집 완료 후:
`python match_apt_seq.py --region all`

## 5. build_danji_from_v2.py (전체 재집계)
Actions 완료 후:
`python build_danji_from_v2.py --region all`

## 6. HTML 빌드 + sitemap + deploy
`python build_danji_pages.py`
`python build_dong_pages.py`
`python build_gu_pages.py`
`python sync_trades.py --sitemap-only`
`git push`

## 오늘 완료한 것들
- regions.py 9개 지역 추가 (세종~제주)
- 전체 스크립트 REGION_MAP 업데이트 (collect_complexes/trades/pyeongs_v2/match_apt_seq/build_danji_from_v2)
- sync_trades.py 구 파이프라인 완전 삭제 (price_history 덮어쓰기 버그 원천 차단)
- slug_utils.py gu_url_slug 충돌 방지, extract_gu_from_address 세종/2토큰 수정
- sync-trades.yml 9개 지역 job 추가
- OG 이미지 12,502/12,661개 완료
- 단지 수집: 세종~전남 3,652개 완료
