# 다음 세션 할 일 (2026-04-15 오후 저장)

## 완료된 것
- OG 이미지 단일 파일(og-image.png)로 통일, 워크플로우 OG 생성 스텝 제거
- 동 OG 타임아웃/concurrency/push 충돌 수정
- 단지 급감 가드 99%로 강화
- buildUrlWithTab() 함수 추가 (danji/app.js:6-13)

## 해야 할 것

### 1. 워크플로우 재실행 확인
- GitHub Actions sync-trades 재실행 후 성공 여부 확인
- 빌드 시간이 OG 제거로 많이 줄었는지 확인

### 2. 단지 페이지 배너
- 배너 위치/형태 결정 후 buildUrlWithTab() 연결
- buildUrlWithTab(baseUrl) → baseUrl?type=매매|전세|월세
- 중개사 페이지에서 type 파라미터 읽어서 해당 탭 자동 선택

### 3. 매물 등록 시 kapt_code 매칭
- 중개사 매물 등록 시 단지명 + 좌표로 apartments 테이블에서 kapt_code 정확히 매칭
- apartments 테이블: kapt_name(단지명), lat/lon(좌표), kapt_code
- 단지명 유사도 → 좌표 500m 이내 → kapt_code 확정

## 나중에 할 것
- telegram_chat_logs 테이블 구현
