# Installation Guide

## Prerequisites

- Python 3.11 or higher
- pip (Python package installer)
- 2GB free disk space (for models)
- 4GB RAM minimum

## Step-by-Step Installation

### 1. Create Virtual Environment

```bash
cd /Users/adityaaman/Desktop/All\ Development/urltourl
python3.11 -m venv venv
```

### 2. Activate Virtual Environment

**On macOS/Linux:**
```bash
source venv/bin/activate
```

**On Windows:**
```bash
venv\Scripts\activate
```

You should see `(venv)` prefix in your terminal.

### 3. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

This will install:
- sentence-transformers (300MB)
- torch (500MB)
- transformers (200MB)
- numpy, pandas, scikit-learn
- tqdm

Installation takes 3-5 minutes depending on internet speed.

### 4. Verify Installation

```bash
python test_matcher.py
```

Expected output:
```
============================================================
URL MAPPER - UNIT TESTS
============================================================

Testing TextProcessor...
  ✓ Text normalization works
  ✓ Tokenization works
  ✓ Product code extraction works
  ✓ Attribute extraction works
✓ TextProcessor tests passed

...

============================================================
ALL TESTS PASSED!
============================================================
```

### 5. Run Quick Demo

```bash
./quick_test.sh
```

This will:
- Verify dependencies
- Run matcher on sample data (10×25 products)
- Generate results in `output/matches.csv`

Expected completion time: 20-30 seconds

## Troubleshooting

### Issue: Python 3.11 not found

**Solution:**
```bash
# Install Python 3.11 via Homebrew (macOS)
brew install python@3.11

# Or download from python.org
# https://www.python.org/downloads/
```

### Issue: pip install fails

**Solution:**
```bash
# Upgrade pip
python -m pip install --upgrade pip

# Install with verbose output to see errors
pip install -v -r requirements.txt
```

### Issue: torch installation fails

**Solution:**
```bash
# Install CPU-only version (smaller, faster)
pip install torch --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt
```

### Issue: Out of memory during model loading

**Solution:**
Use a smaller model or ensure at least 4GB RAM available:
```bash
python url_mapper.py \
    --a data/a.csv \
    --b data/b.csv \
    --model sentence-transformers/all-MiniLM-L6-v2
```

### Issue: Model download fails

**Solution:**
```bash
# Pre-download model
python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"
```

## Verifying Installation

### Check Python Version

```bash
python --version
# Should show: Python 3.11.x or higher
```

### Check Installed Packages

```bash
pip list | grep -E "(sentence-transformers|torch|numpy|pandas|scikit-learn)"
```

Expected output:
```
numpy                     1.24.0
pandas                    2.0.0
scikit-learn              1.3.0
sentence-transformers     2.2.0
torch                     2.0.0
```

### Check Model Cache

```bash
python -c "from sentence_transformers import SentenceTransformer; m = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2'); print('Model loaded successfully')"
```

## Optional: GPU Support

If you have a CUDA-capable GPU:

```bash
# Install PyTorch with CUDA support
pip uninstall torch
pip install torch --index-url https://download.pytorch.org/whl/cu118

# Verify GPU is available
python -c "import torch; print(f'CUDA available: {torch.cuda.is_available()}')"
```

GPU acceleration provides 3-5x speedup for embedding generation.

## First Run

After successful installation:

```bash
# Run on sample data
python url_mapper.py \
    --a data/sample_nykaa.csv \
    --b data/sample_purplle.csv \
    --out output/

# View results
cat output/matches.csv | head -20
```

Expected output location: `output/matches.csv`

## Next Steps

- Read `README.md` for full documentation
- Check `USAGE_GUIDE.md` for detailed usage instructions
- Run `python test_matcher.py` to verify all components work
- Prepare your own CSV data with columns: `url`, `title`, `brand`, `category`

## Getting Help

If issues persist:

1. Check logs: `cat output/matching_log.txt`
2. Run tests: `python test_matcher.py`
3. Verify CSV format: `head data/sample_nykaa.csv`
4. Check Python version: `python --version`
5. Check dependencies: `pip list`

## Uninstallation

To remove the environment:

```bash
# Deactivate virtual environment
deactivate

# Remove directory
rm -rf venv/
```

## System Requirements Summary

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| Python | 3.11 | 3.11+ |
| RAM | 4GB | 8GB+ |
| Disk Space | 2GB | 5GB |
| CPU | 2 cores | 4+ cores |
| GPU | None | CUDA-capable |
| Internet | Required for first run | - |
