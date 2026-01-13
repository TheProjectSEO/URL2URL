-- Create job
create or replace function url_to_url.url_create_job(
  p_name text,
  p_site_a_url text,
  p_site_b_url text,
  p_categories text[] default array[]::text[],
  p_config jsonb default '{}'::jsonb
) returns url_to_url.crawl_jobs language sql as $$
  insert into url_to_url.crawl_jobs(name, site_a_url, site_b_url, categories, config, status)
  values (p_name, p_site_a_url, p_site_b_url, coalesce(p_categories, array[]::text[]), coalesce(p_config, '{}'::jsonb), 'pending')
  returning *;
$$;

-- Get job
create or replace function url_to_url.url_get_job(
  p_job_id uuid
) returns url_to_url.crawl_jobs language sql stable as $$
  select * from url_to_url.crawl_jobs where id = p_job_id;
$$;

-- List jobs (simple pagination)
create or replace function url_to_url.url_list_jobs(
  p_limit int default 50,
  p_offset int default 0
) returns setof url_to_url.crawl_jobs language sql stable as $$
  select * from url_to_url.crawl_jobs
   order by created_at desc
   limit coalesce(p_limit, 50)
  offset coalesce(p_offset, 0);
$$;

-- Update job status/timestamps
create or replace function url_to_url.url_update_job_status(
  p_job_id uuid,
  p_status text,
  p_started_at timestamptz default null,
  p_completed_at timestamptz default null
) returns boolean language plpgsql as $$
begin
  update url_to_url.crawl_jobs
     set status = p_status,
         started_at = coalesce(p_started_at, started_at),
         completed_at = coalesce(p_completed_at, completed_at)
   where id = p_job_id;
  return found;
end;
$$;

-- Update job fields
create or replace function url_to_url.url_update_job(
  p_job_id uuid,
  p_name text default null,
  p_categories text[] default null,
  p_config jsonb default null
) returns url_to_url.crawl_jobs language sql as $$
  update url_to_url.crawl_jobs
     set name = coalesce(p_name, name),
         categories = coalesce(p_categories, categories),
         config = coalesce(p_config, config)
   where id = p_job_id
  returning *;
$$;

-- Delete job
create or replace function url_to_url.url_delete_job(
  p_job_id uuid
) returns boolean language plpgsql as $$
begin
  delete from url_to_url.crawl_jobs where id = p_job_id;
  return found;
end;
$$;

-- Aggregate job stats (matches)
create or replace function url_to_url.url_get_job_stats(
  p_job_id uuid
) returns table(
  total_matches int,
  avg_score numeric,
  pending_count int,
  approved_count int,
  rejected_count int,
  needs_review_count int,
  confidence_distribution jsonb
) language plpgsql stable as $$
declare
  dist jsonb;
begin
  select jsonb_build_object(
    'exact_match', count(*) filter (where confidence_tier = 'exact_match'),
    'high_confidence', count(*) filter (where confidence_tier = 'high_confidence'),
    'good_match', count(*) filter (where confidence_tier = 'good_match'),
    'likely_match', count(*) filter (where confidence_tier = 'likely_match'),
    'manual_review', count(*) filter (where confidence_tier = 'manual_review'),
    'no_match', count(*) filter (where confidence_tier = 'no_match')
  ) into dist
  from url_to_url.matches where job_id = p_job_id;

  return query
  select
    count(*)::int as total_matches,
    avg(score)::numeric as avg_score,
    count(*) filter (where status = 'pending')::int as pending_count,
    count(*) filter (where status = 'approved')::int as approved_count,
    count(*) filter (where status = 'rejected')::int as rejected_count,
    count(*) filter (where confidence_tier in ('likely_match','manual_review','no_match'))::int as needs_review_count,
    coalesce(dist, '{}'::jsonb) as confidence_distribution
  from url_to_url.matches
  where job_id = p_job_id;
end;
$$;

