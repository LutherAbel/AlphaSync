-- AlphaSync Phase A schema
-- Run in Supabase SQL Editor once per environment.

create table if not exists public.profiles (
  id               uuid primary key references auth.users(id) on delete cascade,
  email            text,
  plan_expires_at  timestamptz,
  custom_initial   numeric,
  custom_monthly   numeric,
  dca_enabled      boolean,
  dca_day_of_month integer,
  created_at       timestamptz not null default now(),
  updated_at       timestamptz not null default now()
);

alter table public.profiles add column if not exists dca_enabled boolean;
alter table public.profiles add column if not exists dca_day_of_month integer;
alter table public.profiles drop constraint if exists profiles_dca_day_of_month_check;
alter table public.profiles
  add constraint profiles_dca_day_of_month_check
  check (dca_day_of_month is null or (dca_day_of_month between 1 and 28));

alter table public.profiles enable row level security;

drop policy if exists "profiles_select_own" on public.profiles;
create policy "profiles_select_own"
  on public.profiles for select
  using (auth.uid() = id);

drop policy if exists "profiles_update_own" on public.profiles;
create policy "profiles_update_own"
  on public.profiles for update
  using (auth.uid() = id)
  with check (auth.uid() = id);

-- Auto-create a profile row on new auth.users insert.
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.profiles (id, email)
  values (new.id, new.email)
  on conflict (id) do nothing;
  return new;
end;
$$;

drop trigger if exists on_auth_user_created on auth.users;
create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user();

-- Touch updated_at on profile updates.
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at
  before update on public.profiles
  for each row execute function public.touch_updated_at();
