# 다음 세션 할 일 (2026-04-12 저장)

## 1. GitHub Actions 시크릿 등록 (필수 — 안 하면 루프 안 돌아감)
- https://github.com/kangmin79/hwik-web/settings/secrets/actions
- Name: `HWIK_INTERNAL_SECRET` / Value: `hwik-internal-2026`
- 등록 후 Actions 탭에서 agent-improve-loop 첫 실행 확인

## 2. 자동 루프 모니터링
```sql
-- 점수 추이 (agent_prompts 버전별)
SELECT version, score, pass_count, total_count, notes, created_at
FROM agent_prompts ORDER BY created_at DESC;

-- eval 실행 현황
SELECT run_id, pass_count, total_count, single_accuracy, improved, created_at
FROM eval_runs ORDER BY created_at DESC LIMIT 20;

-- 자주 실패하는 케이스 TOP 10
SELECT message, expected_action, actual_action, count(*)
FROM eval_cases WHERE pass=false
GROUP BY message, expected_action, actual_action
ORDER BY count DESC LIMIT 10;
```

## 3. 점수 정체 시 할 것
- webhook에 deterministic 안전망 추가
  (AI가 continue 반환해도 필수필드 다 있으면 confirm으로 override)
- 또는 telegram-agent 모델을 Haiku → Sonnet 교체

## 4. 텔레그램 봇 남은 기능
- 사진 업로드 end-to-end 테스트
- 손님 등록 전체 플로우 테스트  
- telegram_chat_logs 구현 (대화 전체 저장 — 이미 설계 완료, 착수 예정)

## 변경된 값들
- HWIK_INTERNAL_SECRET = `hwik-internal-2026` (이번 세션에서 변경)
- HWIK_ANON_KEY 시크릿 새로 추가됨 (anon key 명시적 등록)
