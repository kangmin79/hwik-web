# 2026-04-26 단지 페이지 D 디자인 운영 배포

## 요약
헬리오시티 미리보기로 합의한 D 디자인을 13,000+ 단지 페이지 전 구간에 적용. PC/모바일 동시 적용. SSR + hydrated DOM 일치(클로킹 회피).

## 변경 파일
- 신규: `build_d_design.py` — D 디자인 SSR 풀콘텐츠 빌더 (헬퍼 함수 17개 + build_fallback_html_d)
- 신규: `danji/style-d.css` — D 디자인 CSS (design_d.html 추출 + SPA 적응 + 모바일 보정, 18.6KB)
- 수정: `build_danji_pages.py`
  - USE_D_DESIGN=1 시 build_fallback_html_d 사용 + style-d.css/Pretendard link 추가
  - app.js / style-d.css 캐시 키 = 날짜 + mtime (같은 날 변경분도 즉시 갱신)
  - build_jsonld() FAQPage 보강 (5년 매매/전세 평균/월세 평균/최고층/신축·노후/전세가율/dong 비교 — 7~9개 추가)
- 수정: `danji/app.js`
  - lineColor() D 공식 호선 색상 + 양방향 매칭(`l.includes(k) || k.includes(l)`)
  - 학교 초→중→고 정렬
  - applyDDesign(d) 통합 함수 — render() 끝에서 호출
  - 신규 D 변환 함수 11개:
    - _dExtractLocationSection (.tags → .location-section, 자체 _LC/_lineColor 포함)
    - _dInjectTradeKindBadge (활성 탭 색상 칩)
    - _dInjectNearbyStyle (단지명 앞 보라 뱃지 + 가격 주황 + 매매 칩)
    - _dInjectDanjiInfo (단지 소개 dl + 시세 요약 토글 + 인근 단지 SEO 문단)
    - _dEnrichFaq (FAQ 8~9개 보강)
    - _dDisableCardClick (가격 카드 onclick 제거)
    - _dPatchMap (카카오맵 링크 제거 + 클릭 → 풀화면)
    - _dPatchSeo (CTA 제거 + .seo-text 제거 + 데이터 안내 펼침/텍스트 교체 + 신고 버튼)
    - _dSplitFaq (visible 4 + hidden + 더보기)
    - _dReorderFaq (FAQ 를 더 알아보기 다음으로 이동)
    - _dInjectFooter (휙 소개·개인정보·이용약관 + hwik.kr footer)
  - applyDDesign 안 모든 _d* 함수 try-catch 격리
  - fillNearbyIfNeeded 끝에 _dInjectNearbyStyle 재호출 + date 컨테이너 추가

## 빌드 검증
- 헬리오시티(서울 송파) — 사용자 시각 OK
- 5개 시도 sample — 부산/인천/경기/강원/제주 fingerprint OK
- 서울 세대수 top5 (올림픽파크포레온/잠실파크리오/디에이치퍼스티어/잠실엘스/잠실리센츠) OK
- 모바일 (잠실리센츠) 시각 OK
- 13K 전체: 18,608개 생성, 203개 스킵
- 랜덤 5개 (인천/울산/경북/경남) fingerprint OK

## 디자인 변경 (시각)
- 단지명 색상: #0a0e1a → 인디고 #4338ca (오피스텔과 통일)
- 헤더: 좌(휙 36×36 노란 뱃지 + H1 + sub) / 우(location-section 지하철·학교)
- 호선 뱃지: 공식 색상 (8호선 #E6186C, 9호선 #BDB092 등)
- 학교 뱃지: 초=민트 / 중=파랑 / 고=옐로 (data-type attr)
- 거래 뱃지: 매매=주황 / 전세=파랑 / 월세=초록 칩
- 주변 단지 카드: 단지명 앞 [아파트/주상복합/도시형] 보라 뱃지 + 매매 칩 + 가격 주황
- 단지 소개 dl 2컬럼 + 시세 요약 토글 + 인근 단지 SEO 문단 (신규)
- 더 알아보기 → 자주 묻는 질문 (4 visible + 더보기)
- 데이터 안내 펼침 + 깔끔한 신고 버튼 (이모지 제거)
- footer 추가 (휙 소개 / 개인정보처리방침 / 이용약관 / hwik.kr)
- 지도: 카카오맵 링크 제거 + 지도 클릭 → 풀 지도 새창
- 가격 카드 onclick 제거 (smooth scroll 차단)
- CTA 노란 풀폭 버튼 제거

## 모바일 적응
- @media min-width 768px → min-width 1px (모든 폭 D)
- @media max-width 767px 보정:
  - 헤더 1열 스택 (flex-direction: column)
  - location-section width 100%
  - H1 줄바꿈 허용 (긴 단지명 안 잘리게)
  - location loc-row wrap

## SEO 영향
- 클로킹 안전: SSR fallback HTML (build_fallback_html_d) ≈ hydrated DOM (applyDDesign) 텍스트 일치
- JSON-LD FAQPage 16개 Q&A (D 보강 텍스트 동일)
- internal link 추가 (footer 3개)
- structured data (`<dl>`) 강화
- 텍스트 콘텐츠량 비슷 또는 증가 (FAQ 8~9개 추가)
- GSC 사용자 70% PC 에 맞는 디자인

## 주의
- 13,000+ HTML 파일 한 커밋 — push 시 GitHub Pages CDN 전파 ~10분
- 운영 반영 후 OLD 디자인 자동 복구 없음 — git revert 필요
