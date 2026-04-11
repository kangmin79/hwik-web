-- 텔레그램 봇 연동용 컬럼 추가
-- 휙 봇 ↔ 중개사 1:1 대화 연동 (phase 1)
--
-- 연동 플로우:
--   1) 중개사가 텔레그램에서 @hwik_kr_bot 한테 /start
--   2) 봇이 폰번호 요구 → 중개사가 텍스트로 입력
--   3) profiles 에서 phone 매칭 → telegram_chat_id 저장
--   4) 이후 이 chat_id 로 오는 모든 메시지는 해당 agent_id 로 간주

alter table profiles
  add column if not exists telegram_chat_id bigint,
  add column if not exists telegram_linked_at timestamptz;

-- 한 텔레그램 계정 = 한 중개사 계정 강제
create unique index if not exists profiles_telegram_chat_id_key
  on profiles(telegram_chat_id)
  where telegram_chat_id is not null;
