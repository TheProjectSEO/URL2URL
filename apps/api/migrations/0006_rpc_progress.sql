-- Upsert current progress for a job
create or replace function url_to_url.url_update_progress(
  p_job_id uuid,
  p_stage text,
  p_current int,
  p_total int,
  p_rate numeric,
  p_eta_seconds int,
  p_message text
) returns boolean language plpgsql as $$
begin
  insert into url_to_url.job_progress(job_id, stage, current_count, total_count, rate, eta_seconds, message, updated_at)
  values (p_job_id, p_stage, p_current, p_total, p_rate, p_eta_seconds, p_message, now())
  on conflict (job_id)
  do update set stage = excluded.stage,
                current_count = excluded.current_count,
                total_count = excluded.total_count,
                rate = excluded.rate,
                eta_seconds = excluded.eta_seconds,
                message = excluded.message,
                updated_at = excluded.updated_at;
  return true;
end;
$$;

-- Get current progress for a job
create or replace function url_to_url.url_get_progress(
  p_job_id uuid
) returns table(
  job_id uuid,
  stage text,
  current_count int,
  total_count int,
  rate numeric,
  eta_seconds int,
  message text,
  updated_at timestamptz
) language sql stable as $$
  select job_id, stage, current_count, total_count, rate, eta_seconds, message, updated_at
    from url_to_url.job_progress
   where job_id = p_job_id;
$$;

-- Delete progress (cleanup)
create or replace function url_to_url.url_delete_progress(
  p_job_id uuid
) returns boolean language plpgsql as $$
begin
  delete from url_to_url.job_progress where job_id = p_job_id;
  return true;
end;
$$;

