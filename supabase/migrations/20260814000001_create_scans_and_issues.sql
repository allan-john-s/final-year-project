-- ============================================================================
-- Module 3A — Scanner Architecture & Database Foundation
-- Tables: public.scans, public.accessibility_issues
--
-- A scan records one scanner run against a project's website; accessibility
-- issues are the normalized findings of that run. Both tables are owned by
-- the project's user and protected by strict Row Level Security.
--
-- Run this file manually in the Supabase Dashboard → SQL Editor.
-- It is idempotent (drop ... if exists guards, extension guard).
-- ============================================================================

-- gen_random_uuid() is built into PostgreSQL 13+; ensure pgcrypto is present
-- for older instances / explicitness.
create extension if not exists "pgcrypto";

-- ----------------------------------------------------------------------------
-- Table: public.scans
-- ----------------------------------------------------------------------------
create table public.scans (
    id              uuid primary key default gen_random_uuid(),
    project_id      uuid not null references public.projects (id) on delete cascade,
    user_id         uuid not null references auth.users (id) on delete cascade,
    scanner_type    text not null
                    check (scanner_type in ('AXE', 'LIGHTHOUSE', 'PA11Y', 'WAVE', 'RESEARCH')),
    status          text not null default 'PENDING'
                    check (status in ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED')),

    -- lifecycle timing
    started_at      timestamptz,
    completed_at    timestamptz,
    duration_ms     bigint check (duration_ms is null or duration_ms >= 0),

    -- results
    summary         jsonb not null default '{}'::jsonb,
    total_issues    integer not null default 0 check (total_issues >= 0),
    critical_count  integer not null default 0 check (critical_count >= 0),
    serious_count   integer not null default 0 check (serious_count >= 0),
    moderate_count  integer not null default 0 check (moderate_count >= 0),
    minor_count     integer not null default 0 check (minor_count >= 0),
    accessibility_score numeric(5, 2) check (
        accessibility_score is null or accessibility_score between 0 and 100
    ),

    -- normalized scanner metadata (mirrors the normalized scan result model)
    scanner_name        text check (char_length(scanner_name) <= 100),
    scanner_version     text check (char_length(scanner_version) <= 50),
    wcag_version        text check (char_length(wcag_version) <= 10),
    scan_url            text check (char_length(scan_url) <= 2048),
    scan_depth          integer not null default 1 check (scan_depth >= 1),
    pages_scanned       integer not null default 0 check (pages_scanned >= 0),
    browser_name        text check (char_length(browser_name) <= 100),
    browser_version     text check (char_length(browser_version) <= 50),
    user_agent          text check (char_length(user_agent) <= 512),
    total_dom_elements  integer not null default 0 check (total_dom_elements >= 0),
    tested_elements     integer not null default 0 check (tested_elements >= 0),
    normalization_duration_ms integer check (normalization_duration_ms is null or normalization_duration_ms >= 0),
    persistence_duration_ms   integer check (persistence_duration_ms is null or persistence_duration_ms >= 0),

    created_at      timestamptz not null default now()
);

comment on table public.scans is
    'A single scanner run against a project website, owned by the project user.';

comment on column public.scans.status is
    'PENDING | RUNNING | COMPLETED | FAILED — controlled scan lifecycle.';
comment on column public.scans.scanner_type is
    'AXE | LIGHTHOUSE | PA11Y | WAVE | RESEARCH — which engine produced this scan.';
comment on column public.scans.summary is
    'Flexible per-run summary (e.g. per-page breakdown); counts are also denormalized.';

-- ----------------------------------------------------------------------------
-- Table: public.accessibility_issues
-- ----------------------------------------------------------------------------
create table public.accessibility_issues (
    id               uuid primary key default gen_random_uuid(),
    scan_id          uuid not null references public.scans (id) on delete cascade,

    -- normalized finding
    rule_id          text not null check (char_length(rule_id) between 1 and 100),
    rule_name        text not null check (char_length(rule_name) between 1 and 200),
    description      text not null default '' check (char_length(description) <= 4000),
    help             text not null default '' check (char_length(help) <= 2000),
    help_url         text not null default '' check (char_length(help_url) <= 2048),
    impact           text not null
                     check (impact in ('CRITICAL', 'SERIOUS', 'MODERATE', 'MINOR')),
    wcag_level       text check (wcag_level in ('A', 'AA', 'AAA')),
    tags             jsonb not null default '[]'::jsonb,
    element_selector text not null default '' check (char_length(element_selector) <= 2000),
    html_snippet     text not null default '' check (char_length(html_snippet) <= 8000),
    failure_summary  text not null default '' check (char_length(failure_summary) <= 4000),
    xpath            text not null default '' check (char_length(xpath) <= 4000),
    css_path         text not null default '' check (char_length(css_path) <= 4000),
    dom_path         text not null default '' check (char_length(dom_path) <= 4000),
    screenshot_path  text not null default '' check (char_length(screenshot_path) <= 2048),

    created_at       timestamptz not null default now()
);

comment on table public.accessibility_issues is
    'A normalized accessibility finding from a scan, owned via its scan.';
comment on column public.accessibility_issues.impact is
    'CRITICAL | SERIOUS | MODERATE | MINOR — controlled severity.';

-- ----------------------------------------------------------------------------
-- Indexes (ownership queries + list ordering + status lookups)
-- ----------------------------------------------------------------------------
create index scans_user_id_created_at_idx
    on public.scans (user_id, created_at desc);

create index scans_project_id_created_at_idx
    on public.scans (project_id, created_at desc);

-- RUNNING scans are the hot poll target for the future scheduler; a partial
-- index keeps that lookup cheap without indexing low-cardinality statuses.
create index scans_running_status_idx
    on public.scans (status) where status = 'RUNNING';

-- (scan_id, impact) serves per-scan lookups (incl. FK cascade deletes) and
-- impact-count aggregation in one index.
create index accessibility_issues_scan_id_impact_idx
    on public.accessibility_issues (scan_id, impact);

-- ----------------------------------------------------------------------------
-- Row Level Security — users can only access scans/issues they own
-- ----------------------------------------------------------------------------
alter table public.scans enable row level security;
alter table public.accessibility_issues enable row level security;

-- --- scans ---------------------------------------------------------------

create policy "Users can create scans on their own projects"
    on public.scans for insert
    to authenticated
    with check (
        auth.uid() = user_id
        and exists (
            select 1 from public.projects p
            where p.id = project_id and p.user_id = auth.uid()
        )
    );

create policy "Users can view their own scans"
    on public.scans for select
    to authenticated
    using (auth.uid() = user_id);

-- UPDATE can move a scan through its lifecycle (status, timings, counts) but
-- never reassign ownership: user_id must stay the caller and project_id must
-- keep pointing at a project the caller owns.
create policy "Users can update their own scans"
    on public.scans for update
    to authenticated
    using (auth.uid() = user_id)
    with check (
        auth.uid() = user_id
        and exists (
            select 1 from public.projects p
            where p.id = project_id and p.user_id = auth.uid()
        )
    );

create policy "Users can delete their own scans"
    on public.scans for delete
    to authenticated
    using (auth.uid() = user_id);

-- --- accessibility_issues --------------------------------------------------

create policy "Users can view issues of their own scans"
    on public.accessibility_issues for select
    to authenticated
    using (exists (
        select 1 from public.scans s
        where s.id = scan_id and s.user_id = auth.uid()
    ));

-- A malicious client cannot attach an issue to someone else's scan: the
-- referenced scan must belong to the caller.
create policy "Users can insert issues into their own scans"
    on public.accessibility_issues for insert
    to authenticated
    with check (exists (
        select 1 from public.scans s
        where s.id = scan_id and s.user_id = auth.uid()
    ));

create policy "Users can update issues of their own scans"
    on public.accessibility_issues for update
    to authenticated
    using (exists (
        select 1 from public.scans s
        where s.id = scan_id and s.user_id = auth.uid()
    ))
    with check (exists (
        select 1 from public.scans s
        where s.id = scan_id and s.user_id = auth.uid()
    ));

create policy "Users can delete issues of their own scans"
    on public.accessibility_issues for delete
    to authenticated
    using (exists (
        select 1 from public.scans s
        where s.id = scan_id and s.user_id = auth.uid()
    ));
