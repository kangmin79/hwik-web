# 다음 세션 할 일 (2026-04-14 오후 저장)

## 오늘 완료한 것
- 전국 SEO 페이지 링크 전수 검사 (18,891 danji / 1,534 dong / 232 gu / 37 ranking)
- **버그 수정**: GU_SLUGS 실파일 검증 추가 → gu 404 링크 24개 제거
- **버그 수정**: 강원/충청/전라/경상/제주/세종 6,100개 단지 dong 링크 복원 (빌드 순서 문제)
- **기능 추가**: 주상복합·도시형 생활주택 보라색 태그 (H2 옆)
- **기능 추가**: get_prop_type() → COMPLEX_TYPE_MAP 기반 정확한 유형 표기
- **버그 수정**: build_intro_sentence 조사 오류 `주상복합로` → `주상복합으로`
- 전체 재빌드 배포 완료 (55c4d228e3)

## 현재 페이지 수
- danji 18,891 / dong 1,534 / gu 232 / ranking 37

## 다음에 할 일

### 1. OG 이미지 생성 (신규 지역분)
```
python build_og_images.py
```
증분 빌드 — 변경분만 생성

### 2. 월별 신규 단지 수집 자동화
Actions job (월 1회): collect_complexes → pyeongs → match_apt_seq

### 3. 랭킹 도 단위 탭 추가 여부 결정
현재 충북/충남 등은 전체(all) 탭에만 포함됨

### 4. agent.html — 단지 페이지 연결 (미완)
danji/app.js "휙 등록 매물" 섹션 → 중개사 있으면 agent.html 링크 추가
