# 앱 기능 다음 할 일

## 1. agent.html — 단지 페이지 연결
- danji/app.js "휙 등록 매물" 섹션 → 중개사 있으면 agent.html 링크 추가
- URL: `/agent.html?id=AGENT_ID&lat=LAT&lng=LNG`

## 2. agent.html — hub-new에서 매물 선택 후 링크 생성
- hub-new에서 매물 체크박스 선택 → "링크 복사" 버튼
- URL: `/agent.html?id=AGENT_ID&cards=ID1,ID2,ID3`
- 카톡으로 손님에게 전송

## 3. agent.html — 헤더 디자인 마무리
- SEO 안정화 후 마무리 예정

## 4. telegram_chat_logs 테이블 구현
- 텔레그램 대화 전부 저장
- 채팅 플로우 테스트 후 착수

## 현재 상태
- agent.html 완성 (중개사 홈페이지)
  - 프로필, 매물 리스트, 바텀 시트 (사진/지도/카카오 문의)
  - 단지 유입 모드: 5개 필터 + 더보기 + 주변 단지 시세
- mobile.html 속도 개선 (캐시 전략)
- telegram-webhook 손님 등록 완료 후 매칭 결과 버튼 추가
