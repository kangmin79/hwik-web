# 다음 세션 할 일 (2026-04-14 저장)

## 1. agent.html — 단지 페이지 연결
- danji/app.js에서 "휙 등록 매물" 섹션 → 중개사 있으면 agent.html 링크 추가
- URL: `/agent.html?id=AGENT_ID&lat=LAT&lng=LNG`

## 2. SEO 페이지 안정화
- danji/gu/dong/ranking 페이지 점검
- Google Search Console 확인

## 3. agent.html 헤더 디자인
- SEO 안정화 후 마무리 예정 (지금 보류)

## 4. 전국 확장 단지 수집 (이전 세션 미완)
- gyeongbuk / gyeongnam / gangwon / jeju 수집
- collect_pyeongs_v2.py → match_apt_seq.py → build_danji_from_v2.py

## 오늘 만든 것들
- **agent.html** 중개사 홈페이지 전체 완성
  - 프로필 헤더 (이름/사무소/주소/전화)
  - 매물 리스트 (계약가능만, 노란 카드)
  - 바텀 시트: 사진 스와이프 + 손님에게 한마디 + 미니맵 + 풀스크린 지도
  - 카카오 오픈채팅 문의 버튼 (profiles.kakao_chat_url)
  - 단지 유입 모드 (?lat=&lng=): 200m→1km 우선순위 5개 + 더보기 배너 + 주변 단지 시세
- **sw.js** cache-first 전략 (mobile.html 캐시)
- **mobile.html** getToken() 캐시로 속도 개선
- **telegram-webhook** 손님 등록 완료 후 MAIN_INLINE 버튼 추가
