# 다음 세션 (2026-04-13)

## 최우선 1개

### 전체 코드 재검사: 2일 연속 danji 사고 재발 방지 3겹 방어 검증
- 2026-04-11 `app.js` 덮어쓰기, 04-12 `style.css` 덮어쓰기 — 같은 패턴(`extract_css_js()`) 2회 반복
- 방어 장치 3개가 실제로 막히는지 새 눈으로 재검사:
  1. `build_danji_pages.py` 에 `extract_css_js` 흔적 0건인지 (`git log --all -S`)
  2. `danji.html` 최상단 경고 헤더 존재 + `build_*.py` 가 `danji.html` 읽지 않는지
  3. `.github/workflows/sync-trades.yml` pre-push 게이트 스텝 존재 + 실제 failure 시 push 차단되는지 (dry-run 고려)
  4. **bot 수정 금지 파일 diff 블랙리스트 추가** — `sync-trades.yml` 의 `커밋 및 푸시` 스텝 앞에 `danji/style.css`, `danji/app.js` 가 staged diff 에 포함되면 즉시 exit 1. 줄수 알람 대신 "교체 자체를 거부" 하는 근본 방어. 구현은 5줄 bash 루프

## 다음 작업 대기열 (재검사 1~4 통과 확인 후 순서대로, **한 커밋 = 한 건**)

2026-04-12 전체 코드 감사에서 발견한 시한폭탄. 각각 독립 커밋. 감사 상세는 `docs/2026-04-12.md` (아래 섹션 추가 예정).

1. 🔴 **build_danji_pages.py:863 / build_dong_pages.py:637 / build_gu_pages.py:524 — "먼저 삭제, 나중에 검증" 순서 뒤집기.** Supabase 5분 장애 시 13,000 + 500 + 80개 페이지 전멸 시나리오. 순서를 (1) fetch → (2) 최소 개수 검증 → (3) 기존 파일 삭제 → (4) 새 파일 생성 으로 재배치. 각 파일 4~5줄.
2. 🔴 **sync_trades.py:1123 — sitemap 최소 URL 검증.** `if included + dong_count < 100: raise ValueError(...)` 3줄. 빈 sitemap 덮어쓰기 차단.
3. 🔴 **sync_trades.py:1073 — `/dong/` 루트 sitemap 추가.** 오늘 새벽 cron 에서 다시 누락 재발 확인(이메일 "파일 → sitemap 미등록: dong/index"). 2줄 추가.
4. 🟠 **bot 수정 금지 파일 diff 블랙리스트** (위 재검사 4번과 동일). `danji/style.css`, `danji/app.js` 를 staged diff 에 포함 시 exit 1. 5줄 bash.
5. 🟠 **build_dong_index.py — 수동 편집 보존 메커니즘.** dong/index.html 에 어제 손으로 보강한 FAQPage + ItemList 가 오늘 새벽 빌드에 다시 날아감(이메일 확인). `build_dong_index.py` 가 기존 파일의 JSON-LD 를 읽어서 머지하거나, 아예 템플릿에 하드코딩하거나 둘 중 하나.
6. 🟠 **build_danji_pages.py extract_gu_from_address() fallback 정규화.** `gu = ... or parts[0]` 패턴 6곳. address/location slug 불일치로 404 링크 누수. 중간 난이도.
7. 🟡 **MIN_DANJI_WITH_TRADE 상수 중앙화.** `build_dong_pages.py:51` + `build_og_images_dong.py:50` 중복 하드코딩. regions.py 또는 config.py 로 이전.
8. 🟡 **sync_trades.py 병렬 race condition.** seoul/incheon/gyeonggi job 병렬 write → build job 전 안정화 대기 또는 `needs` + 명시적 flush.

- 상세 맥락: [docs/2026-04-12.md](docs/2026-04-12.md)
