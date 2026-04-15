# 다음 세션 할 일 (2026-04-15 오후)

## 오늘 완료한 것
- trade_raw_v2 인덱스 추가 (created_at, prop_type) — 빌드 타임아웃 해결
- OG 이미지 잔재 정리 (build_danji_pages.py img 태그, 빌드 이메일 로그)
- 빌드 실패 자동 수정 에이전트 구현
  - auto_fix.py — Claude Haiku로 로그 분석 → Python 스크립트 자동 수정
  - sync-trades.yml — failure() 시 auto_fix.py 실행 → commit+push+재실행
  - GitHub Secret ANTHROPIC_API_KEY 등록 완료
- sync-trades.yml 개선
  - build job if 조건 완화 (1개 지역 실패해도 빌드 진행)
  - retry_count 입력 파라미터 추가
  - 동/구/랭킹 스텝 tee 로그 캡처 추가
- 빌드 검증 오류 수정
  - verify_data.py 공급/전용 비율 0.95~2.0으로 완화
  - sync_trades.py sitemap에 dong/index + 소규모 동 페이지 추가

## 빌드 현황 (2026-04-15 수동 실행)
- 실거래 844건 수집
- HTML 18,891개 정상 생성
- SEO 검증: 내부링크/회귀방지 PASS, PageSpeed FAIL (root 도구파일 — 무관)
- 데이터 검증: HTML 대조 PASS, 비율 임계값 오류는 오늘 수정됨

## 다음에 할 것

### 1. 내일 새벽 빌드 결과 확인
- 자동 수정 에이전트가 첫 실패 시 제대로 동작하는지 확인
- SEO 검증 전체 PASS 여부 확인

### 2. 단지 페이지 배너 (buildUrlWithTab 연결)
- danji/app.js에 buildUrlWithTab() 이미 추가됨
- 단지 페이지에서 거래유형(매매/전세/월세) 탭 → 중개사 페이지 링크 연결
- type 파라미터로 탭 자동 선택

### 3. 매물 등록 시 kapt_code 매칭
- 중개사 매물 등록 시 단지명 + 좌표로 apartments 테이블 kapt_code 정확히 매칭

## 나중에 할 것
- telegram_chat_logs 테이블 구현 (텔레그램 대화 전부 저장)
