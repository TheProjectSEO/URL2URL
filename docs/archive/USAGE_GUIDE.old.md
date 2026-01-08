# URL-to-URL Matcher - Usage Guide

Complete guide for using the semantic product matching engine.

## Quick Start (5 minutes)

### 1. Setup Environment

```bash
# Navigate to project
cd /Users/adityaaman/Desktop/All\ Development/urltourl

# Run quick test script
./quick_test.sh
```

This will:
- Create virtual environment
- Install dependencies
- Run matcher on sample data (10×25 products)
- Generate results in `output/matches.csv`

### 2. View Results

```bash
# View first 10 matches
head -n 11 output/matches.csv

# Open in spreadsheet
open output/matches.csv

# Check statistics
tail -n 20 output/matching_log.txt
```

---

## Preparing Your Data

### CSV Requirements

Both input CSVs **must** have these exact columns:

| Column | Type | Description | Example |
|--------|------|-------------|---------|
| `url` | string | Product page URL | `https://nykaa.com/product-123` |
| `title` | string | Full product title | `Maybelline Fit Me Foundation 128` |
| `brand` | string | Brand name | `Maybelline` |
| `category` | string | Product category | `Foundation` |

### Data Quality Tips

✅ **Good Title Formatting:**
```
Maybelline Fit Me Matte + Poreless Foundation 128 Warm Nude
L'Oreal Infallible 24H Fresh Wear Foundation 130 True Beige
MAC Ruby Woo Retro Matte Lipstick
```

❌ **Poor Title Formatting:**
```
Foundation 128                    # Missing brand
Maybelline Foundation            # Missing shade/code
MAYBELLINE FIT ME FOUNDATION    # All caps (acceptable but not ideal)
```

---

## Running the Matcher

### Basic Usage

```bash
python url_mapper.py \
    --a data/nykaa.csv \
    --b data/purplle.csv \
    --out output/
```

### With Custom Parameters

```bash
python url_mapper.py \
    --a data/nykaa.csv \
    --b data/purplle.csv \
    --out results/2026-01-07/ \
    --top_k 50 \
    --model sentence-transformers/all-MiniLM-L6-v2
```

### Performance Tuning

**For faster matching (less accurate):**
```bash
python url_mapper.py --a data/a.csv --b data/b.csv --top_k 10
```

**For better accuracy (slower):**
```bash
python url_mapper.py --a data/a.csv --b data/b.csv --top_k 100
```

**Recommended Settings by Dataset Size:**

| Site A | Site B | top_k | Expected Time |
|--------|--------|-------|---------------|
| 50 | 600 | 25 | ~20 sec |
| 100 | 1000 | 50 | ~45 sec |
| 500 | 5000 | 25 | ~3 min |
| 1000 | 10000 | 50 | ~8 min |

---

## Understanding the Output

### Output CSV Structure

```csv
source_url,source_title,best_match_url,best_match_title,confidence,confidence_label,raw_score,why_not_100,needs_review,top_5_candidates
```

### Example Row

```
source_url: https://nykaa.com/maybelline-fit-me-128
source_title: Maybelline Fit Me Matte + Poreless Foundation 128 Warm Nude
best_match_url: https://purplle.com/maybelline-fit-me-128-warm-nude
best_match_title: Maybelline New York Fit Me Matte+Poreless Liquid Foundation 128 Warm Nude
confidence: 100
confidence_label: exact_match
raw_score: 0.9845
why_not_100:
needs_review: False
top_5_candidates: Maybelline New York Fit Me Matte+Poreless Liquid Foundation 128 Warm Nude (score: 0.985, semantic: 0.972) | ...
```

### Confidence Labels Explained

| Label | Confidence | Meaning | Action |
|-------|------------|---------|--------|
| `exact_match` | 100% | Perfect match found | Use immediately |
| `high_confidence` | 90% | Very strong match | Safe to use |
| `good_match` | 80% | Likely correct | Review if critical |
| `likely_match` | 70% | Probably correct | Manual review recommended |
| `manual_review` | 50% | Uncertain match | Must review manually |
| `no_confident_match` | 0% | No good match found | Find alternative |

### "Why Not 100%" Examples

```
Brand mismatch: Lakme vs Maybelline
→ Different brands, cannot be 100%

Shade differs: 128 vs 130
→ Same product line but different shades

Product type differs: Matte vs Glossy
→ Different finish/formulation

Semantic similarity below threshold: 0.87
→ Titles not similar enough

Low text overlap: 0.42
→ Few common words in titles
```

---

## Reviewing Matches

### Filter by Confidence

**View only matches needing review:**
```python
import pandas as pd
df = pd.read_csv('output/matches.csv')
needs_review = df[df['needs_review'] == True]
needs_review.to_csv('output/review_queue.csv', index=False)
```

**View by confidence bucket:**
```python
exact = df[df['confidence_label'] == 'exact_match']
high = df[df['confidence_label'] == 'high_confidence']
manual = df[df['confidence_label'] == 'manual_review']

print(f"Exact matches: {len(exact)}")
print(f"High confidence: {len(high)}")
print(f"Manual review needed: {len(manual)}")
```

### Analyzing Alternative Candidates

The `top_5_candidates` column shows other potential matches:

```python
# Parse top 5 candidates
import re

def parse_candidates(candidates_str):
    pattern = r"(.+?) \(score: ([\d.]+), semantic: ([\d.]+)\)"
    matches = re.findall(pattern, candidates_str)
    return [(title, float(score), float(sem)) for title, score, sem in matches]

for _, row in df.iterrows():
    if row['confidence'] < 80:
        print(f"\nSource: {row['source_title']}")
        print(f"Best match: {row['best_match_title']} ({row['confidence']}%)")
        print("Alternatives:")
        for i, (title, score, sem) in enumerate(parse_candidates(row['top_5_candidates'])[1:], 2):
            print(f"  {i}. {title} (score: {score:.3f})")
```

---

## Monitoring & Statistics

### Key Metrics to Track

```python
import pandas as pd
import numpy as np

df = pd.read_csv('output/matches.csv')

# Overall statistics
print(f"Total products: {len(df)}")
print(f"Exact matches: {(df['confidence'] == 100).sum()}")
print(f"Needs review: {df['needs_review'].sum()}")
print(f"Average confidence: {df['confidence'].mean():.1f}%")
print(f"Average score: {df['raw_score'].mean():.3f}")

# Distribution by confidence
print("\nConfidence Distribution:")
print(df['confidence_label'].value_counts())

# Score quartiles
print("\nScore Quartiles:")
print(df['raw_score'].describe())
```

---

## Troubleshooting

### Common Issues

**1. CSV Column Mismatch**
```
Error: Missing columns in data/nykaa.csv: {'brand'}
```
**Fix:** Ensure CSV has exact columns: `url`, `title`, `brand`, `category`

**2. Memory Error**
```
RuntimeError: CUDA out of memory
```
**Fix:** Force CPU usage by setting environment variable before running:
```bash
export CUDA_VISIBLE_DEVICES=""
python url_mapper.py --a data/a.csv --b data/b.csv
```

**3. Model Download Fails**
```
Error downloading sentence-transformers model
```
**Fix:** Ensure internet connection and retry. Model will be cached after first download.

**4. Low Matching Quality**
```
Most matches have confidence < 70%
```
**Fix:**
- Check data quality (titles have brand/product codes?)
- Increase `--top_k` to 50 or 100
- Use a better model: `sentence-transformers/paraphrase-multilingual-mpnet-base-v2`

---

## Best Practices

### Do's

- Clean your data first: Remove duplicates, fix encoding issues
- Use consistent naming: Same brand names across sites
- Include product codes: Helps exact matching (e.g., "SKU123", "Model456")
- Review borderline matches: Always check 50-79% confidence matches
- Log your runs: Keep `matching_log.txt` for each run
- Version your data: Track which CSV versions were matched

### Don'ts

- Don't trust 50% matches blindly: Always review
- Don't mix categories: Match foundations with foundations, not with lipsticks
- Don't skip data validation: Use `head` to check CSV format before running
- Don't ignore alternatives: Sometimes 2nd best match is correct
- Don't over-rely on automation: Human review for critical use cases

---

## Support & Resources

- **Documentation**: `README.md`
- **Code**: `url_mapper.py`
- **Logs**: `output/matching_log.txt`
- **Sample Data**: `data/sample_*.csv`

For issues or questions, check the logs first:
```bash
cat output/matching_log.txt | grep ERROR
tail -n 50 output/matching_log.txt
```
