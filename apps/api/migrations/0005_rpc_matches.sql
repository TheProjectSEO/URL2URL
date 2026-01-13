-- Create match (simple path)
create or replace function url_to_url.url_create_match(
  p_job_id uuid,
  p_source_product_id uuid,
  p_matched_product_id uuid,
  p_score numeric,
  p_confidence_tier text,
  p_explanation text
) returns url_to_url.matches language sql as $$
  insert into url_to_url.matches(
    job_id, source_product_id, matched_product_id, score, confidence_tier, explanation, status)
  values (p_job_id, p_source_product_id, p_matched_product_id, p_score, p_confidence_tier, p_explanation, 'pending')
  returning *;
$$;

-- Update match status
create or replace function url_to_url.url_update_match_status(
  p_match_id uuid,
  p_status text
) returns url_to_url.matches language sql as $$
  update url_to_url.matches
     set status = p_status,
         reviewed_at = case when p_status in ('approved','rejected') then now() else reviewed_at end
   where id = p_match_id
  returning *;
$$;

-- Get match by id
create or replace function url_to_url.url_get_match(
  p_match_id uuid
) returns url_to_url.matches language sql stable as $$
  select * from url_to_url.matches where id = p_match_id;
$$;

-- Store match with top-5 candidates and flags
create or replace function url_to_url.store_match_with_candidates(
  p_job_id uuid,
  p_source_product_id uuid,
  p_matched_product_id uuid,
  p_score numeric,
  p_confidence_tier text,
  p_explanation text,
  p_top_5_candidates jsonb,
  p_is_no_match boolean,
  p_no_match_reason text
) returns url_to_url.matches language sql as $$
  insert into url_to_url.matches(
    job_id, source_product_id, matched_product_id, score, confidence_tier, explanation,
    top_5_candidates, is_no_match, no_match_reason, status)
  values (
    p_job_id, p_source_product_id, p_matched_product_id, p_score, p_confidence_tier, p_explanation,
    coalesce(p_top_5_candidates, '[]'::jsonb), coalesce(p_is_no_match, false), p_no_match_reason, 'pending')
  returning *;
$$;

-- Matches by job (flat join for UI)
create or replace function url_to_url.url_get_matches_by_job(
  p_job_id uuid,
  p_limit int default 100,
  p_offset int default 0
) returns table (
  id uuid,
  job_id uuid,
  source_product_id uuid,
  matched_product_id uuid,
  score numeric,
  confidence_tier text,
  explanation text,
  status text,
  created_at timestamptz,
  source_url text,
  source_title text,
  matched_url text,
  matched_title text
) language sql stable as $$
  select m.id, m.job_id, m.source_product_id, m.matched_product_id,
         m.score, m.confidence_tier, m.explanation, m.status, m.created_at,
         sp.url as source_url, sp.title as source_title,
         tp.url as matched_url, tp.title as matched_title
    from url_to_url.matches m
    join url_to_url.products sp on sp.id = m.source_product_id
    left join url_to_url.products tp on tp.id = m.matched_product_id
   where m.job_id = p_job_id
   order by m.created_at desc
   limit coalesce(p_limit, 100)
  offset coalesce(p_offset, 0);
$$;

