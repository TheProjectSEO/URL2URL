# Semantic URL-to-URL Product Matching Engine

A production-ready semantic matching engine that maps products between e-commerce sites using multi-signal scoring with sentence transformers.

## Features

- **Multi-Signal Scoring**: Combines semantic similarity (60%), token overlap (25%), and attribute matching (15%)
- **Confidence Bucketing**: 6-level confidence system from exact matches to manual review
- **Grounded Explanations**: Detailed "why not 100%" reasons for each match
- **Exact Match Detection**: Automatic 100% confidence for brand+product code matches
- **Production Quality**: Progress bars, comprehensive logging, error handling
- **Efficient Processing**: Vectorized operations with numpy/sklearn

## Installation

```bash
# Create virtual environment (recommended)
python3.11 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

```bash
python url_mapper.py --a data/nykaa.csv --b data/purplle.csv --out output/
```

## Usage

### Basic Command

```bash
python url_mapper.py \
  --a data/nykaa.csv \
  --b data/purplle.csv \
  --out output/ \
  --top_k 25
```

### CLI Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--a` | Yes | - | Path to Site A CSV (smaller dataset) |
| `--b` | Yes | - | Path to Site B CSV (larger dataset) |
| `--out` | No | `output/` | Output directory for results |
| `--top_k` | No | `25` | Number of top candidates to evaluate |
| `--model` | No | `all-MiniLM-L6-v2` | Sentence transformer model |

### Input CSV Format

Both CSVs must contain these columns:

```csv
url,title,brand,category
https://example.com/product1,"Maybelline Fit Me Matte + Poreless Foundation 128 Warm Nude",Maybelline,Foundation
https://example.com/product2,"Lakme 9to5 Primer + Matte Lipstick Ruby Rush M11",Lakme,Lipstick
```

**Required Columns:**
- `url`: Product page URL
- `title`: Product title (used for matching)
- `brand`: Brand name
- `category`: Product category

## Output Format

Results are saved to `output/matches.csv` with the following structure:

| Column | Description |
|--------|-------------|
| `source_url` | Original product URL from Site A |
| `source_title` | Original product title |
| `best_match_url` | Best matching URL from Site B |
| `best_match_title` | Best matching product title |
| `confidence` | Confidence score (0-100) |
| `confidence_label` | Human-readable confidence bucket |
| `raw_score` | Underlying multi-signal score (0-1) |
| `why_not_100` | Explanation if confidence < 100% |
| `needs_review` | Boolean flag for manual review |
| `top_5_candidates` | Alternative match candidates |

## Confidence Buckets

| Score Range | Confidence | Label | Review Required |
|-------------|------------|-------|-----------------|
| 0.95+ | 100% | `exact_match` | No |
| 0.90-0.94 | 90% | `high_confidence` | No |
| 0.80-0.89 | 80% | `good_match` | No |
| 0.70-0.79 | 70% | `likely_match` | Yes |
| 0.50-0.69 | 50% | `manual_review` | Yes |
| <0.50 | 0% | `no_confident_match` | Yes |

## Matching Algorithm

### Multi-Signal Scoring

```
Final Score = (0.60 × Semantic Similarity) + (0.25 × Token Overlap) + (0.15 × Attribute Match)
```

1. **Semantic Similarity (60%)**
   - Uses `sentence-transformers/all-MiniLM-L6-v2`
   - Cosine similarity of normalized embeddings
   - Captures semantic meaning beyond keywords

2. **Token Overlap (25%)**
   - Jaccard similarity of tokenized titles
   - Removes common stop words
   - Rewards lexical similarity

3. **Attribute Matching (15%)**
   - Brand matching (exact/partial)
   - Product code extraction and comparison
   - Shade/color/finish detection
   - Category validation

### Exact Match Override

Automatic 100% confidence if:
- Same brand + same product code, OR
- Same brand + identical normalized titles

### Explanation Generation

For matches below 100%, the system provides grounded reasons:

```
"Brand mismatch: Lakme vs Maybelline; Shade differs: 128 vs 130; Semantic similarity below threshold: 0.87"
```

## Example Output

```
source_url: https://nykaa.com/lakme-lipstick-red
source_title: Lakme 9to5 Primer + Matte Lipstick Ruby Rush M11
best_match_url: https://purplle.com/lakme-9to5-ruby-rush-m11
best_match_title: Lakme 9to5 Primer+Matte Lipstick M11 Ruby Rush
confidence: 100
confidence_label: exact_match
raw_score: 0.9845
why_not_100:
needs_review: False
top_5_candidates: Lakme 9to5 Primer+Matte Lipstick M11 Ruby Rush (score: 0.985, semantic: 0.972) | ...
```

## Statistics Report

After processing, the engine generates comprehensive statistics:

```
================================================================================
MATCHING STATISTICS
================================================================================
Total products matched: 50
Products needing review: 8 (16.0%)

Confidence Distribution:
  exact_match         :   12 (24.0%) | Avg Score: 0.975
  high_confidence     :   18 (36.0%) | Avg Score: 0.912
  good_match          :   12 (24.0%) | Avg Score: 0.845
  likely_match        :    5 (10.0%) | Avg Score: 0.742
  manual_review       :    3 ( 6.0%) | Avg Score: 0.598
  no_confident_match  :    0 ( 0.0%) | Avg Score: 0.000

Score Statistics:
  Mean:   0.867
  Median: 0.892
  Min:    0.543
  Max:    0.985
  Std:    0.112
================================================================================
```

## Logging

Two log outputs are generated:

1. **Console**: Real-time progress with tqdm bars
2. **File**: Detailed log saved to `output/matching_log.txt`

Example console output:

```
15:23:45 | INFO | Loading Site A products from data/nykaa.csv
15:23:45 | INFO | Loading model: sentence-transformers/all-MiniLM-L6-v2
Batches: 100%|████████| 2/2 [00:01<00:00, 1.43it/s]
15:23:47 | INFO | Loaded 50 products from Site A
15:23:47 | INFO | Loading Site B products from data/purplle.csv
Batches: 100%|████████| 20/20 [00:12<00:00, 1.58it/s]
15:23:59 | INFO | Loaded 623 products from Site B
15:23:59 | INFO | Computing similarity matrix...
Matching products: 100%|████████| 50/50 [00:03<00:00, 14.2it/s]
```

## Performance

- **50 source products × 600 target products**
  - Embedding generation: ~15 seconds
  - Similarity computation: ~2 seconds
  - Multi-signal scoring: ~3 seconds
  - **Total: ~20 seconds**

- **Memory Usage**: ~500MB for 1000 products
- **GPU Support**: Automatic if CUDA available

## Advanced Usage

### Custom Model

Use a different sentence transformer model:

```bash
python url_mapper.py \
  --a data/nykaa.csv \
  --b data/purplle.csv \
  --model sentence-transformers/paraphrase-multilingual-mpnet-base-v2
```

### Increasing Candidate Pool

For more thorough matching (slower):

```bash
python url_mapper.py \
  --a data/nykaa.csv \
  --b data/purplle.csv \
  --top_k 100
```

## Architecture

### Class Structure

```
ProductMatcher
├── TextProcessor (static utility)
│   ├── normalize_text()
│   ├── tokenize()
│   ├── extract_product_code()
│   └── extract_attributes()
├── load_products()
├── compute_multi_signal_score()
├── check_exact_match()
├── get_confidence_bucket()
└── find_matches()
```

### Data Flow

```
CSV Input → ProductRecord → Embeddings → Similarity Matrix
                                              ↓
                                    Multi-Signal Scoring
                                              ↓
                                    Confidence Bucketing
                                              ↓
                                    Explanation Generation
                                              ↓
                                      MatchResult → CSV Output
```

## Troubleshooting

### Import Errors

```bash
# Make sure you're in the virtual environment
source venv/bin/activate

# Reinstall dependencies
pip install --upgrade -r requirements.txt
```

### CUDA Out of Memory

If running on GPU with limited memory:

```python
# The model automatically uses CPU if CUDA unavailable
# To force CPU usage:
import os
os.environ['CUDA_VISIBLE_DEVICES'] = ''
```

### Missing Columns Error

Ensure your CSVs have exactly these columns:
- `url`
- `title`
- `brand`
- `category`

Case-sensitive column names required.

## Extending the Engine

### Adding Custom Attributes

Edit `TextProcessor.extract_attributes()`:

```python
# Add volume extraction
VOLUME_PATTERN = re.compile(r'(\d+)\s?(ml|l|g|kg)')
volume_match = VOLUME_PATTERN.search(title)
if volume_match:
    attributes['volume'] = volume_match.group(1) + volume_match.group(2)
```

### Adjusting Signal Weights

Modify `compute_multi_signal_score()`:

```python
# Example: Prioritize brand matching more
semantic_score = semantic_sim * 0.50  # Reduced from 0.60
token_score = token_overlap * 0.20     # Reduced from 0.25
attr_score = attr_match * 0.30         # Increased from 0.15
```

### Custom Confidence Buckets

Edit `get_confidence_bucket()`:

```python
# Add "perfect_match" tier
if score >= 0.98:
    return (100, "perfect_match")
```

## Testing

Run a quick test with sample data:

```bash
# Create sample CSVs
mkdir -p data
python -c "
import pandas as pd
pd.DataFrame({
    'url': ['https://example.com/p1'],
    'title': ['Test Product'],
    'brand': ['TestBrand'],
    'category': ['Category']
}).to_csv('data/test_a.csv', index=False)
pd.DataFrame({
    'url': ['https://example.com/p2'],
    'title': ['Test Product'],
    'brand': ['TestBrand'],
    'category': ['Category']
}).to_csv('data/test_b.csv', index=False)
"

# Run matcher
python url_mapper.py --a data/test_a.csv --b data/test_b.csv --out test_output/
```

## License

MIT License - See LICENSE file for details.

## Author

Aditya Aman
Created: 2026-01-07

## Version

1.0.0
