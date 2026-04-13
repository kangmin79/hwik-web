# 다음 세션 할 일 (2026-04-13 저장)

## 1. GitHub Secret 추가 (가장 먼저)
- GitHub 저장소 → Settings → Secrets → Actions → New secret
- Name: `TELEGRAM_BOT_TOKEN` / Value: 봇 토큰
- 없으면 schedule-alerts.yml 알림 발송 안 됨

## 2. 테스트
- 손님 등록 → 매칭 → "전체 결과 보기" 버튼 탭 → 모바일 휙 열리는지
- 일정 저장 → 15분 후 텔레그램 알림 오는지
- mobile-v6에서 ?client=ID로 CRM 뷰 열리는지 + 완료/삭제 버튼

## 3. 버튼 확인
- /start 다시 보내서 브리핑/손님/휙허브 3개 버튼 뜨는지

## 오늘 바뀐 것들
- 텔레그램 아키텍처 재설계: 브리핑+손님등록+알림 수신만
- 버튼: 브리핑/매물/손님/내정보 → 브리핑/손님/휙허브
- 손님 등록 후 SQL 기반 자동 매칭 (JWT 문제 우회)
- 매칭 결과 URL 버튼 (hub-new/?client=ID)
- hub-new: ?client=ID 파라미터로 손님카드+매칭탭 바로 열림
- mobile-v6: ?client=ID 파라미터 + CRM 일정 완료/삭제 버튼
- GitHub Actions schedule-alerts.yml: 15분마다 일정 알림 텔레그램 푸시
- auto-improve: Anthropic 직접 호출로 교체 (function-to-function 401 수정)
- search_text 없는 카드 1,549개 배치 채움
