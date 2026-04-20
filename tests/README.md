# 매칭 E2E 스모크 테스트

브라우저가 실제로 돌리는 경로와 **100% 동일하게** 매칭 시스템을 검증합니다.
- 같은 엔드포인트 (`api.hwik.kr/functions/v1/...`)
- 같은 키 (anon key + 본인 JWT)
- 같은 insert 경로 (PostgREST + RLS 적용)

배포 전에 돌려서 실패하면 배포하지 않습니다.

## 1회 셋업 — JWT 추출

브라우저가 로그인 시 저장하는 JWT를 테스트가 재사용합니다. 실제 사용자 토큰이므로 브라우저와 동일한 결과가 나옵니다.

### 방법
1. https://hwik.kr/hub-new/ 접속해서 본인 카카오 계정으로 로그인
2. F12 → Console 탭
3. 아래 한 줄 붙여넣고 Enter:
   ```js
   copy(JSON.parse(localStorage.getItem(Object.keys(localStorage).find(k=>k.startsWith('sb-')&&k.endsWith('auth-token')))).access_token)
   ```
4. 클립보드에 JWT가 복사됨 (토큰은 1시간 후 만료 → 다시 추출)
5. 프로젝트 루트에 `.env.test` 파일 생성:
   ```
   HWIK_TEST_JWT=<붙여넣기>
   HWIK_TEST_AGENT_ID=<본인 user id>
   ```
   - `HWIK_TEST_AGENT_ID`는 콘솔에 `Auth.user.id` 찍으면 보임

## 실행

```bash
node tests/smoke_matching.mjs
```

### 예상 출력 (성공)
```
[1/4] 손님 카드 등록... OK (id: test_client_xxx)
[2/4] auto-match 호출... OK (matched: 2, saved: 2)
[3/4] match_notifications 확인... OK (2건)
[4/4] 테스트 카드 삭제... OK
✅ PASS
```

### 실패 시
- `auto-match 401`: JWT 만료 → 재추출
- `matched: 0`: 본인 계정에 매물이 1건도 없음 → 먼저 매물 등록
- `match_notifications 0건`: auto-match가 upsert는 했으나 조회 권한 문제 → RLS 확인

## 테스트가 하는 일

1. **손님 등록 경로** — `registerClient()`가 하는 그대로
   - parse-property 호출 (AI 파싱)
   - cards insert (테스트용 고유 id)
   - auto-match 호출 (본인 매물과 역방향 매칭)
   - match_notifications 조회 (알림 저장 확인)

2. **매물 등록 경로** — `confirmSave()`가 하는 그대로
   - 동일한 4단계

3. **정리** — 테스트 카드 전부 삭제 (id가 `test_`로 시작하는 것만)

## 테스트 이후 남은 데이터

테스트는 본인 계정에 실제로 카드를 만들었다가 지웁니다. 중간에 실패하면 `test_` 접두어 카드가 남을 수 있어요 → 재실행하면 시작할 때 지웁니다.

## 제약

- **기존 매칭 대상(본인 매물·손님) 데이터가 있어야** 의미가 있음 (0건이면 matched: 0이 정상)
- JWT 1시간 만료 → CI 자동화는 `HWIK_INTERNAL_SECRET` 쓰는 경로로 별도 구성 필요 (추후)
