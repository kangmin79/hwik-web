-- AI 에이전트 자동 개선 시스템 테이블

-- 프롬프트 버전 관리
create table if not exists agent_prompts (
  id          bigserial primary key,
  draft_type  text not null,           -- 'property' | 'client'
  prompt_text text not null,
  score       float,                    -- 최근 eval 점수 (0~1)
  pass_count  int  default 0,
  total_count int  default 0,
  is_current  boolean not null default false,
  version     int  not null default 1,
  notes       text,                     -- 이 버전에서 개선한 점
  created_at  timestamptz default now()
);

-- 현재 버전 인덱스
create index if not exists agent_prompts_current_idx
  on agent_prompts(draft_type, is_current)
  where is_current = true;

-- eval 실행 기록 (매 run마다 저장)
create table if not exists eval_runs (
  id               bigserial primary key,
  run_id           text not null unique default gen_random_uuid()::text,
  property_prompt_version int,
  client_prompt_version   int,
  score            text,                -- A/B/C/D/F
  pass_count       int,
  total_count      int,
  single_accuracy  float,
  multi_accuracy   float,
  duration_ms      int,
  improved         boolean default false,  -- 이 run이 프롬프트 개선으로 이어졌는지
  created_at       timestamptz default now()
);

-- 개별 테스트 케이스 결과 (실패 케이스 학습 데이터)
create table if not exists eval_cases (
  id          bigserial primary key,
  run_id      text not null,
  case_id     int  not null,
  case_type   text not null,  -- 'single' | 'multi'
  draft_type  text not null,
  message     text,
  draft_json  jsonb,
  expected_intent text,
  expected_action text,
  actual_intent   text,
  actual_action   text,
  actual_reply    text,
  actual_updates  jsonb,
  pass        boolean not null,
  latency_ms  int,
  created_at  timestamptz default now()
);

create index if not exists eval_cases_run_idx on eval_cases(run_id);
create index if not exists eval_cases_pass_idx on eval_cases(pass, draft_type);

-- RLS: service_role만 접근
alter table agent_prompts enable row level security;
alter table eval_runs      enable row level security;
alter table eval_cases     enable row level security;
