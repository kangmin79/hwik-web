# 다음 세션 할 일 (2026-04-13 저녁 저장)

## 1. OG 이미지 확인 (가장 먼저)
- `python - <<'EOF'` 로 manifest 개수 확인
- 12,661개 완료됐으면 git push → Actions 활성화

## 2. GitHub Actions 활성화
- GitHub → Actions → "실거래가 동기화" → Enable → Run workflow
- mode: daily, region: 비워두기
- 정상 완료 확인 후 매일 새벽 3시 자동 실행

## 3. 트래픽 모니터링
- GSC에서 인덱싱 페이지 수 확인 (8,260 → 13,651 목표)
- 하루 100트래픽 나오면 중개사 페이지(hwik.kr/agent/) 개발 착수

## 오늘 완료한 것들
- sync-trades.yml 신버전 교체 (collect_trades_v2, 8개 광역시 병렬)
- build_danji_pages.py 누락 수정 + 실행 순서 정정
- OG 이미지 fallback 처리 (기본 og-image.png)
- sitemap dong 404 94개 제거 (13,651개, 0개 실패)
- 404 리다이렉트 URL 디코딩 버그 수정
- 카카오 지도 lazy load
- 차트 최고가 하이라이트 유지 버그 수정
- sitemap GSC 재제출 완료
- OG 이미지 PC에서 생성 중 (12,661개 목표, 현재 진행 중)
