-- Enable required extensions
create extension if not exists vector;

-- Dedicated schema
create schema if not exists url_to_url;

-- Jobs table
create table if not exists url_to_url.crawl_jobs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid,
  name text not null,
  site_a_url text not null,
  site_b_url text not null,
  categories text[] default array[]::text[],
  config jsonb default '{}'::jsonb,
  status text not null default 'pending',
  created_at timestamptz not null default now(),
  started_at timestamptz,
  completed_at timestamptz
);

-- Products table
create table if not exists url_to_url.products (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references url_to_url.crawl_jobs(id) on delete cascade,
  site text not null check (site in ('site_a','site_b')),
  url text not null,
  title text not null,
  brand text,
  category text,
  price numeric,
  embedding vector(384),
  metadata jsonb default '{}'::jsonb,
  created_at timestamptz not null default now()
);
create index if not exists idx_products_job_site on url_to_url.products(job_id, site);
create index if not exists idx_products_job on url_to_url.products(job_id);

-- Matches table
create table if not exists url_to_url.matches (
  id uuid primary key default gen_random_uuid(),
  job_id uuid not null references url_to_url.crawl_jobs(id) on delete cascade,
  source_product_id uuid not null references url_to_url.products(id) on delete cascade,
  matched_product_id uuid references url_to_url.products(id) on delete set null,
  score numeric not null,
  confidence_tier text not null,
  explanation text,
  top_5_candidates jsonb default '[]'::jsonb,
  is_no_match boolean default false,
  no_match_reason text,
  status text not null default 'pending',
  reviewed_by uuid,
  reviewed_at timestamptz,
  created_at timestamptz not null default now()
);
create index if not exists idx_matches_job on url_to_url.matches(job_id);
create index if not exists idx_matches_job_status on url_to_url.matches(job_id, status);

-- Progress table (for real-time polling + durability)
create table if not exists url_to_url.job_progress (
  job_id uuid primary key references url_to_url.crawl_jobs(id) on delete cascade,
  stage text not null,
  current_count integer not null default 0,
  total_count integer not null default 0,
  rate numeric not null default 0,
  eta_seconds integer not null default 0,
  message text,
  updated_at timestamptz not null default now()
);

