-- ============================================================================
-- Module 2 — Project Management & Database Foundation
-- Table: public.projects
--
-- A project represents a website/application an authenticated user wants to
-- analyze for accessibility. Future scan records will reference projects via
-- project_id.
--
-- Run this file manually in the Supabase Dashboard → SQL Editor.
-- ============================================================================

-- gen_random_uuid() is built into PostgreSQL 13+; ensure pgcrypto is present
-- for older instances / explicitness.
create extension if not exists "pgcrypto";

-- ----------------------------------------------------------------------------
-- Table
-- ----------------------------------------------------------------------------
create table public.projects (
    id          uuid primary key default gen_random_uuid(),
    user_id     uuid not null references auth.users (id) on delete cascade,
    name        text not null check (char_length(trim(name)) between 1 and 100),
    description text not null default '' check (char_length(description) <= 2000),
    website_url text not null check (char_length(website_url) <= 2048),
    status      text not null default 'NOT_SCANNED'
                check (status in ('NOT_SCANNED', 'SCANNING', 'SCANNED', 'FAILED')),
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);

comment on table public.projects is
    'A website/application owned by a user, to be analyzed for accessibility.';

comment on column public.projects.status is
    'NOT_SCANNED | SCANNING | SCANNED | FAILED — scan lifecycle state.';

-- ----------------------------------------------------------------------------
-- Indexes (ownership queries + list ordering)
-- ----------------------------------------------------------------------------
create index projects_user_id_created_at_idx
    on public.projects (user_id, created_at desc);

-- ----------------------------------------------------------------------------
-- updated_at trigger
-- ----------------------------------------------------------------------------
create or replace function public.set_updated_at()
returns trigger
language plpgsql
as $$
begin
    new.updated_at = now();
    return new;
end;
$$;

drop trigger if exists projects_set_updated_at on public.projects;
create trigger projects_set_updated_at
    before update on public.projects
    for each row
    execute function public.set_updated_at();

-- ----------------------------------------------------------------------------
-- Row Level Security — users can only access their own projects
-- ----------------------------------------------------------------------------
alter table public.projects enable row level security;

create policy "Users can create their own projects"
    on public.projects for insert
    to authenticated
    with check (auth.uid() = user_id);

create policy "Users can view their own projects"
    on public.projects for select
    to authenticated
    using (auth.uid() = user_id);

create policy "Users can update their own projects"
    on public.projects for update
    to authenticated
    using (auth.uid() = user_id)
    with check (auth.uid() = user_id);

create policy "Users can delete their own projects"
    on public.projects for delete
    to authenticated
    using (auth.uid() = user_id);
