# URL-to-URL Product Matching Engine

> **Single Source of Truth** - All project documentation lives here. Do NOT create additional MD files.

---

## Quick Start

```bash
# Activate virtual environment
source venv/bin/activate

# Run product matching (local CSV files)
python run_pipeline.py --match-only \
    --site-a-data data/nykaa.csv \
    --site-b-data data/purplle.csv \
    --output output/matches.csv

# Run full pipeline (crawl + match)
python run_pipeline.py \
    --crawl \
    --site-a https://www.nykaa.com \
    --site-b https://www.purplle.com \
    --categories "lipstick,foundation,serum"

# Run tests
python test_matcher.py
```

---

## Project Overview

**Purpose**: Semantic product matching between e-commerce websites using ML embeddings.

**Use Cases**:
- Competitive pricing intelligence
- Product catalog reconciliation
- Cross-marketplace analytics

**Current Sites Supported**:
- **Site A**: Nykaa (nykaa.com)
- **Site B**: Purplle (purplle.com)

**Performance** (Phase 2 Results):
- 99 Nykaa products matched against 655 Purplle products
- 34 high-confidence matches (score > 0.70)
- Processing time: ~45 seconds

---

## Infrastructure Credentials

### Railway (Deployment)

```yaml
RAILWAY_API_KEY: 3475fb29-620f-4c97-a9f7-6a72376e06ac
RAILWAY_DOCS: https://docs.railway.com/reference/cli-api
```

### Supabase (Database)

```yaml
SUPABASE_PROJECT_ID: qyjzqzqqjimittltttph
SUPABASE_URL: https://qyjzqzqqjimittltttph.supabase.co
SUPABASE_SCHEMA: url_to_url
SUPABASE_DASHBOARD: https://supabase.com/dashboard/project/qyjzqzqqjimittltttph/editor/201115?schema=url_to_url
```

> **CRITICAL**: NEVER use the `public` schema. All tables MUST be in `url_to_url` schema.

---

## Architecture

### Current Architecture (CLI Tool)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                      URL-TO-URL MATCHING ENGINE                         │
└─────────────────────────────────────────────────────────────────────────┘

┌──────────────────┐     ┌──────────────────┐     ┌──────────────────────┐
│  Nykaa Crawler   │────▶│   URL Mapper     │────▶│    Output CSV        │
│ (scrape_nykaa.py)│     │ (url_mapper.py)  │     │ (matches.csv)        │
└──────────────────┘     └──────────────────┘     └──────────────────────┘
         │                        ↑
         │                        │
┌──────────────────┐              │
│ Purplle Crawler  │──────────────┘
│(scrape_purplle.py)
└──────────────────┘

Data Flow:
1. Crawlers extract products → CSV files
2. URL Mapper loads CSVs → generates embeddings
3. Semantic matching → confidence scores
4. Output → matches.csv with explanations
```

### Future Architecture (Full App)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        URL-TO-URL MATCHING APP                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────┐
│   Next.js Frontend  │────▶│   FastAPI Backend   │────▶│    Supabase     │
│   (Vercel/Railway)  │     │     (Railway)       │     │  (url_to_url)   │
└─────────────────────┘     └─────────────────────┘     └─────────────────┘
         │                           │                          │
         │                           │                          │
         └───────────────────────────┼──────────────────────────┘
                                     │
                            ┌────────▼────────┐
                            │   Playwright    │
                            │   Cloud Crawler │
                            │    (Railway)    │
                            └─────────────────┘
```

---

## Tech Stack

### Current (CLI Tool)
| Component | Technology |
|-----------|------------|
| Language | Python 3.11+ |
| ML Model | sentence-transformers/all-MiniLM-L6-v2 |
| Embeddings | 384 dimensions, L2 normalized |
| Crawling | Playwright (headless browser) |
| Data Storage | CSV files (local) |

### Future (Full App)
| Component | Technology |
|-----------|------------|
| Frontend | Next.js 14 (App Router) |
| Backend | FastAPI |
| Database | Supabase (PostgreSQL) |
| Auth | Supabase Auth |
| Hosting | Railway |
| Vector Store | pgvector (Supabase extension) |

---

## Database Schema

**Schema**: `url_to_url` (NOT public)

### Tables (To Be Created)

```sql
-- Enable pgvector extension (run once)
CREATE EXTENSION IF NOT EXISTS vector;

-- Organizations (multi-tenant support)
CREATE TABLE url_to_url.organizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Crawl Jobs
CREATE TABLE url_to_url.crawl_jobs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    org_id UUID REFERENCES url_to_url.organizations(id),
    name TEXT NOT NULL,
    site_a_url TEXT NOT NULL,
    site_b_url TEXT NOT NULL,
    categories JSONB DEFAULT '[]',
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    config JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT now(),
    started_at TIMESTAMPTZ,
    completed_at TIMESTAMPTZ
);

-- Crawled Products
CREATE TABLE url_to_url.products (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES url_to_url.crawl_jobs(id) ON DELETE CASCADE,
    site TEXT NOT NULL CHECK (site IN ('site_a', 'site_b')),
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    brand TEXT,
    category TEXT,
    price DECIMAL,
    metadata JSONB DEFAULT '{}',
    embedding vector(384),
    created_at TIMESTAMPTZ DEFAULT now(),
    UNIQUE(job_id, url)
);

-- Match Results
CREATE TABLE url_to_url.matches (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES url_to_url.crawl_jobs(id) ON DELETE CASCADE,
    source_product_id UUID REFERENCES url_to_url.products(id) ON DELETE CASCADE,
    matched_product_id UUID REFERENCES url_to_url.products(id) ON DELETE CASCADE,
    score DECIMAL NOT NULL CHECK (score >= 0 AND score <= 1),
    confidence_tier TEXT CHECK (confidence_tier IN ('exact_match', 'high_confidence', 'good_match', 'likely_match', 'manual_review', 'no_match')),
    explanation TEXT,
    status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    reviewed_by UUID,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Job Progress (real-time tracking)
CREATE TABLE url_to_url.job_progress (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id UUID REFERENCES url_to_url.crawl_jobs(id) ON DELETE CASCADE,
    site TEXT NOT NULL CHECK (site IN ('site_a', 'site_b')),
    products_found INTEGER DEFAULT 0,
    products_matched INTEGER DEFAULT 0,
    current_category TEXT,
    current_url TEXT,
    rate DECIMAL,
    eta_seconds INTEGER,
    updated_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for performance
CREATE INDEX idx_products_job_site ON url_to_url.products(job_id, site);
CREATE INDEX idx_products_embedding ON url_to_url.products USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX idx_matches_job ON url_to_url.matches(job_id);
CREATE INDEX idx_matches_status ON url_to_url.matches(job_id, status);
CREATE INDEX idx_job_progress_job ON url_to_url.job_progress(job_id);
```

---

## Matching Algorithm

### Multi-Signal Scoring

```python
Final Score = (0.60 x Semantic) + (0.25 x Token Overlap) + (0.15 x Attributes)
```

| Signal | Weight | Method |
|--------|--------|--------|
| Semantic Similarity | 60% | sentence-transformers cosine similarity |
| Token Overlap | 25% | Jaccard similarity of cleaned tokens |
| Attribute Match | 15% | Brand, shade, color, finish matching |

### Confidence Tiers

| Score | Confidence | Tier | Needs Review |
|-------|------------|------|--------------|
| 0.95+ | 100% | exact_match | No |
| 0.90-0.94 | 90% | high_confidence | No |
| 0.80-0.89 | 80% | good_match | No |
| 0.70-0.79 | 70% | likely_match | Yes |
| 0.50-0.69 | 50% | manual_review | Yes |
| <0.50 | 0% | no_match | Yes |

### Grounded Explanations

For every match below 100%, the system generates specific reasons:
- "Brand mismatch: Lakme vs Maybelline"
- "Shade differs: 128 vs 130"
- "Semantic similarity below threshold: 0.87"

---

## File Structure

```
urltourl/
├── CLAUDE.md                 # THIS FILE - Single source of truth
├── run_pipeline.py           # Main CLI entry point
├── url_mapper.py             # Matching engine (600 lines)
├── test_matcher.py           # Unit tests
├── requirements.txt          # Python dependencies
├── quick_test.sh             # Quick test script
│
├── crawler/                  # Playwright crawlers
│   ├── nykaa_crawler.py      # Nykaa product extractor
│   └── purplle_crawler.py    # Purplle product extractor
│
├── scrape_nykaa.py           # Standalone Nykaa scraper
├── scrape_purplle.py         # Standalone Purplle scraper
│
├── data/                     # Crawled data
│   ├── checkpoints/          # Crawl state checkpoints
│   ├── nykaa/                # Nykaa products (CSV)
│   └── purplle/              # Purplle products (CSV)
│
├── output/                   # Match results
│   ├── demo_run/             # Demo results
│   ├── test_run/             # Test results
│   └── full_run/             # Production results
│
├── docs/
│   └── archive/              # Deprecated documentation
│       ├── README.old.md
│       ├── PROJECT_SUMMARY.old.md
│       ├── USAGE_GUIDE.old.md
│       └── INSTALL.old.md
│
└── venv/                     # Python virtual environment
```

---

## CLI Commands Reference

### Full Pipeline

```bash
# Crawl both sites and match
python run_pipeline.py \
    --crawl \
    --site-a https://www.nykaa.com \
    --site-b https://www.purplle.com \
    --categories "lipstick,foundation,serum" \
    --output output/full_run/
```

### Match Only (Pre-crawled Data)

```bash
python run_pipeline.py \
    --match-only \
    --site-a-data data/nykaa/products.csv \
    --site-b-data data/purplle/products.csv \
    --output output/matches.csv
```

### Advanced Options

```bash
python url_mapper.py \
    --a data/site_a.csv \
    --b data/site_b.csv \
    --out output/ \
    --top_k 100 \                    # More candidates for accuracy
    --model sentence-transformers/paraphrase-multilingual-mpnet-base-v2
```

---

## Input/Output Formats

### Input CSV (Products)

```csv
url,title,brand,category,price
https://nykaa.com/product/123,Maybelline Fit Me Foundation 128,Maybelline,Foundation,599
```

### Output CSV (Matches)

```csv
source_url,source_title,best_match_url,best_match_title,score,confidence_tier,explanation,needs_review
https://nykaa.com/...,Maybelline...,https://purplle.com/...,Maybelline...,0.92,high_confidence,"",false
```

---

## Deployment Instructions

### Railway CLI Deployment

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login with API key
railway login --token 3475fb29-620f-4c97-a9f7-6a72376e06ac

# Initialize project
railway init

# Link to project
railway link

# Deploy
railway up

# Set environment variables
railway variables set SUPABASE_URL=https://qyjzqzqqjimittltttph.supabase.co
railway variables set SUPABASE_KEY=<your-service-role-key>
```

### Supabase Migrations

Use the Supabase MCP tools (not CLI):

```
mcp__supabase__apply_migration
mcp__supabase__execute_sql
mcp__supabase__list_tables
```

**ALWAYS** specify `schema=url_to_url` when running migrations.

---

## Development Workflow

1. **Local Development**
   ```bash
   source venv/bin/activate
   python run_pipeline.py --match-only ...
   ```

2. **Testing**
   ```bash
   python test_matcher.py
   ./quick_test.sh
   ```

3. **Deploy**
   ```bash
   git add .
   git commit -m "feat: description"
   railway up
   ```

4. **Database Changes**
   - Use Supabase MCP for migrations
   - Always target `url_to_url` schema

---

## API Endpoints (Future)

```
POST   /api/jobs              Create new crawl job
GET    /api/jobs              List all jobs
GET    /api/jobs/{id}         Get job details
POST   /api/jobs/{id}/start   Start crawling
DELETE /api/jobs/{id}         Cancel/delete job
GET    /api/jobs/{id}/matches Get match results
PUT    /api/matches/{id}      Update match (approve/reject)
GET    /api/health            Health check
```

---

## Environment Variables

### Local Development (.env)

```bash
# Supabase
SUPABASE_URL=https://qyjzqzqqjimittltttph.supabase.co
SUPABASE_KEY=<your-anon-key>
SUPABASE_SERVICE_KEY=<your-service-role-key>

# Railway (for deployments)
RAILWAY_TOKEN=3475fb29-620f-4c97-a9f7-6a72376e06ac

# ML Model
MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
EMBEDDING_DIMENSIONS=384
```

### Production (Railway)

Set via `railway variables set KEY=value`

---

## Troubleshooting

### Common Issues

**1. Crawl hangs or times out**
```bash
# Increase timeout in crawler config
timeout: 60000  # 60 seconds
```

**2. Low match quality**
```bash
# Increase candidates for better accuracy
python url_mapper.py --top_k 100
```

**3. Memory issues with large datasets**
```bash
# Process in batches
python run_pipeline.py --batch-size 100
```

**4. Supabase connection issues**
- Check if using `url_to_url` schema (not `public`)
- Verify service role key has correct permissions

---

## Performance Benchmarks

| Dataset Size | Time | Memory |
|--------------|------|--------|
| 50 x 600 | ~20s | ~500MB |
| 100 x 1000 | ~45s | ~800MB |
| 500 x 5000 | ~3m | ~1.5GB |
| 1000 x 10000 | ~8m | ~2.5GB |

---

## Future Roadmap

### Phase 3: Full App
- [ ] Next.js frontend
- [ ] FastAPI backend
- [ ] Supabase Auth integration
- [ ] Cloud Playwright crawler on Railway

### Phase 4: Enhancements
- [ ] Multi-language support
- [ ] Image similarity (CLIP)
- [ ] Real-time WebSocket updates
- [ ] Bulk import/export

---

## Dependencies

```txt
# requirements.txt
sentence-transformers>=2.2.0
torch>=2.0.0
transformers>=4.30.0
numpy>=1.24.0
scikit-learn>=1.3.0
pandas>=2.0.0
tqdm>=4.65.0
playwright>=1.40.0
```

---

## Archived Documentation

Previous documentation files are preserved in `docs/archive/`:
- `README.old.md` - Original README
- `PROJECT_SUMMARY.old.md` - Technical summary
- `USAGE_GUIDE.old.md` - Usage guide
- `INSTALL.old.md` - Installation guide

**These files are READ-ONLY. All updates go to this CLAUDE.md file.**

---

## Author & Version

| Field | Value |
|-------|-------|
| Author | Aditya Aman |
| Created | 2026-01-07 |
| Last Updated | 2026-01-08 |
| Version | 2.0.0 |
| Python | 3.11+ |
| Model | sentence-transformers/all-MiniLM-L6-v2 |

---

## Quick Reference Card

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         QUICK REFERENCE                                 │
├─────────────────────────────────────────────────────────────────────────┤
│ Railway API Key:   3475fb29-620f-4c97-a9f7-6a72376e06ac                │
│ Supabase Project:  qyjzqzqqjimittltttph                                │
│ Supabase Schema:   url_to_url (NOT public!)                            │
├─────────────────────────────────────────────────────────────────────────┤
│ Match Command:     python run_pipeline.py --match-only ...             │
│ Crawl Command:     python run_pipeline.py --crawl ...                  │
│ Test Command:      python test_matcher.py                               │
│ Deploy Command:    railway up                                           │
└─────────────────────────────────────────────────────────────────────────┘
```
