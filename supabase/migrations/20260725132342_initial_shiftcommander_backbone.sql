create extension if not exists pgcrypto;

create schema if not exists sc_core;
create schema if not exists sc_resolver;
create schema if not exists sc_audit;
create schema if not exists api;

revoke all on schema sc_core from public, anon, authenticated;
revoke all on schema sc_resolver from public, anon, authenticated;
revoke all on schema sc_audit from public, anon, authenticated;
revoke all on schema api from public, anon, authenticated;
grant usage on schema api to authenticated;

create type sc_core.schedule_version_status as enum ('DRAFT','RESOLVING','REVIEW_REQUIRED','APPROVED','PUBLISHED','SUPERSEDED','ARCHIVED');
create type sc_core.assignment_status as enum ('PROPOSED','REVIEW_REQUIRED','APPROVED','OVERRIDDEN','REJECTED','PUBLISHED');
create type sc_core.preference_level as enum ('PREFER','AVAILABLE','DO_NOT','UNAVAILABLE');
create type sc_core.seat_type as enum ('ATTENDANT','DRIVER','QRV','THIRD_RIDER');
create type sc_core.decision_type as enum ('APPROVE','OVERRIDE','REJECT','CLEAR');
create type sc_core.import_status as enum ('RECEIVED','VALIDATING','READY','APPLIED','PARTIAL','FAILED','ROLLED_BACK');

create table sc_core.organizations (
  id uuid primary key default gen_random_uuid(),
  code text not null unique,
  name text not null,
  timezone text not null default 'America/New_York',
  created_at timestamptz not null default now()
);

create table sc_core.stations (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references sc_core.organizations(id) on delete cascade,
  code text not null,
  name text not null,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  unique (organization_id, code)
);

create table sc_core.members (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references sc_core.organizations(id) on delete cascade,
  external_member_id text,
  first_name text not null,
  last_name text not null,
  rank text,
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (organization_id, external_member_id)
);

create table sc_core.member_qualifications (
  id uuid primary key default gen_random_uuid(),
  member_id uuid not null references sc_core.members(id) on delete cascade,
  qualification_code text not null,
  effective_from date not null default current_date,
  effective_to date,
  source text,
  created_at timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from),
  unique (member_id, qualification_code, effective_from)
);

create table sc_core.member_compensation_rates (
  id uuid primary key default gen_random_uuid(),
  member_id uuid not null references sc_core.members(id) on delete cascade,
  pay_type text not null check (pay_type in ('hourly','salary','volunteer')),
  hourly_rate numeric(10,2),
  overtime_multiplier numeric(5,2) not null default 1.5,
  effective_from date not null,
  effective_to date,
  created_at timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from),
  unique (member_id, effective_from)
);

create table sc_core.member_hour_caps (
  id uuid primary key default gen_random_uuid(),
  member_id uuid not null references sc_core.members(id) on delete cascade,
  weekly_cap_hours numeric(6,2) not null,
  override_cap_hours numeric(6,2),
  notes text,
  effective_from date not null,
  effective_to date,
  created_at timestamptz not null default now(),
  check (weekly_cap_hours >= 0),
  check (override_cap_hours is null or override_cap_hours >= 0),
  check (effective_to is null or effective_to >= effective_from),
  unique (member_id, effective_from)
);

create table sc_core.member_adr_numbers (
  id uuid primary key default gen_random_uuid(),
  member_id uuid not null references sc_core.members(id) on delete cascade,
  adr_number text not null,
  effective_from date not null,
  effective_to date,
  created_at timestamptz not null default now(),
  check (effective_to is null or effective_to >= effective_from),
  unique (member_id, effective_from)
);

create table sc_core.import_batches (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references sc_core.organizations(id) on delete cascade,
  source_system text not null,
  source_reference text,
  status sc_core.import_status not null default 'RECEIVED',
  received_at timestamptz not null default now(),
  applied_at timestamptz,
  summary jsonb not null default '{}'::jsonb,
  error_message text
);

create table sc_core.availability_occurrences (
  id uuid primary key default gen_random_uuid(),
  member_id uuid not null references sc_core.members(id) on delete cascade,
  import_batch_id uuid references sc_core.import_batches(id) on delete set null,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  preference sc_core.preference_level not null,
  source_system text not null,
  source_reference text,
  notes text,
  created_at timestamptz not null default now(),
  check (ends_at > starts_at)
);

create table sc_core.schedule_periods (
  id uuid primary key default gen_random_uuid(),
  organization_id uuid not null references sc_core.organizations(id) on delete cascade,
  period_start date not null,
  period_end date not null,
  label text,
  created_at timestamptz not null default now(),
  check (period_end >= period_start),
  unique (organization_id, period_start, period_end)
);

create table sc_core.schedule_versions (
  id uuid primary key default gen_random_uuid(),
  schedule_period_id uuid not null references sc_core.schedule_periods(id) on delete cascade,
  version_number integer not null,
  status sc_core.schedule_version_status not null default 'DRAFT',
  parent_version_id uuid references sc_core.schedule_versions(id) on delete set null,
  ruleset_version text,
  created_by uuid references auth.users(id) on delete set null,
  created_at timestamptz not null default now(),
  approved_at timestamptz,
  published_at timestamptz,
  notes text,
  unique (schedule_period_id, version_number)
);

create table sc_core.shifts (
  id uuid primary key default gen_random_uuid(),
  schedule_version_id uuid not null references sc_core.schedule_versions(id) on delete cascade,
  station_id uuid references sc_core.stations(id) on delete set null,
  shift_code text not null,
  starts_at timestamptz not null,
  ends_at timestamptz not null,
  required_staff_count integer not null default 0,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  check (ends_at > starts_at),
  check (required_staff_count >= 0),
  unique (schedule_version_id, shift_code)
);

create table sc_core.shift_units (
  id uuid primary key default gen_random_uuid(),
  shift_id uuid not null references sc_core.shifts(id) on delete cascade,
  unit_code text not null,
  unit_name text,
  active boolean not null default true,
  sort_order integer not null default 0,
  unique (shift_id, unit_code)
);

create table sc_core.shift_seats (
  id uuid primary key default gen_random_uuid(),
  shift_id uuid not null references sc_core.shifts(id) on delete cascade,
  shift_unit_id uuid references sc_core.shift_units(id) on delete cascade,
  seat_code text not null,
  seat_type sc_core.seat_type not null,
  required boolean not null default true,
  qualification_rule jsonb not null default '{}'::jsonb,
  sort_order integer not null default 0,
  unique (shift_id, seat_code)
);

create table sc_resolver.resolver_runs (
  id uuid primary key default gen_random_uuid(),
  schedule_version_id uuid not null references sc_core.schedule_versions(id) on delete cascade,
  resolver_version text not null,
  ruleset_version text,
  status text not null check (status in ('QUEUED','RUNNING','COMPLETED','FAILED','CANCELLED')),
  started_at timestamptz,
  completed_at timestamptz,
  input_snapshot jsonb not null default '{}'::jsonb,
  summary jsonb not null default '{}'::jsonb,
  error_message text,
  created_at timestamptz not null default now()
);

create table sc_resolver.candidates (
  id uuid primary key default gen_random_uuid(),
  resolver_run_id uuid not null references sc_resolver.resolver_runs(id) on delete cascade,
  shift_seat_id uuid not null references sc_core.shift_seats(id) on delete cascade,
  member_id uuid not null references sc_core.members(id) on delete cascade,
  eligible boolean not null,
  total_score numeric(12,4),
  hard_rule_failures jsonb not null default '[]'::jsonb,
  soft_factors jsonb not null default '[]'::jsonb,
  explanation text,
  rank_order integer,
  unique (resolver_run_id, shift_seat_id, member_id)
);

create table sc_resolver.assignments (
  id uuid primary key default gen_random_uuid(),
  resolver_run_id uuid not null references sc_resolver.resolver_runs(id) on delete cascade,
  shift_seat_id uuid not null references sc_core.shift_seats(id) on delete cascade,
  member_id uuid references sc_core.members(id) on delete set null,
  candidate_id uuid references sc_resolver.candidates(id) on delete set null,
  status sc_core.assignment_status not null default 'PROPOSED',
  explanation text,
  created_at timestamptz not null default now(),
  unique (resolver_run_id, shift_seat_id)
);

create table sc_resolver.exceptions (
  id uuid primary key default gen_random_uuid(),
  resolver_run_id uuid not null references sc_resolver.resolver_runs(id) on delete cascade,
  shift_id uuid references sc_core.shifts(id) on delete cascade,
  shift_seat_id uuid references sc_core.shift_seats(id) on delete cascade,
  exception_code text not null,
  severity text not null check (severity in ('INFO','WARNING','BLOCKING')),
  message text not null,
  details jsonb not null default '{}'::jsonb,
  resolved_at timestamptz,
  created_at timestamptz not null default now()
);

create table sc_core.assignment_decisions (
  id uuid primary key default gen_random_uuid(),
  assignment_id uuid not null references sc_resolver.assignments(id) on delete cascade,
  decision sc_core.decision_type not null,
  previous_member_id uuid references sc_core.members(id) on delete set null,
  selected_member_id uuid references sc_core.members(id) on delete set null,
  reason text,
  decided_by uuid references auth.users(id) on delete set null,
  decided_at timestamptz not null default now()
);

create table sc_core.published_schedules (
  id uuid primary key default gen_random_uuid(),
  schedule_version_id uuid not null unique references sc_core.schedule_versions(id) on delete restrict,
  publication_number integer not null,
  snapshot jsonb not null,
  published_by uuid references auth.users(id) on delete set null,
  published_at timestamptz not null default now()
);

create table sc_audit.events (
  id bigint generated always as identity primary key,
  organization_id uuid references sc_core.organizations(id) on delete set null,
  actor_user_id uuid references auth.users(id) on delete set null,
  event_type text not null,
  entity_type text not null,
  entity_id uuid,
  before_state jsonb,
  after_state jsonb,
  context jsonb not null default '{}'::jsonb,
  occurred_at timestamptz not null default now()
);

create index members_org_active_idx on sc_core.members (organization_id, active);
create index qualifications_member_dates_idx on sc_core.member_qualifications (member_id, effective_from, effective_to);
create index availability_member_time_idx on sc_core.availability_occurrences (member_id, starts_at, ends_at);
create index shifts_version_time_idx on sc_core.shifts (schedule_version_id, starts_at);
create index seats_shift_idx on sc_core.shift_seats (shift_id, sort_order);
create index resolver_runs_version_idx on sc_resolver.resolver_runs (schedule_version_id, created_at desc);
create index candidates_seat_rank_idx on sc_resolver.candidates (resolver_run_id, shift_seat_id, rank_order);
create index assignments_member_idx on sc_resolver.assignments (member_id);
create index exceptions_run_severity_idx on sc_resolver.exceptions (resolver_run_id, severity);
create index audit_entity_idx on sc_audit.events (entity_type, entity_id, occurred_at desc);

create or replace function sc_core.touch_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = pg_catalog, sc_core
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger members_touch_updated_at
before update on sc_core.members
for each row execute function sc_core.touch_updated_at();

create view api.schedule_version_summary
with (security_invoker = true)
as
select
  sv.id,
  sp.organization_id,
  sp.period_start,
  sp.period_end,
  sv.version_number,
  sv.status,
  sv.ruleset_version,
  sv.created_at,
  sv.approved_at,
  sv.published_at,
  count(distinct s.id) as shift_count,
  count(distinct ss.id) as seat_count
from sc_core.schedule_versions sv
join sc_core.schedule_periods sp on sp.id = sv.schedule_period_id
left join sc_core.shifts s on s.schedule_version_id = sv.id
left join sc_core.shift_seats ss on ss.shift_id = s.id
group by sv.id, sp.organization_id, sp.period_start, sp.period_end;

revoke all on api.schedule_version_summary from anon;
grant select on api.schedule_version_summary to authenticated;

insert into sc_core.organizations (code, name, timezone)
values ('ADR-FR', 'ShiftCommander ADR-FR', 'America/New_York')
on conflict (code) do nothing;
