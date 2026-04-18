-- 가입 직후 profiles row 자동 생성 트리거
-- 문제: 현재 auth.users 에는 있지만 profiles 에 row 가 없는 "유령 계정" 발생
--       (예: 0c3eab9f-717a-4b92-b5b8-c886d6a62a9d, backkui@naver.com, 2026-03-26 가입)
-- 원인: profiles insert 는 사용자가 "내 정보 저장" 버튼을 눌러야만 실행됨
-- 해결: auth.users insert 시 profiles 에 빈 row 자동 생성 → agent.html 등에서 "존재하지 않는 중개사" 표시 방지

create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, phone)
  values (new.id, coalesce(new.phone, ''))
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- 기존 orphan 복구: auth.users 에 있지만 profiles 에 없는 계정에 빈 row 삽입
insert into public.profiles (id, phone)
select u.id, coalesce(u.phone, '')
from auth.users u
left join public.profiles p on p.id = u.id
where p.id is null
on conflict (id) do nothing;
