# 다음 세션 할 일 (2026-04-19 밤 이후)

## 세션 시작 멘트
"docs/next-session.md + docs/2026-04-19-matching.md 보고 이어서 해줘"

## 오늘 종착점 — 아파트 단지 매칭 완성 + ES256 인증 해결
- 좌표 기반 매칭 시스템 구축 (apartments 30,999건 카카오 geocode 배치 완료)
- Waterfall 3단계 매칭 (도로명 → 지번 → 이름+지역)
- 공식 A코드 우선, 이름 토큰 검증 (False positive 0%)
- Reference Test: 도로명 91% / 지번 89% 실질 정확률
- ES256 JWT 이슈 해결 (Edge Function 8개 `--no-verify-jwt` + Auth API fetch)
- hub-new 매칭 결과 토스트 + 연락처 UI 박스 개선
- 커밋: e0a10e14c93 → 6cfca8739f1 → d66bf87d337 → ebe3ccb6b3e

## 1순위 — 실사용 테스트
- hub-new 강새로고침 후 본인 계정으로 매물 5~10개 등록
- 매칭 토스트 실제 동작 확인 (아파트/오피스텔/빌라)
- my 매물 / client / 공유방 / 검색도 잘 되는지 (ES256 수정 후 모든 패널 확인)

## 2순위 — Step 3 정규식 버그 (미수정, 엣지)
- `[가-힣]+(?:동|읍|면|리)\b` 의 `\b`가 한글 뒤 작동 안 함 (locate-card + test script)
- Waterfall Step 3 (이름+지역 fallback)가 현재 무용. 수정 시 엣지 케이스 3~5% 복구 예상
- 중개사 실전 입력 시 "구+동+단지명" 패턴이면 활성화 가치 있음

## 3순위 — 다른 Edge Function ES256 확인
- `auto-improve`, `eval-agent`, `weekly-keyword-report`, `telegram-agent`, `telegram-webhook`, `report-danji` 등
- 사용자 토큰 쓰는지, 쓰면 동일 조치 (verify_jwt=false + Auth API fetch)

## 보류 중 — 오늘 안 한 것
- apartments DB 중복 레코드 정리 (공식 A + 비공식 apt-*/offi-* 같은 단지)
- 모든 카테고리(오피스텔/빌라/상가) 주소→좌표 저장 확장
- hub-new 매칭 결과 수동 수정 UI ("이 단지 아니에요" 버튼)
- 매물 파싱의 한글→숫자 오인식 (백→100) 후처리

## 사업 방향 (변동 없음)
플라이휠 연결 페이즈 — 신규 기능 금지, 있는 것 잇기만.
결제는 WAU 40~50 or 일 클릭 100 달성 후.
