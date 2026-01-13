-- Store embedding for a product
create or replace function url_to_url.url_store_embedding(
  p_product_id uuid,
  p_embedding float8[]
) returns boolean language plpgsql as $$
begin
  update url_to_url.products
     set embedding = p_embedding::vector
   where id = p_product_id;
  return found;
end;
$$;

-- Update product fields
create or replace function url_to_url.url_update_product(
  p_product_id uuid,
  p_title text,
  p_brand text,
  p_category text,
  p_price numeric,
  p_metadata jsonb
) returns boolean language plpgsql as $$
begin
  update url_to_url.products
     set title = coalesce(p_title, title),
         brand = coalesce(p_brand, brand),
         category = coalesce(p_category, category),
         price = coalesce(p_price, price),
         metadata = coalesce(p_metadata, metadata)
   where id = p_product_id;
  return found;
end;
$$;

-- Create product
create or replace function url_to_url.url_create_product(
  p_job_id uuid,
  p_site text,
  p_url text,
  p_title text,
  p_brand text,
  p_category text,
  p_price numeric,
  p_metadata jsonb
) returns url_to_url.products language sql as $$
  insert into url_to_url.products(job_id, site, url, title, brand, category, price, metadata)
  values (p_job_id, p_site, p_url, p_title, p_brand, p_category, p_price, coalesce(p_metadata, '{}'::jsonb))
  returning *;
$$;

-- Get single product
create or replace function url_to_url.url_get_product(
  p_product_id uuid
) returns url_to_url.products language sql stable as $$
  select * from url_to_url.products where id = p_product_id;
$$;

-- Get products by job (optional site)
create or replace function url_to_url.url_get_products_by_job(
  p_job_id uuid,
  p_site text default null
) returns setof url_to_url.products language sql stable as $$
  select * from url_to_url.products
   where job_id = p_job_id
     and (p_site is null or site = p_site)
   order by created_at asc;
$$;

-- pgvector candidate search (cosine similarity)
create or replace function url_to_url.search_similar_products(
  p_embedding float8[],
  p_job_id uuid,
  p_site text,
  p_limit int
) returns table (
  id uuid,
  title text,
  url text,
  brand text,
  category text,
  metadata jsonb,
  similarity float8
) language sql stable as $$
  select id, title, url, brand, category, metadata,
         1 - (embedding <=> (p_embedding::vector)) as similarity
    from url_to_url.products
   where job_id = p_job_id
     and site = p_site
     and embedding is not null
   order by embedding <=> (p_embedding::vector)
   limit coalesce(p_limit, 100);
$$;

