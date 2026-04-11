-- 텔레그램 봇 손님 등록 진행 상태 저장
-- mobile.html _chatDraft 의 봇 버전
--
-- 플로우:
--   1) 중개사가 텔레그램에서 손님 조건 입력
--   2) parse-property → draft 병합
--   3) 누락 필수 필드(trade/location/price/category/contact) 있으면 질문 대기
--   4) 모두 채워지면 확인 카드(inline keyboard) 표시
--   5) 등록 버튼 → cards insert + draft 삭제
--
-- TTL: 오래된 draft는 수동 / 별도 cron 으로 청소 (1일 이상 방치 시)

create table if not exists telegram_drafts (
  chat_id bigint primary key,
  agent_id uuid not null references profiles(id) on delete cascade,
  draft jsonb not null default '{}'::jsonb,
  raw_text text not null default '',
  skipped text[] not null default '{}',
  missing_field text,
  state text not null default 'idle',   -- idle | confirm
  draft_type text,                        -- client | property
  updated_at timestamptz not null default now()
);

create index if not exists telegram_drafts_agent_idx
  on telegram_drafts(agent_id);

create index if not exists telegram_drafts_updated_idx
  on telegram_drafts(updated_at);
