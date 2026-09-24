-- ============================================================
-- SUPABASE MULTI-TENANT SCHEMA — EasyFind Job Hunter
-- ============================================================
-- Run this in Supabase SQL Editor
-- ============================================================

-- Enable required extensions
create extension if not exists "uuid-ossp";
create extension if not exists "pgcrypto";

-- ============================================================
-- USERS (linked to auth.users via foreign key)
-- ============================================================
create table public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  full_name text,
  avatar_url text,
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  -- Preferences
  timezone text default 'Europe/Paris',
  language text default 'fr',
  daily_limit integer default 20,
  autopilot_enabled boolean default false
);

-- Auto-create user profile on signup
create or replace function public.handle_new_user()
returns trigger language plpgsql security definer as $$
begin
  insert into public.users (id, email, full_name, avatar_url)
  values (
    new.id,
    new.email,
    new.raw_user_meta_data->>'full_name',
    new.raw_user_meta_data->>'avatar_url'
  );
  return new;
end $$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- ============================================================
-- SETTINGS (1:1 with user)
-- ============================================================
create table public.settings (
  user_id uuid primary key references public.users(id) on delete cascade,
  -- Search parameters
  search_query text default 'développeur web',
  search_location text default 'France',
  search_radius_km integer default 50,
  search_experience text,
  search_contract_type text[],
  search_salary_min integer,
  search_remote boolean default false,
  -- AI Prompts (JSONB for flexibility)
  prompts jsonb default '{
    "qualification": "Analyse cette offre et dis si elle correspond à un profil développeur web fullstack...",
    "email_generation": "Rédige un email de candidature personnalisé...",
    "follow_up": "Rédige un email de relance poli..."
  }'::jsonb,
  -- Autopilot config
  autopilot_enabled boolean default false,
  autopilot_schedule text default '0 9 * * *', -- cron
  autopilot_max_per_run integer default 10,
  -- Blacklist/whitelist
  blacklisted_domains text[] default '{}',
  whitelisted_domains text[] default '{}',
  -- Notifications
  notify_on_reply boolean default true,
  notify_on_new_match boolean default true,
  notify_daily_summary boolean default false,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- ============================================================
-- SESSIONS (user's search sessions)
-- ============================================================
create table public.sessions (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid not null references public.users(id) on delete cascade,
  name text not null,
  kind text not null check (kind in ('job_search', 'prospecting', 'networking')),
  status text default 'active' check (status in ('active', 'paused', 'archived')),
  config jsonb default '{}'::jsonb,
  -- Stats cache
  stats jsonb default '{
    "total_companies": 0,
    "qualified": 0,
    "contacted": 0,
    "replied": 0,
    "emails_sent": 0
  }'::jsonb,
  autopilot_enabled boolean default false,
  last_run_at timestamptz,
  next_run_at timestamptz,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index idx_sessions_user_id on public.sessions(user_id);
create index idx_sessions_status on public.sessions(status);

-- ============================================================
-- COMPANIES (prospects/companies)
-- ============================================================
create table public.companies (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid not null references public.users(id) on delete cascade,
  session_id uuid not null references public.sessions(id) on delete cascade,
  -- Core info
  company_name text not null,
  website text,
  domain text,
  linkedin_url text,
  -- Location
  address text,
  city text,
  country text default 'France',
  postal_code text,
  -- Contact
  detected_email text,
  detected_phone text,
  contact_form_url text,
  contact_person text,
  contact_role text,
  -- Qualification
  status text default 'new' check (status in (
    'new', 'qualified', 'disqualified', 'contacted', 'sent',
    'replied', 'rejected', 'blacklisted', 'formulaire_en_ligne'
  )),
  qualification_notes text,
  qualification_score integer, -- 0-100
  -- Source tracking
  source text, -- 'serpapi', 'manual', 'import'
  source_url text,
  search_query text,
  -- Metadata
  raw_data jsonb default '{}'::jsonb,
  -- Email tracking
  latest_email_id uuid,
  latest_email_status text,
  latest_email_sent_at timestamptz,
  latest_reply_received_at timestamptz,
  latest_reply_status text,
  -- Timestamps
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  contacted_at timestamptz,
  qualified_at timestamptz
);

create index idx_companies_user_id on public.companies(user_id);
create index idx_companies_session_id on public.companies(session_id);
create index idx_companies_status on public.companies(status);
create index idx_companies_domain on public.companies(domain);
create index idx_companies_created_at on public.companies(created_at desc);

-- ============================================================
-- EMAILS (sent/received emails)
-- ============================================================
create table public.emails (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid not null references public.users(id) on delete cascade,
  company_id uuid not null references public.companies(id) on delete cascade,
  session_id uuid not null references public.sessions(id) on delete cascade,
  -- Direction
  direction text not null check (direction in ('outbound', 'inbound')),
  -- Gmail integration
  gmail_message_id text,
  gmail_thread_id text,
  gmail_label_ids text[],
  -- Content
  subject text not null,
  body_text text,
  body_html text,
  -- Recipients
  from_email text not null,
  to_emails text[] not null,
  cc_emails text[] default '{}',
  bcc_emails text[] default '{}',
  -- Status
  status text default 'draft' check (status in (
    'draft', 'queued', 'sent', 'delivered', 'opened', 'clicked',
    'replied', 'bounced', 'failed'
  )),
  -- AI generation
  generated_by_ai boolean default false,
  prompt_used text,
  -- Tracking
  sent_at timestamptz,
  opened_at timestamptz,
  clicked_at timestamptz,
  replied_at timestamptz,
  -- Error handling
  error_message text,
  retry_count integer default 0,
  -- Timestamps
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

create index idx_emails_user_id on public.emails(user_id);
create index idx_emails_company_id on public.emails(company_id);
create index idx_emails_session_id on public.emails(session_id);
create index idx_emails_status on public.emails(status);
create index idx_emails_gmail_thread_id on public.emails(gmail_thread_id);
create index idx_emails_created_at on public.emails(created_at desc);

-- ============================================================
-- OAUTH TOKENS (Google, etc.) - encrypted
-- ============================================================
create table public.oauth_tokens (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid not null references public.users(id) on delete cascade,
  provider text not null check (provider in ('google', 'microsoft', 'github')),
  -- Encrypted tokens (use pgcrypto or application-level encryption)
  access_token_enc bytea not null,
  refresh_token_enc bytea,
  expires_at timestamptz,
  scope text,
  token_type text default 'Bearer',
  created_at timestamptz default now(),
  updated_at timestamptz default now(),
  unique (user_id, provider)
);

-- ============================================================
-- SERPAPI KEYS (user-provided, encrypted)
-- ============================================================
create table public.serpapi_keys (
  user_id uuid primary key references public.users(id) on delete cascade,
  api_key_enc bytea not null,
  monthly_quota integer default 100,
  used_this_month integer default 0,
  quota_reset_at timestamptz default (date_trunc('month', now()) + interval '1 month'),
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

-- ============================================================
-- JOB LOG (audit trail)
-- ============================================================
create table public.job_log (
  id uuid primary key default uuid_generate_v4(),
  user_id uuid not null references public.users(id) on delete cascade,
  session_id uuid references public.sessions(id) on delete set null,
  company_id uuid references public.companies(id) on delete set null,
  email_id uuid references public.emails(id) on delete set null,
  action text not null,
  details jsonb default '{}'::jsonb,
  status text default 'success' check (status in ('success', 'error', 'warning')),
  error_message text,
  created_at timestamptz default now()
);

create index idx_job_log_user_id on public.job_log(user_id);
create index idx_job_log_session_id on public.job_log(session_id);
create index idx_job_log_created_at on public.job_log(created_at desc);

-- ============================================================
-- ROW LEVEL SECURITY (RLS)
-- ============================================================
alter table public.users enable row level security;
alter table public.settings enable row level security;
alter table public.sessions enable row level security;
alter table public.companies enable row level security;
alter table public.emails enable row level security;
alter table public.oauth_tokens enable row level security;
alter table public.serpapi_keys enable row level security;
alter table public.job_log enable row level security;

-- Users: can only see own profile
create policy "users_own" on public.users
  for all using (auth.uid() = id);

-- Settings: 1:1 with user
create policy "settings_own" on public.settings
  for all using (auth.uid() = user_id);

-- Sessions: user owns their sessions
create policy "sessions_own" on public.sessions
  for all using (auth.uid() = user_id);

-- Companies: user owns their companies
create policy "companies_own" on public.companies
  for all using (auth.uid() = user_id);

-- Emails: user owns their emails
create policy "emails_own" on public.emails
  for all using (auth.uid() = user_id);

-- OAuth tokens: user owns their tokens
create policy "oauth_tokens_own" on public.oauth_tokens
  for all using (auth.uid() = user_id);

-- SerpApi keys: user owns their key
create policy "serpapi_keys_own" on public.serpapi_keys
  for all using (auth.uid() = user_id);

-- Job log: user owns their logs
create policy "job_log_own" on public.job_log
  for all using (auth.uid() = user_id);

-- ============================================================
-- UPDATED_AT TRIGGERS
-- ============================================================
create or replace function public.update_updated_at_column()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end $$;

create trigger update_users_updated_at
  before update on public.users
  for each row execute procedure public.update_updated_at_column();

create trigger update_settings_updated_at
  before update on public.settings
  for each row execute procedure public.update_updated_at_column();

create trigger update_sessions_updated_at
  before update on public.sessions
  for each row execute procedure public.update_updated_at_column();

create trigger update_companies_updated_at
  before update on public.companies
  for each row execute procedure public.update_updated_at_column();

create trigger update_emails_updated_at
  before update on public.emails
  for each row execute procedure public.update_updated_at_column();

create trigger update_oauth_tokens_updated_at
  before update on public.oauth_tokens
  for each row execute procedure public.update_updated_at_column();

create trigger update_serpapi_keys_updated_at
  before update on public.serpapi_keys
  for each row execute procedure public.update_updated_at_column();

-- ============================================================
-- HELPER FUNCTIONS
-- ============================================================

-- Get current user's active session
create or replace function public.get_active_session()
returns uuid language sql stable as $$
  select id from public.sessions
  where user_id = auth.uid() and status = 'active'
  order by created_at desc limit 1
$$;

-- Get user's SerpApi usage
create or replace function public.get_serpapi_usage()
returns jsonb language sql stable as $$
  select jsonb_build_object(
    'used', coalesce(used_this_month, 0),
    'quota', coalesce(monthly_quota, 100),
    'remaining', greatest(coalesce(monthly_quota, 100) - coalesce(used_this_month, 0), 0),
    'reset_at', quota_reset_at
  ) from public.serpapi_keys where user_id = auth.uid()
$$;

-- Increment SerpApi usage
create or replace function public.increment_serpapi_usage()
returns void language plpgsql as $$
begin
  update public.serpapi_keys
  set used_this_month = used_this_month + 1,
      updated_at = now()
  where user_id = auth.uid();
end $$;

-- ============================================================
-- REALTIME PUBLICATION (optional)
-- ============================================================
alter publication supabase_realtime add table public.companies;
alter publication supabase_realtime add table public.emails;
alter publication supabase_realtime add table public.sessions;
alter publication supabase_realtime add table public.job_log;

-- ============================================================
-- STORAGE BUCKETS (for attachments, CVs, etc.)
-- ============================================================
-- Run in Supabase Dashboard > Storage
-- bucket: user-attachments (private, per user folder: {user_id}/)
-- bucket: cvs (private, per user folder: {user_id}/)