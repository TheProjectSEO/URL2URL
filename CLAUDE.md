# URL-to-URL Product Matching Platform

> **Single Source of Truth** - All project documentation lives here. Do NOT create additional MD files.

---

## What This Platform IS

A **full-stack semantic product matching platform** that:
- Matches products between two e-commerce websites using ML embeddings
- Provides a web UI for creating jobs, uploading CSVs, and reviewing matches
- Uses pgvector for scalable O(1) similarity search (handles 1M+ products)
- Returns multi-candidate matches with confidence scores
- Supports batch processing with background job execution

**Primary Use Case**: Given your product catalog (Site A) and a competitor's catalog (Site B), find which of your products exist on the competitor's site with confidence scores.

---

## AI/ML Components Explained

### What "AI" Means in This Platform

This platform uses **ML embeddings** (Machine Learning), **NOT generative AI** (LLMs like ChatGPT/Claude).

| Component | What It Is | What It Does |
|-----------|------------|--------------|
| **sentence-transformers** | Pre-trained neural network | Converts text → 384-dimensional vectors |
| **pgvector** | PostgreSQL extension | Finds similar vectors using cosine distance |
| **Multi-signal scoring** | Rule-based algorithm | Combines similarity scores with weights |

### What AI DOES in This Platform

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         AI/ML PIPELINE                                       │
└─────────────────────────────────────────────────────────────────────────────┘

   Product Title                    384-dim Vector                Similar Products
        │                                │                              │
        ▼                                ▼                              ▼
┌───────────────┐    Embedding    ┌──────────────┐   Similarity   ┌─────────────┐
│ "Maybelline   │ ──────────────▶ │ [0.02, -0.15,│ ────────────▶  │ Top 100     │
│  Fit Me       │   Generation    │  0.08, ...]  │    Search      │ Candidates  │
│  Foundation"  │                 │ (384 floats) │   (pgvector)   │             │
└───────────────┘                 └──────────────┘                └─────────────┘
        │                                                               │
        │                    ML MODEL                                   │
        │         sentence-transformers/all-MiniLM-L6-v2               │
        │                                                               │
        │   ┌─────────────────────────────────────────────────────┐    │
        └──▶│  • Trained on 1B+ sentence pairs                    │    │
            │  • Understands semantic meaning                      │    │
            │  • "Foundation" ≈ "Liquid Foundation" ≈ "Base Makeup"│    │
            │  • Language: English (primary), multilingual support │    │
            │  • Size: 22M parameters (small, fast)                │    │
            └─────────────────────────────────────────────────────┘    │
                                                                        │
                           RULE-BASED SCORING                           │
            ┌─────────────────────────────────────────────────────┐    │
            │  Final Score = 0.60×Semantic + 0.25×Token + 0.15×Attr│◀───┘
            │  (No AI here - just weighted math)                   │
            └─────────────────────────────────────────────────────┘

New signals and toggles (MVP+):
- Enriched embeddings: title + brand + category (config: embed_enriched_text)
- Token normalization v2: stricter token cleanup (config: token_norm_v2)
- Brand ontology: alias→canonical matching (config: use_brand_ontology)
- Category ontology: synonyms/related (config: use_category_ontology)
- Variant extractor: size/shade/model/pack parsing (config: use_variant_extractor)
- OCR image text: optional visual text similarity (config: use_ocr_text, ocr_max_comparisons)
```

### What AI Does NOT Do

| Capability | Status | Explanation |
|------------|--------|-------------|
| ❌ **Generate product descriptions** | Not implemented | No text generation |
| ❌ **Answer questions** | Not implemented | No conversational AI |
| ❌ **Explain matches in natural language** | Not implemented | Explanations are template-based |
| ❌ **Learn from user feedback** | Not implemented | Model is pre-trained, not fine-tuned |
| ❌ **Handle images** | Not implemented | Text-only matching |
| ❌ **Make decisions** | Not implemented | Human reviews required for <80% matches |

### The ML Model: sentence-transformers/all-MiniLM-L6-v2

| Property | Value |
|----------|-------|
| **Type** | Bi-encoder (BERT-based) |
| **Parameters** | 22 million (small/fast) |
| **Training Data** | 1B+ sentence pairs from NLI, paraphrase, Q&A datasets |
| **Output** | 384-dimensional normalized vector |
| **Speed** | ~1000 embeddings/second on CPU |
| **Languages** | English (primary), limited multilingual |
| **License** | Apache 2.0 (free for commercial use) |

**Why this model?**
- Fast enough for real-time embedding generation
- Good quality for product title matching
- Small memory footprint (~90MB)
- No API costs (runs locally)

### No External AI APIs

This platform does **NOT** call:
- ❌ OpenAI API
- ❌ Anthropic Claude API
- ❌ Google Gemini API
- ❌ Any LLM service

All ML inference runs locally using the sentence-transformers library.

OCR requirements (optional):
- pytesseract + Tesseract binary (installed in Docker)
- Provide `image_url` in CSV or metadata to enable OCR comparisons

### Future: LLM Validation (Planned, Not Implemented)

For borderline matches (70-90% confidence), we plan to add optional LLM validation:

```python
# PLANNED - NOT YET IMPLEMENTED
# Would use Claude API to verify uncertain matches

prompt = f"""
Are these the same product?
Product A: {source_title} (Brand: {source_brand})
Product B: {target_title} (Brand: {target_brand})

Current confidence: {score}%
Respond: YES, NO, or UNCERTAIN
"""
```

| When | LLM Validation |
|------|----------------|
| Score ≥ 95% | Skip (clearly same product) |
| Score 70-94% | **Use LLM** (borderline, needs verification) |
| Score < 70% | Skip (clearly different or no match) |

**Why not implemented yet?**
- Adds latency (~1-2 seconds per match)
- Adds cost (~$0.01 per 100 matches)
- Current accuracy (90%+) is acceptable for most use cases

---

## What This Platform IS NOT

- ❌ **Not a general-purpose web scraper** - Crawlers exist but are site-specific (Nykaa, Purplle). Primary input is CSV upload.
- ❌ **Not real-time matching** - Jobs run asynchronously in background (see "Why Not Real-Time?" below)
- ❌ **Not a price comparison tool** - Focuses on product identity matching, not pricing analytics
- ❌ **Not limited to beauty products** - Works with any product catalog (Nykaa/Purplle are examples)

### Why Not Real-Time?

**Problem**: Matching 1,000 products against 10,000 requires:
- Generating 1,000 embeddings (~30 seconds)
- Running 1,000 pgvector searches (~60 seconds)
- Computing multi-signal scores for 100,000 candidate pairs (~10 minutes)

**Solution**: Background job processing with progress tracking.

| Approach | User Experience | Technical Reality |
|----------|-----------------|-------------------|
| ❌ Synchronous API | Request times out after 30s | Browser shows error |
| ❌ WebSocket streaming | Complex, still takes 15 min | User must keep tab open |
| ✅ Background jobs | Submit and check back later | Reliable, scalable |

**User Workflow**:
1. Submit job → Get job ID immediately
2. Poll `/api/jobs/{id}/progress` or check UI
3. Results available when status = "completed"

---

## Quick Start

### Option 1: Web Application (Recommended)

```bash
# Terminal 1: Start API backend
cd apps/api
source ../../venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2: Start Next.js frontend
cd apps/web
npm run dev

# Open browser
open http://localhost:3000

Migrations

- Schema/RPCs are snapshotted under `apps/api/migrations`
- To apply via psql, set `DATABASE_URL` and run:
  ```bash
  ./apps/api/migrations/apply.sh
  ```
```

### Option 2: CLI (Legacy)

```bash
source venv/bin/activate
python run_pipeline.py --match-only \
    --site-a-data data/nykaa.csv \
    --site-b-data data/purplle.csv \
    --output output/matches.csv
```

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                     URL-TO-URL PRODUCT MATCHING PLATFORM                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐     ┌─────────────────────┐     ┌─────────────────────┐
│   Next.js Frontend  │────▶│   FastAPI Backend   │────▶│      Supabase       │
│   localhost:3000    │     │   localhost:8000    │     │  (PostgreSQL + pgvector)
│                     │     │                     │     │                     │
│  • Job Dashboard    │     │  • /api/jobs        │     │  • crawl_jobs       │
│  • CSV Upload       │     │  • /api/upload      │     │  • products         │
│  • Match Review     │     │  • /api/matches     │     │  • matches          │
│  • Progress Tracking│     │  • Background Tasks │     │  • embeddings       │
└─────────────────────┘     └─────────────────────┘     └─────────────────────┘
                                      │
                            ┌─────────▼─────────┐
                            │  ML Matcher Engine │
                            │                    │
                            │  • sentence-transformers
                            │  • pgvector search │
                            │  • Multi-signal scoring
                            └────────────────────┘
```

---

## Product Crawlers (Optional)

### What the Crawlers ARE

Site-specific Playwright-based scrapers that extract product data from e-commerce websites.

| Crawler | File | Supported Site |
|---------|------|----------------|
| Nykaa Crawler | `scrape_nykaa.py` | nykaa.com |
| Purplle Crawler | `scrape_purplle.py` | purplle.com |

### What They CAN Do

| Capability | Details |
|------------|---------|
| **JavaScript Rendering** | Uses Playwright (headless Chromium) - handles dynamic content |
| **Category Navigation** | Crawls by category (lipstick, foundation, serum, etc.) |
| **Pagination** | Handles infinite scroll and "Load More" buttons |
| **Rate Limiting** | Built-in delays to avoid IP blocks (2-5 sec between requests) |
| **Checkpoint Resume** | Saves progress, can resume after crash |
| **Data Extraction** | Title, brand, price, URL, category, product ID |

### What They CANNOT Do

| Limitation | Reason |
|------------|--------|
| ❌ **Generic scraping** | Selectors are hardcoded for Nykaa/Purplle DOM structure |
| ❌ **Login/auth pages** | No session handling or cookie management |
| ❌ **CAPTCHA bypass** | Will fail if site shows CAPTCHA |
| ❌ **Real-time monitoring** | One-time crawl, not continuous |
| ❌ **Image download** | Extracts image URLs only, doesn't download files |
| ❌ **Anti-bot evasion** | Basic stealth only - may get blocked at scale |

### Adding a New Site

To add support for a new e-commerce site:

1. **Analyze DOM structure** - Find product title, price, brand selectors
2. **Copy template** - Use `scrape_nykaa.py` as starting point
3. **Update selectors** - Modify CSS/XPath selectors for new site
4. **Handle pagination** - Implement site-specific page navigation
5. **Test thoroughly** - Sites change layouts frequently

```python
# Example: Key selectors to update
PRODUCT_TITLE_SELECTOR = 'h1.product-name'      # Site-specific
PRODUCT_PRICE_SELECTOR = 'span.price-value'     # Site-specific
PRODUCT_BRAND_SELECTOR = 'a.brand-link'         # Site-specific
```

### Recommended Approach

**For production use**: Upload product data via CSV (exported from your database or catalog system) rather than crawling. Crawlers are useful for:
- Initial data collection
- Competitor analysis (one-time)
- Testing the matching engine

---

## How the Matching Works

### Step 1: Embedding Generation

Each product title is converted to a 384-dimensional normalized vector.

| Parameter | Value |
|-----------|-------|
| **Model** | `sentence-transformers/all-MiniLM-L6-v2` |
| **Embedding Dimensions** | 384 |
| **Normalization** | L2 normalized (unit vectors) |
| **Batch Size** | 32 products per batch |
| **Input** | Product title (primary), brand, category (optional) |

```python
# What gets embedded
text_to_embed = f"{product.title}"  # Primary signal
# Future: f"{product.title} {product.brand} {product.category}"

# Output
"Maybelline Fit Me Foundation 128" → [0.023, -0.156, 0.089, ..., 0.045]  # 384 floats
```

### Step 2: pgvector Similarity Search (Pre-filtering)

For each Site A product, pgvector finds the **top 100 most similar** Site B products using cosine distance.

| Parameter | Value | Why |
|-----------|-------|-----|
| **Distance Metric** | Cosine (`<=>` operator) | Best for text embeddings |
| **Index Type** | IVFFlat | Balance of speed and accuracy |
| **Pre-filter Limit** | 100 candidates | Reduces O(n²) to O(n×100) |

```sql
-- Actual query executed per product
SELECT id, title, url, brand, category,
       1 - (embedding <=> $source_embedding) as similarity
FROM url_to_url.products
WHERE job_id = $job_id AND site = 'site_b' AND embedding IS NOT NULL
ORDER BY embedding <=> $source_embedding
LIMIT 100;
```

### Step 3: Multi-Signal Scoring

Each of the 100 candidates is scored using **three weighted signals**:

```
Final Score = (0.60 × Semantic) + (0.25 × Token) + (0.15 × Attributes)
```

#### Signal 1: Semantic Similarity (60% weight)

| Parameter | Details |
|-----------|---------|
| **What it measures** | Meaning similarity via embeddings |
| **Calculation** | `1 - cosine_distance(embedding_a, embedding_b)` |
| **Range** | 0.0 (opposite) to 1.0 (identical) |
| **Strengths** | Catches synonyms, paraphrases, reordered words |
| **Weaknesses** | May miss brand mismatches |

```python
# Example
"Maybelline Fit Me Foundation" vs "Maybelline FitMe Liquid Foundation"
# Semantic: 0.94 (high - same meaning)
```

#### Signal 2: Token Overlap (25% weight)

| Parameter | Details |
|-----------|---------|
| **What it measures** | Exact word matches |
| **Calculation** | Jaccard similarity: `|A ∩ B| / |A ∪ B|` |
| **Preprocessing** | Lowercase, remove punctuation, split on whitespace |
| **Range** | 0.0 (no common words) to 1.0 (identical words) |
| **Strengths** | Catches exact product names, shade numbers |
| **Weaknesses** | Misses synonyms ("lipstick" vs "lip color") |

```python
# Example
"Maybelline Fit Me Foundation 128" vs "Maybelline FitMe Foundation 125"
# Tokens A: {maybelline, fit, me, foundation, 128}
# Tokens B: {maybelline, fitme, foundation, 125}
# Intersection: {maybelline, foundation} = 2
# Union: {maybelline, fit, me, foundation, 128, fitme, 125} = 7
# Jaccard: 2/7 = 0.286
```

#### Signal 3: Attribute Matching (15% weight)

| Attribute | Match Score | Partial Score |
|-----------|-------------|---------------|
| **Brand** | 1.0 if exact match | 0.5 if substring match |
| **Category** | 1.0 if exact match | 0.5 if related category |
| **Price** | Not currently used | Future: ±20% tolerance |

```python
# Example
Source: brand="Maybelline", category="Foundation"
Target: brand="Maybelline New York", category="Face Foundation"
# Brand: 0.5 (substring match)
# Category: 0.5 (related)
# Attribute Score: (0.5 + 0.5) / 2 = 0.5
```

#### Combined Scoring Example

```python
# Product A: "Maybelline Fit Me Foundation 128" (Nykaa)
# Product B: "Maybelline New York Fit Me Foundation 128" (Purplle)

Semantic Score:    0.96  × 0.60 = 0.576
Token Score:       0.71  × 0.25 = 0.178
Attribute Score:   0.75  × 0.15 = 0.113
─────────────────────────────────────────
Final Score:                     0.867 (86.7%)
Confidence Tier:                 good_match
```

### Step 4: Confidence Tier Assignment

Based on the final score, each match is assigned a **confidence tier**:

| Score Range | Tier | Human Interpretation | Needs Review? |
|-------------|------|----------------------|---------------|
| **95-100%** | `exact_match` | Identical product, different URL | No |
| **90-94%** | `high_confidence` | Same product, minor title variations | No |
| **80-89%** | `good_match` | Very likely same product | Optional |
| **70-79%** | `likely_match` | Probably same, some differences | Yes |
| **50-69%** | `manual_review` | Uncertain, could be similar products | Yes |
| **<50%** | `no_match` | Not the same product | N/A |

#### Explanation Generation

For matches below 95%, the system generates **grounded explanations**:

```python
# Examples of auto-generated explanations:
"Brand mismatch: Lakme vs Maybelline"
"Shade differs: 128 vs 130"
"Low semantic similarity: 0.72"
"Category mismatch: Lipstick vs Lip Gloss"
```

### Step 5: Top 5 Candidates Storage

Each source product stores its **top 5 match candidates** (not just the best match):

```json
{
  "source_product_id": "abc-123",
  "matched_product_id": "xyz-789",  // Best match
  "score": 0.867,
  "confidence_tier": "good_match",
  "top_5_candidates": [
    {"product_id": "xyz-789", "title": "Maybelline...", "score": 0.867, "url": "..."},
    {"product_id": "xyz-456", "title": "Maybelline...", "score": 0.823, "url": "..."},
    {"product_id": "xyz-123", "title": "L'Oreal...", "score": 0.756, "url": "..."},
    {"product_id": "xyz-999", "title": "Revlon...", "score": 0.712, "url": "..."},
    {"product_id": "xyz-888", "title": "Lakme...", "score": 0.698, "url": "..."}
  ],
  "is_no_match": false
}
```

**Why top 5?**
- Best match may be wrong (human can select #2 or #3)
- Supports "show similar products" feature
- Allows bulk review workflows

### No-Match Handling

Products with best score **below 50%** are marked as `is_no_match: true`:

```json
{
  "source_product_id": "abc-999",
  "matched_product_id": null,
  "score": 0.0,
  "confidence_tier": "no_match",
  "top_5_candidates": [],
  "is_no_match": true,
  "no_match_reason": "Best candidate scored 42% - below 50% threshold"
}
```

---

## Features

### ✅ Working Features

| Feature | Status | Description |
|---------|--------|-------------|
| **Job Management** | ✅ | Create, list, delete matching jobs |
| **CSV Upload** | ✅ | Upload product catalogs for both sites |
| **Background Matching** | ✅ | Jobs run async, won't timeout |
| **pgvector Search** | ✅ | O(1) similarity search at scale |
| **Multi-Candidate Matches** | ✅ | Top 5 candidates per product |
| **No-Match Detection** | ✅ | Products below 50% marked as no match |
| **Match Review UI** | ✅ | Approve/reject matches in frontend |
| **Progress Tracking** | ✅ | Real-time polling with counters + OCR comps |
| **OCR Text Signal** | ✅ | Optional visual text signal (Tesseract required) |
| **Ontologies** | ✅ | Brand aliases + category synonyms |

### 🚧 Planned Features

| Feature | Priority | Description |
|---------|----------|-------------|
| Batch Processing | High | Process remaining products in batches |
| Export to CSV | Medium | Download match results |
| AI Validation | Low | LLM verification for borderline matches |
| Image Matching | Low | Visual similarity using CLIP |

---

## API Endpoints

### Jobs

```
POST   /api/jobs                    Create new job
GET    /api/jobs                    List all jobs
GET    /api/jobs/{id}               Get job with stats
DELETE /api/jobs/{id}               Delete job
POST   /api/jobs/{id}/run-background  Start matching (uses DB products)
GET    /api/jobs/{id}/progress      Get real-time progress
GET    /api/jobs/{id}/metrics       Get persisted matcher metrics
GET    /api/jobs/{id}/diagnostics   Download component score CSV (sample)
```

### Upload

```
POST   /api/upload/products/{job_id}/{site}   Upload CSV (site = site_a or site_b)
```

### Matches

```
GET    /api/matches?job_id={id}     List matches with filters
PUT    /api/matches/{id}            Update match status
PUT    /api/matches/bulk            Bulk approve/reject
```

### Health

```
GET    /api/health                  API health check
GET    /                            API info
```

---

## Database Schema

**Schema**: `url_to_url` (NEVER use `public`)

### Tables

```sql
-- Jobs table
url_to_url.crawl_jobs (
    id UUID PRIMARY KEY,
    name TEXT,
    site_a_url TEXT,
    site_b_url TEXT,
    status TEXT,  -- pending, running, completed, failed
    config JSONB,
    created_at, started_at, completed_at
)

-- Products table (with embeddings)
url_to_url.products (
    id UUID PRIMARY KEY,
    job_id UUID REFERENCES crawl_jobs,
    site TEXT,  -- site_a or site_b
    url TEXT,
    title TEXT,
    brand TEXT,
    category TEXT,
    price DECIMAL,
    embedding vector(384),
    metadata JSONB
)

-- Matches table (with top 5 candidates)
url_to_url.matches (
    id UUID PRIMARY KEY,
    job_id UUID,
    source_product_id UUID,
    matched_product_id UUID,
    score DECIMAL,
    confidence_tier TEXT,
    explanation TEXT,
    top_5_candidates JSONB,
    is_no_match BOOLEAN,
    no_match_reason TEXT,
    status TEXT  -- pending, approved, rejected
)
```

### Key RPC Functions

```sql
url_to_url.search_similar_products(embedding, job_id, site, limit)
url_to_url.store_match_with_candidates(...)
url_to_url.url_get_job(job_id)
url_to_url.url_get_job_stats(job_id)
url_to_url.url_store_embedding(product_id, embedding)
```

---

## File Structure

```
urltourl/
├── CLAUDE.md                    # THIS FILE - Single source of truth
├── requirements.txt             # Python dependencies
│
├── apps/
│   ├── api/                     # FastAPI Backend
│   │   ├── main.py              # App entry point, CORS, lifespan
│   │   ├── routers/
│   │   │   ├── jobs.py          # Job CRUD + run endpoints
│   │   │   ├── matches.py       # Match retrieval + bulk update
│   │   │   ├── upload.py        # CSV upload endpoint
│   │   │   └── health.py        # Health checks
│   │   ├── services/
│   │   │   ├── supabase.py      # Database operations
│   │   │   ├── matcher.py       # ML matching engine
│   │   │   ├── job_runner.py    # Background job orchestration
│   │   │   └── progress.py      # Progress tracking
│   │   ├── models/
│   │   │   └── schemas.py       # Pydantic models
│   │   └── requirements.txt     # API-specific deps
│   │
│   └── web/                     # Next.js Frontend
│       ├── src/
│       │   ├── app/
│       │   │   ├── page.tsx           # Dashboard
│       │   │   ├── jobs/
│       │   │   │   ├── page.tsx       # Job list
│       │   │   │   ├── new/page.tsx   # Create job
│       │   │   │   └── [id]/page.tsx  # Job details + matches
│       │   ├── components/
│       │   │   ├── MatchTable.tsx
│       │   │   ├── JobProgress.tsx
│       │   │   └── CSVUpload.tsx
│       │   └── lib/
│       │       └── api.ts             # API client
│       └── package.json
│
├── data/                        # CSV data files
│   ├── nykaa_products.csv
│   └── purplle_products.csv
│
└── (legacy CLI files)
    ├── run_pipeline.py
    ├── url_mapper.py
    └── scrape_*.py
```

---

## Infrastructure

### Credentials

```yaml
# Railway (Backend Hosting)
RAILWAY_API_KEY: 3475fb29-620f-4c97-a9f7-6a72376e06ac
PRODUCTION_URL: https://product-matcher-production-ef35.up.railway.app

# Supabase (Database)
SUPABASE_PROJECT_ID: qyjzqzqqjimittltttph
SUPABASE_URL: https://qyjzqzqqjimittltttph.supabase.co
SUPABASE_SCHEMA: url_to_url
```

### Environment Variables

```bash
# apps/api/.env
SUPABASE_URL=https://qyjzqzqqjimittltttph.supabase.co
SUPABASE_KEY=<service-role-key>
PYTHON_ENV=development
CORS_ORIGINS=http://localhost:3000

# apps/web/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
```

---

## Performance Benchmarks

### Latest Run (January 2026)

| Metric | Value |
|--------|-------|
| Site A Products | 1,000 |
| Site B Products | 998 |
| Processing Time | 13.5 minutes |
| High Confidence Matches | 52 |
| Medium Confidence | 222 |
| No Match | 726 |
| Match Rate | 27.4% |

### Scaling Expectations

| Scale | Expected Time | Notes |
|-------|---------------|-------|
| 100 × 1,000 | ~2 min | Small catalog |
| 1,000 × 10,000 | ~15 min | Medium catalog |
| 10,000 × 100,000 | ~2 hours | Large catalog |
| 100,000 × 1,000,000 | ~1 day | Enterprise scale |

---

## Usage Workflow

### 1. Create a Job

```bash
curl -X POST http://localhost:8000/api/jobs \
  -H "Content-Type: application/json" \
  -d '{"name": "Nykaa vs Purplle", "site_a_url": "https://nykaa.com", "site_b_url": "https://purplle.com"}'
```

### 2. Upload Products

```bash
# Upload Site A (your products)
curl -X POST "http://localhost:8000/api/upload/products/{job_id}/site_a" \
  -F "file=@data/nykaa_products.csv"

# Upload Site B (competitor)
curl -X POST "http://localhost:8000/api/upload/products/{job_id}/site_b" \
  -F "file=@data/purplle_products.csv"
```

### 3. Run Matching

```bash
curl -X POST "http://localhost:8000/api/jobs/{job_id}/run-background"
```

### 4. Check Progress

```bash
curl "http://localhost:8000/api/jobs/{job_id}/progress"
```

### 5. View Results

Open `http://localhost:3000/jobs/{job_id}` in browser.

---

## CSV Format

### Input CSV (Required Columns)

```csv
url,title
https://nykaa.com/product/123,Maybelline Fit Me Foundation 128
https://nykaa.com/product/456,L'Oreal True Match Foundation
```

### Input CSV (Optional Columns)

```csv
url,title,brand,category,price
https://nykaa.com/...,Maybelline Fit Me...,Maybelline,Foundation,599
```

### Output (Matches Table)

| Column | Description |
|--------|-------------|
| source_product_id | Site A product UUID |
| matched_product_id | Best match from Site B |
| score | 0.0 - 1.0 confidence |
| confidence_tier | exact_match, high_confidence, etc. |
| top_5_candidates | JSONB array of candidates |
| is_no_match | true if score < 50% |

---

## Troubleshooting

### API Returns 0 Products

The API may show 0 products while products exist in DB. Query Supabase directly:

```sql
SELECT site, COUNT(*) FROM url_to_url.products
WHERE job_id = 'your-job-id' GROUP BY site;
```

### Job Stuck in "Running"

Check background task logs or query job status:

```sql
SELECT status, started_at, completed_at
FROM url_to_url.crawl_jobs WHERE id = 'your-job-id';
```

### Progress Tracking Errors

The `job_progress` table may be missing columns. Non-blocking - matching continues.

### CORS Issues

Ensure `CORS_ORIGINS` includes your frontend URL in `apps/api/.env`.

---

## Development Commands

```bash
# Start API (with hot reload)
cd apps/api && uvicorn main:app --reload --port 8000

# Start Frontend
cd apps/web && npm run dev

# Run DB migrations (via Supabase MCP)
mcp__supabase__apply_migration

# Deploy to Railway
cd apps/api && railway up

# Test API health
curl http://localhost:8000/api/health
```

---

## Key Design Decisions

### Why pgvector over FAISS?
- Integrated with Supabase (no separate service)
- Persistent storage (survives restarts)
- SQL-based querying (filter by job_id, site)
- IVFFlat index for O(1) search

### Why Background Tasks over Sync?
- Large jobs (1000+ products) timeout HTTP connections
- Users can close browser and check results later
- Progress can be polled via API

### Why Multi-Signal Scoring?
- Semantic alone misses brand mismatches
- Token overlap catches exact word matches
- Attribute matching validates metadata

### Why Top 5 Candidates?
- Single best match may be wrong
- Allows human review of alternatives
- Supports "show similar products" UI

---

## Quick Reference

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            QUICK REFERENCE                                   │
├─────────────────────────────────────────────────────────────────────────────┤
│ Frontend:        http://localhost:3000                                      │
│ Backend API:     http://localhost:8000                                      │
│ API Docs:        http://localhost:8000/docs                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│ Production API:  https://product-matcher-production-ef35.up.railway.app    │
│ Supabase:        https://supabase.com/dashboard/project/qyjzqzqqjimittltttph│
│ Schema:          url_to_url (NEVER use public!)                             │
├─────────────────────────────────────────────────────────────────────────────┤
│ Start API:       cd apps/api && uvicorn main:app --reload                   │
│ Start Frontend:  cd apps/web && npm run dev                                 │
│ Deploy:          cd apps/api && railway up                                  │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 3.2.0 | 2026-01-13 | Added AI/ML components explanation, clarified what AI does/doesn't do |
| 3.1.0 | 2026-01-13 | Added detailed matching parameters, crawler docs, real-time explanation |
| 3.0.0 | 2026-01-13 | Full web app, pgvector, background jobs |
| 2.0.0 | 2026-01-08 | Supabase integration, API endpoints |
| 1.0.0 | 2026-01-07 | CLI-only, CSV-based matching |

**Author**: Aditya Aman
**Last Updated**: 2026-01-13
