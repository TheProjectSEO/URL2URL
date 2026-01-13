# End‑to‑End Deployment & Test Runbook

This runbook walks you through applying DB migrations, deploying backend (Railway) and frontend (Vercel), pushing code to GitHub, and validating the platform. OCR is disabled by default; all matching improvements are text‑only (enriched embeddings, token_norm_v2, brand/category ontologies, variant parsing).

## 0) Prerequisites

- GitHub repo configured and remote set (`origin`).
- Supabase Postgres connection string (service role): `DATABASE_URL`.
- Railway project for the FastAPI backend.
- Vercel project for the Next.js frontend.
- Local tools: `git`, `psql` (or Supabase CLI), Railway CLI (optional), Vercel CLI (optional).

## 1) Review & Commit Local Changes

```bash
# From repo root
git status
# Add all changes
git add -A
# Commit with a descriptive message
git commit -m "feat: matcher_v2 pipeline, ontologies, variants, diagnostics, progress counters"
# Push to GitHub main (or your active branch)
git push origin main
```

If you work on a feature branch, open a PR and merge to `main` before deploying.

## 2) Apply Database Migrations (Supabase)

Migrations are snapshotted under `apps/api/migrations`. These are safe to re‑apply if the DB already has the schema/functions.

```bash
# Set service-role Postgres connection string (not the anon key)
export DATABASE_URL="postgres://USER:PASSWORD@HOST:PORT/DBNAME"

# Apply in order via psql
./apps/api/migrations/apply.sh
```

Quick verification (optional):

```sql
-- Run in psql connected to your DB
select extname from pg_extension where extname = 'vector';
\d+ url_to_url.products
-- Check IVFFlat index exists on products.embedding

-- Test a couple RPCs
select * from url_to_url.url_list_jobs(10,0);
select * from url_to_url.url_get_job_stats('00000000-0000-0000-0000-000000000000'::uuid) limit 1;
```

## 3) Configure Backend (Railway)

Environment variables (Railway → Variables):

- `PYTHON_ENV=production`
- `SUPABASE_SERVICE_KEY=<your supabase service key>`
- `CORS_ORIGINS=https://your-frontend.vercel.app` (comma‑separate if multiple)
- Optional: `ANTHROPIC_API_KEY=<your anthropic key>` (only if enabling AI validation)

Build & deploy:

- From dashboard: trigger a new deploy, or
- Railway CLI:
  ```bash
  cd apps/api
  railway up
  ```

Health checks:

```bash
# Replace with your Railway URL
curl https://<your-railway-app>.railway.app/api/health
curl https://<your-railway-app>.railway.app/api/health/detailed
```

## 4) Configure Frontend (Vercel)

Environment variables (Vercel → Settings → Environment Variables):

- `NEXT_PUBLIC_API_URL=https://<your-railway-app>.railway.app`

Deploy:

- Vercel dashboard: Deploy
- Or CLI:
  ```bash
  cd apps/web
  vercel --prod
  ```

## 5) Test the Platform (Text‑Only Signals)

Recommended per‑job toggles in the UI:

- Enable: Enriched embeddings, token_norm_v2, Brand ontology, Category ontology, Variant extractor
- Disable: OCR image text (toggle hidden by default), Price signals (not used)
- Optional: AI validation ON with a cap (e.g., 100/job) for borderline cases

Steps:

1. Create a job (Jobs → New) and set toggles as above.
2. Upload CSVs for Site A and Site B.
   - Required column: `url`
   - Optional: `title`, `brand`, `category` (helpful for accuracy)
   - `image_url` not required (OCR is disabled)
3. Start the job (Run).
4. Watch progress: stage, ETA, rate, and counters.
5. Review matches and auto‑approved results (≥90%); export CSV if needed.
6. Download “Diagnostics CSV” from Actions to audit component scores (semantic/token/attributes) on a sample.
7. Matcher Metrics card will show alias/synonym/variant activity.

Endpoints of interest:

- `GET /api/jobs/{id}` → job details
- `GET /api/jobs/{id}/progress` → real‑time stage/progress
- `GET /api/jobs/{id}/metrics` → persisted matcher metrics
- `GET /api/jobs/{id}/diagnostics?sample_size=50` → component scores CSV
- `GET /api/jobs/{id}/export` → matches CSV export

## 6) Optional: Enable AI Validation

- Set `ANTHROPIC_API_KEY` on backend.
- In Job Settings, enable AI validation, set min/max (e.g., 0.70–0.90) and cap (e.g., 100/job).
- The pipeline will adjust scores only for the borderline range and persist reasoning.

## 7) CORS & Environment Checks

- Ensure `CORS_ORIGINS` includes your Vercel URL (`https://your-frontend.vercel.app`).
- Frontend must point to the backend: `NEXT_PUBLIC_API_URL=https://<railway-url>`.
- Confirm `SUPABASE_SERVICE_KEY` is present and valid on the backend.

## 8) Troubleshooting

- 500 errors on API:
  - Check Railway logs, ensure `SUPABASE_SERVICE_KEY` is set.
  - Confirm migrations were applied (schema `url_to_url` and RPCs exist).
- CORS errors:
  - Verify `CORS_ORIGINS` contains your Vercel domain; redeploy backend.
- Empty matches:
  - Ensure CSVs have titles/brands/categories where possible for best accuracy.
  - Try enabling `embed_enriched_text` and `token_norm_v2` if not already.
- Slow jobs:
  - Large catalogs are processed in batches; monitor progress; adjust toggles if needed.

## 9) Rollback / Redeploy

- To rollback API:
  - Redeploy a previous commit on Railway or `git revert` locally → push → redeploy.
- To rollback web:
  - Vercel → Deployments → Promote previous deployment.

## 10) Appendix: Feature Flags (Per Job)

- `embed_enriched_text` (default OFF): embed `title + brand + category`.
- `token_norm_v2` (default OFF): stricter token cleanup for overlap.
- `use_brand_ontology` (default OFF): brand alias canonicalization.
- `use_category_ontology` (default OFF): category synonyms/related.
- `use_variant_extractor` (default OFF): shade/size/model/pack extraction and comparison.
- `ai_validation_enabled` (default OFF): optional Anthropic Claude validation; use `ai_validation_min`, `ai_validation_max`, and `ai_validation_cap` to control range and cost.

## 11) What’s Not Enabled Now

- OCR image text (disabled): UI toggle hidden; Docker image does not include Tesseract. Can be re‑enabled later if needed.
- Price signals: intentionally not part of scoring.

---

Once these steps are complete, you’ll be able to create jobs, run matching with the improved text‑based signals, monitor progress, export results, and audit component scores across verticals.

