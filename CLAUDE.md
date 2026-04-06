# 휙 (Hwik) 프로젝트

## 한 줄 요약
중개사가 손님에게 매물 "휙" 보내는 부동산 앱 — AI 시대에 맞는 에이전틱 SaaS

## 핵심 철학
- 한 카드 = 한 매물의 모든 핵심 정보
- 스와이프로 빠른 비교 (틴더 방식)
- 클릭/필터 최소화 → 검색창 하나로 AI가 처리
- 직방/다방처럼 목록→상세→뒤로가기 반복 NO
- "마찰을 가장 많이 제거한 제품이 승자" (에이전틱 SaaS 방향)

## 사용자 프로필
- 비전공자 (개발 경험 없음)
- claude.ai 웹 대화창 + Claude Code(VS Code) 사용
- 설명은 쉽고 직관적으로
- 코드 복붙보다 직접 파일 수정 방식 선호
- 승인 묻지 말고 바로 진행 선호

## 비즈니스 모델

### B2B2C 구조
```
중개사 → 휙에서 매물 링크 생성 → 카톡 전송 → 손님이 스와이프
```

### 수익
- 링크 생성당 300원 (약함 → 월 구독 또는 브랜딩 도구로 전환 고려)
- 초기 무료 (매물 관리 기능으로 락인)

### 바이럴 루프
```
중개사가 링크 보냄 → 손님이 열어봄 → 카드 안에 휙 검색 → 앱 다운로드
```
- 중개사 단톡방에서 매물 카드 이미지가 핵심 바이럴 포인트
- 카드 디자인 퀄리티가 곧 경쟁력

## 기술 스택

### 프론트엔드
- HTML/CSS/JavaScript (단일 파일)
- 카카오맵 SDK, 카카오 JS SDK

### 백엔드
- Supabase (PostgreSQL + Auth + Storage + Edge Functions)
- Supabase 프로젝트: jqaxejgzkchxbfzgzyzi
- API URL: https://api.hwik.kr

### 호스팅
- GitHub Pages (kangmin79.github.io/hwik-web)
- 커스텀 도메인: hwik.kr

### 외부 API
- 국토부 — 실거래가(매매/전세/월세), 단지목록, 건축물대장
- 카카오 — 주소→좌표 변환, 키워드 검색, 지도 JS, OAuth
- Claude (Anthropic) — 원고 텍스트 AI 생성
- OpenAI — text-embedding-3-small (벡터 검색)

## DB 구조 (Supabase)

### cards (매물 카드 — 핵심 테이블)
- id (text PK), agent_id (text FK→profiles)
- property (jsonb: type, price, location, complex, area, floor, room, features, category, rawText 등)
- trade_status (text: 계약가능/계약중/완료)
- photos (jsonb array), agent_comment (text)
- private_note (jsonb: memo, rawText)
- lat, lng (float8), coord_type (text)
- embedding (vector), search_text, search_text_private
- price_number, deposit, monthly_rent (bigint)
- contact_name, contact_phone (text)
- created_at, updated_at
- **주의: link_id 컬럼 없음** (id 자체가 링크 ID)

### profiles (중개사 프로필)
- id (uuid PK), phone, business_name, agent_name, address
- phone_verified (bool), style (text), profile_photo (text)
- og_version (text) — **코드에서 og_design_version 아닌 og_version**
- profile_photo_url (text), design_version (text), is_admin (bool)
- naver_map_url, office_lat, office_lon

### apartments (아파트 단지 마스터 — 6,369개)
- kapt_code, kapt_name, doro_juso, umd_nm, sgg, lat, lon, slug, pyeongs

### trades (실거래 내역)
- kapt_code (FK), trade_type, price, pyeong, floor, year, month, day

### 기타 테이블
- client_notes, match_notifications, card_shares, share_rooms, share_room_members
- search_logs, error_logs, memos, stations, schools, facilities

## Edge Functions

### parse-property
- POST `{text}` → AI 파싱 결과 반환 (**DB 저장 안 함**)
- 클라이언트에서 직접 cards 테이블에 insert 해야 함
- 응답: type, price, location, complex, area, floor, features, embedding, search_text, price_number 등

### embed-card
- POST `{card_id, text}` → 임베딩 생성 + cards 테이블 업데이트
- Authorization: Bearer <user_token> 필수

### auto-match
- POST `{card_id, agent_id}` → 손님 카드와 자동 매칭
- auth 체크 없음 (agent_id로 검증)

### match-properties
- POST `{client_card_id, agent_id, limit, threshold}` → 매칭 매물 반환

### search-property
- POST `{query, agent_id, limit, search_mode}` → 벡터 검색 결과
- search_mode: 'my' | 'shared' | 'client'

### batch-parse (별도 배포)
- POST `{text, agent_id, skip_save:true}` → 여러 매물 일괄 파싱

### extract-image (별도 배포)
- POST `{image: base64}` → OCR 텍스트 추출

### send-otp / verify-otp (별도 배포)
- 전화번호 OTP 인증

## 주요 파일 구조

### 기존 파일 (유지)
- `card_generator_v2_auth.html` — 기존 매물 등록 (다크 테마)
- `my_cards.html` — 기존 매물 관리 (다크 테마, 탭 구조)
- `mobile-v6.html` — 모바일 버전
- `property_view.html` — 손님용 카드 뷰어
- `index.html` — 메인 랜딩
- `config.js` — API 키, esc(), categorizeProperty()

### 새 파일 (hub-new)
- `hub-new/index.html` — **새 UI (허브 스타일, 단일 파일)**
  - 접속: https://hwik.kr/hub-new/
  - 기존 card_generator + my_cards의 모든 기능을 허브 UI로 통합
  - 라이트/다크 테마, 반응형 (4단계 브레이크포인트)

### 네이버 블로그 (별도 폴더)
- `Desktop/네이버/` — 블로그 원고 생성 시스템
  - test.py: 단지 조회 + 원고 생성
  - blog_web.py: Flask 웹 인터페이스
  - naver_blog_post.py: 네이버 자동 포스팅
  - build_apt_db.py: 단지 DB 구축
  - generate_banner.py: 배너 이미지 생성

## 디자인 결정사항

### 카드 디자인
- memo(사진) / noimg(그라데이션) 2가지로 통합
- 이미지 없는 카드: 다크 그라데이션 + 타이포그래피
- 템플릿 레지스트리 패턴

### 테마
- 라이트/다크 토글 (localStorage 유지)
- 라이트 액센트: #6366f1 (인디고)
- 다크 액센트: #facc15 (노란색)
- 매매: #ea580c, 전세: #4f46e5, 월세: #7c3aed

### Hub UI 철학
- 중앙 노드(중개사) + 5개 주변 노드(매물등록/내매물/손님/알림/공유방)
- 필터 버튼 없음 → 검색창 하나로 AI가 처리
- 비활성 자동복귀 **삭제** (중개사 업무 특성상 불필요 — 전화/외출 등)
- 5초 유휴 시 노드 순차 호버 애니메이션 (보라색 글로우 삼중 빛)
- 로딩 시 "휙" 로고 펄스 (모래시계 금지 — hwikLoading() 함수)
- 허브 노드 반경: 메인 265, 패널 열림 시 동적 축소
- **패널 열리면 무조건 세로 리스트** (render()에서 split 체크 → _renderVertical)
- 패널 닫으면 원형 복귀 (RADIUS=265)
- 선택된 노드가 맨 위로, 모든 노드 동일 너비(160px)
- 중앙 박스: 패널 시 80px로 축소 (CSS transition)

### 검색 시스템
- **통합 검색**: 어느 패널에서든 동일한 결과
  - 일반 검색어 → 내 매물 상위 5건 + 공유 매물
  - 손님 키워드(찾는분/손님/구합니다 등) → 손님 카드만
- 가격 파싱: 억+천+만
- 가격 조건: 이하/이상/미만/초과/넘는/부터/까지/아래 + 붙은 패턴 + 보증금 패턴
- 하드 필터: 거래유형/카테고리/거래상태 키워드 자동 분리
- 필드 가중치: 13개 필드 (type:10, complex:8, location:8 등)
- 벡터 검색: limit 50, 하드필터 후적용, 3개 모드 병렬 (my+shared+client)
- 학습: clickScores + queryClickScores 이중 추적

### UI 스타일 규칙
- 매물 입력 박스: **보라색(#6366f1) 2px 테두리**
- 손님에게 한마디: **민트색(#4ecdc4) 2px 테두리**
- 손님 등록 박스: **민트색(#4ecdc4) 2px 테두리**
- 매물 버튼 색상: 공유(초록) / 상세(파랑) / 수정(주황) / 삭제(빨강)
- 미리보기 열리면 헤더 숨김 (56px 공간 확보)
- 폰 목업: flex:1 (min 300, max 600) + 보내기 버튼 하단 고정
- 공유방 생성: prompt() 금지 → 모달 내 인라인 입력
- 내 정보: 보기 화면 아닌 **바로 수정 가능한 폼**

## 현재 작업 상태 (2026-03-30)

### ✅ hub-new 완료
- Auth (카카오 로그인, 프로필, OTP)
- 매물 등록 (단건+대량 통합, OCR, 사진, agent_comment, private_note)
- 내 매물 (통합검색, 체크박스+공유/상세/수정/삭제, 미리보기 연동, 실적)
- 손님 (등록 기능 추가, CRM 타임라인, 자연어 파싱, 매칭, 일정, 연락처 인라인 수정)
- 공유방 (관리 모달, 생성/삭제/탈퇴/멤버초대/공유해제, 에이전트별 그룹, 피커 모달)
- 알림 (지연/매칭/메모 + 달력)
- 메모 (읽음 자동 처리)
- 공유 (카카오+링크+SMS, OG 이미지, 방 선택 피커 + shared_by)
- 내 정보 (바로 수정 폼 + 연락처 읽기전용)
- 반응형 (4단계 + 세로 스택), 테마, PWA, 에러 수집
- 로딩 스플래시 (휙 로고), 유휴 시 순차 호버 애니메이션

### 🐛 수정된 버그들
- parse-property는 DB 저장 안 함 → 클라이언트에서 직접 insert
- link_id 컬럼 DB에 없음 → 모든 참조 제거
- og_design_version → og_version (DB 컬럼명 불일치)
- Supabase JS SDK에서 property->>type JSON 필터 → .neq() 사용
- 최신 카드가 전부 손님 → 서버 필터 필수
- 패널 열릴 때 원형 복구 문제 → render()에서 split 체크
- panel-area overflow:hidden → overflow-y:auto (스크롤 복원)
- 공유 시 shared_by 필드 누락 → 추가
- triggerAutoMatch 인증 헤더 → Auth.getToken()
- 손님 카드에 auto-match 호출 제거 (낭비)
- SQL 매칭 0% → _score 우선 표시
- 매칭 로드 race condition → promise 체인

### Edge Function 수정/신규 (2026-03-31)
- auto-match: CORS * + wanted_trade_type + 임베딩 memo 포함
- room-share-match: 신규 — 공유방 매물 → 멤버 손님 자동 매칭

### 📋 남은 작업
- 테스트 데이터 정리 (22,870건 중 대부분 테스트)
- MVP 전 모듈화 (현재 단일 파일 유지)
- 모바일 최적화
- 다크 테마 UI 점검

## 코드 규칙

### 파일 구조
- 단일 HTML 파일 (CSS/JS 인라인) — MVP 전까지 유지
- 외부 의존성 최소화

### 스타일
- 모바일 퍼스트
- 인라인 스타일 적극 사용 (CSS 캐시 문제 방지)

### 네이밍
- 한국어 주석 OK
- 함수명: camelCase
- CSS 클래스: kebab-case

### 면적/가격 표기 규칙
- "평" 단어 사용 금지 (법적으로 평은 공급면적 기준인데 데이터는 전용면적)
- 면적: 전용면적 ㎡ 표기 (예: 전용 84㎡)
- 공급면적: 있으면 별도 표시, 없으면 전용만
- 가격 비교: ㎡당 가격(전용면적 기준) 사용 (예: 4,094만/㎡)
- 추측/계산 데이터 절대 금지 — 모든 데이터 출처: 국토교통부
- 데이터 없는 항목은 표시 안 함

### 배포
- git push origin main → GitHub Pages 자동 배포
- 승인 묻지 말고 바로 배포
- Edge Function: supabase functions deploy [name]
- 실거래가: GitHub Actions 매일 새벽 1시(KST) 자동 동기화

## 컨텍스트 자동 저장 규칙
- 대화 컨텍스트가 70%를 넘으면 **즉시** `docs/YYYY-MM-DD.md` 파일에 아래 내용을 저장한다
  - 오늘 작업한 내용 (완료된 것)
  - 미완성 작업 (진행 중이거나 시작 못 한 것)
  - 다음 대화 시작점 (다음에 어디서 이어받으면 되는지 한 줄 요약)
- 파일명: `docs/2026-04-06.md` 형식 (오늘 날짜)
- 저장 후 사용자에게 "컨텍스트 70% 도달 — docs/YYYY-MM-DD.md 저장 완료" 라고 알린다
- 이 규칙은 사용자가 요청하지 않아도 자동으로 실행한다

## 참고
- 에이전틱 SaaS 방향: 버튼/필터 UI 대신 AI가 처리하는 구조
- 부동산 검색은 AI 검색창 하나가 필터 UI보다 효과적
- 중개사가 "말하듯이 적으면" AI가 카드로 만들어주는 게 핵심 가치
