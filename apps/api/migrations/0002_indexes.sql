-- Vector index for fast similarity search (IVFFlat)
-- Ensure the table has enough rows before creating IVFFlat index for best performance.

-- Create an IVF index on products.embedding scoped by job_id+site to improve locality
create index if not exists idx_products_embedding_ivf on url_to_url.products using ivfflat (embedding vector_cosine_ops) with (lists = 100);

-- Helpful supporting indexes
create index if not exists idx_products_site_url on url_to_url.products(site, url);

