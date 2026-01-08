#!/bin/bash
# Quick test script for URL mapper
# Run this to test the engine with sample data

set -e

echo "=========================================="
echo "URL-to-URL Matcher Quick Test"
echo "=========================================="
echo ""

# Check if virtual environment exists
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3.11 -m venv venv
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies if needed
if ! python -c "import sentence_transformers" 2>/dev/null; then
    echo "Installing dependencies..."
    pip install -q --upgrade pip
    pip install -q -r requirements.txt
fi

# Clean output directory
echo "Cleaning output directory..."
rm -rf output/
mkdir -p output/

# Run the matcher
echo ""
echo "Running matcher on sample data..."
echo "Site A: data/sample_nykaa.csv (10 products)"
echo "Site B: data/sample_purplle.csv (25 products)"
echo ""

python url_mapper.py \
    --a data/sample_nykaa.csv \
    --b data/sample_purplle.csv \
    --out output/ \
    --top_k 10

echo ""
echo "=========================================="
echo "Test Complete!"
echo "=========================================="
echo "Results saved to: output/matches.csv"
echo "Log file: output/matching_log.txt"
echo ""
echo "View results:"
echo "  cat output/matches.csv | head -20"
echo "  open output/matches.csv"
echo ""
