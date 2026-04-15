# 다음 세션 할 일 (2026-04-15 오후)

## 오늘 완료한 것 (SEO 집중 작업)
- danji 날짜 표시 KST 오늘날짜로 수정
- 주변 단지 가격 없는 항목 + 오피스텔(offi-) 404 필터
- sitemap lastmod → 오늘날짜, 4개 지역 분리 (seoul/metro/cities/pages)
- GSC sitemap 재제출 완료 (20,726페이지 인식)
- Twitter Card summary → summary_large_image 전체 수정
- ranking FAQPage 1→5개, gu ItemList 20→50개
- index.html SearchAction 제거 (URL 불일치)
- 충북-청주청원구 근본 원인 수정 (LOCATION_GU_FIX 35개 패턴)
- 단지 title에 위치 추가 (브라이튼여의도 실거래가 시세 · 영등포구 여의도동 | 휙)
- FAQ 위 요약 문단 추가 (build_danji_pages.py + app.js 둘 다)
- 워크플로우 git add에 서브 sitemap 파일 추가
- verify_seo.py sitemapindex 포맷 지원 + 이메일 파싱 키워드 수정

## 빌드 현황
- HTML 18,891개 정상, sitemap 4개 파일 커밋 확인
- 내부링크 0건, 회귀방지 PASS
- 이메일 sitemap: - → 다음 빌드부터 정상 출력 예정

## 다음에 할 것

### 1. 최근 실거래 클릭 → 상단 업데이트 기능
- 단지 페이지 최근 실거래 리스트 행 클릭 시 상단 가격/층수/날짜 업데이트
- 체류시간 증가 목적 (구글 긍정 신호)
- app.js 약 20줄 수정

### 2. dong/index.html FAQPage 누락 수정
- 검증 FAIL 항목, 간단히 수정 가능

### 3. GSC 순위 모니터링 (1~2주 후)
- 평균 게재순위 10.4 → 개선 여부 확인
- 노출수 225 → 증가 추이 확인

### 4. 백링크 확보 (데이터 안정화 후)
- 네이버 블로그 hwik.kr 링크 글 작성
- 노출 중인 단지 위주: 브라이튼여의도, 돈암삼성, 일성파크

## 나중에 할 것
- telegram_chat_logs 테이블 구현
- 매물 등록 시 kapt_code 매칭
