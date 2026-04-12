-- data_reports: 사용자 데이터 오류 신고
create table if not exists public.data_reports (
  id          uuid primary key default gen_random_uuid(),
  danji_id    text not null,
  danji_name  text,
  report_type text not null, -- '가격 오류' | '면적 오류' | '단지 정보 오류' | '기타'
  memo        text,
  page_url    text,
  created_at  timestamptz default now()
);

-- 익명 insert 허용 (로그인 불필요)
alter table public.data_reports enable row level security;
create policy "anyone can insert reports"
  on public.data_reports for insert
  with check (true);

-- 관리자만 조회
create policy "service role can read reports"
  on public.data_reports for select
  using (auth.role() = 'service_role');
