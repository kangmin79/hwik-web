# 다음 세션 할 일 (2026-04-18 이후)

## 오늘 배포 4건 — 결과 관찰 먼저
1. 새벽 1시 sync-trades 정상 완료 이메일 확인
2. schedule-alerts 15분 주기 녹색 (Actions 탭)
3. GSC: /gu/ 404 감소, NOINDEX 1,000 → 더 감소, danji 스니펫에 실거래가 수치
4. hwik.kr/gu/천안동남구 → /gu/충남-천안시-동남구 자동 리다이렉트 확인

## 보류된 워크플로우 개선 (관찰 후 점진 착수)
- C3: sync-trades.yml autofix `git add -A *.py` → 파일명 명시 (리스크 높음, 신중)
- H1~H7: concurrency cancel, 실패 알림, permissions, rebase 방어 등
- M1: 17개 지역 matrix strategy 리팩토링 (470줄 → 30줄, 별도 세션)

## 기타
- GSC 404 /danji/ 41건 자동 매핑은 **포기** (숫자 토큰 다른 잘못된 매칭 위험) → 60일 자연 정리 대기
- 상세: docs/2026-04-17.md
