# 앱 기능 다음 할 일 (2026-04-15 업데이트)

## 1. 단지 페이지 배너 (중개사 연결)
- buildUrlWithTab() 함수 이미 준비됨 (danji/app.js:6-13)
- 배너 위치/형태 결정 후 buildUrlWithTab(baseUrl) 연결
- buildUrlWithTab('https://hwik.kr/agent/홍길동') → '?type=매매|전세|월세'
- 중개사 페이지에서 type 파라미터 읽어서 해당 탭 자동 선택

## 2. 매물 등록 시 kapt_code 매칭
- 중개사 매물 등록 시 단지명 + 좌표로 apartments 테이블에서 kapt_code 정확히 매칭
- apartments 테이블: kapt_name(단지명), lat/lon(좌표), kapt_code
- 로직: 단지명 유사도로 후보 추린 후 → 좌표 500m 이내 → kapt_code 확정

## 3. agent.html — hub-new에서 매물 선택 후 링크 생성
- hub-new에서 매물 체크박스 선택 → "링크 복사" 버튼
- URL: /agent.html?id=AGENT_ID&cards=ID1,ID2,ID3

## 4. telegram_chat_logs 테이블 구현
- 텔레그램 대화 전부 저장
- 채팅 플로우 테스트 후 착수
