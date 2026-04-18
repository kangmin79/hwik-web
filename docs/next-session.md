# 다음 세션 할 일 (2026-04-18 이후)

## 대기 1순위 — sync-trades 결과 확인
- 마지막 커밋 `1e98bdc16c7` (robots.txt AI + llms.txt 개정)
- danji 18,896 canonical/description/내부링크 반영 여부 확인
- Phase 2 canonical 검증 통과 필수

## 남은 작업 (우선순위)
1. **parse-property 401** — 매물 등록 실패, Auth.getToken() 타이밍 버그 가설
   - 브라우저 콘솔 `Auth.user`, `await Auth.sb.auth.getSession()` 확인
   - 해결안: `getToken()` 매번 실시간 세션에서 추출
2. **관찰 (2~4주)** — GSC 색인 2.19천 → 상승, 404 5.84% → 감소
3. **danji_pages 레거시 `apt-*`/`offi-*` 11,725개 정리** (선택)

## 보류 (사용자 판단 대기)
- 테스트 HTML 파일 삭제 (test_suite/theme-preview/select_template 등 — mobile-v6 보존) — "아직 삭제 하면 안될꺼 같아"
- apt-redirect 4,479개 meta-refresh 정적화 — 현재 404로 집계되나 방치 권장

## 오늘(2026-04-18) 추가 완료
- ✅ 자동 수정 에이전트 완전 제거
- ✅ verify_all.py Phase 5 빌드 로직과 정렬 (배포 차단 해소)
- ✅ Phase 6 내부 링크·리다이렉트 정합성 신설
- ✅ .gitignore 확장 (115 → 20)
- ✅ SEO 감사 스크립트 `seo_bot_audit.py` 신설
- ✅ canonical `.html` 통일 (dong/gu/ranking/danji 빌드 스크립트 전부)
- ✅ description 확장 (전 카테고리 100~130자)
- ✅ 내부 링크 `.html` 일관화 (5개 빌드 파일)
- ✅ danji 지역 랭킹 3종 링크 추가 (내부 링크 7 → 10~11)
- ✅ robots.txt AI 크롤러 12개 명시
- ✅ llms.txt 전면 개정

상세는 `docs/2026-04-18.md` 10장~20장 참조.
