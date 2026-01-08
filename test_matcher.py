#!/usr/bin/env python3
"""
Test script for URL Mapper
Validates core functionality without requiring full dataset
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from url_mapper import (
    TextProcessor,
    ProductRecord,
    ProductMatcher,
    setup_logging
)


def test_text_processor():
    """Test text processing utilities."""
    print("Testing TextProcessor...")

    processor = TextProcessor()

    # Test normalization
    text = "Maybelline Fit Me! Foundation #128"
    normalized = processor.normalize_text(text)
    assert "maybelline" in normalized
    assert "128" in normalized
    print("  ✓ Text normalization works")

    # Test tokenization
    tokens = processor.tokenize("Lakme 9to5 Matte Lipstick")
    assert "lakme" in tokens
    assert "9to5" in tokens
    assert "matte" in tokens
    assert "the" not in tokens  # Stop word removed
    print("  ✓ Tokenization works")

    # Test product code extraction
    code1 = processor.extract_product_code("Maybelline SKU123 Foundation")
    assert code1 == "SKU123"
    code2 = processor.extract_product_code("Product 456ABC Lipstick")
    assert code2 == "456ABC"
    print("  ✓ Product code extraction works")

    # Test attribute extraction
    attrs = processor.extract_attributes("Lakme Matte Lipstick 128 Red")
    assert "shade" in attrs
    assert "128" in attrs["shade"]
    assert "color" in attrs
    assert "red" in attrs["color"]
    assert "finish" in attrs
    assert "matte" in attrs["finish"]
    print("  ✓ Attribute extraction works")

    print("✓ TextProcessor tests passed\n")


def test_product_record_creation():
    """Test ProductRecord creation."""
    print("Testing ProductRecord creation...")

    processor = TextProcessor()

    record = ProductRecord(
        url="https://nykaa.com/test",
        title="Maybelline Fit Me Foundation 128 Warm Nude",
        brand="Maybelline",
        category="Foundation",
        title_tokens=processor.tokenize("Maybelline Fit Me Foundation 128 Warm Nude"),
        normalized_title=processor.normalize_text("Maybelline Fit Me Foundation 128 Warm Nude"),
        product_code=processor.extract_product_code("Maybelline Fit Me Foundation 128 Warm Nude"),
        attributes=processor.extract_attributes("Maybelline Fit Me Foundation 128 Warm Nude")
    )

    assert record.brand == "Maybelline"
    assert "maybelline" in record.title_tokens
    assert "shade" in record.attributes
    print("  ✓ ProductRecord created successfully")
    print("✓ ProductRecord tests passed\n")


def test_jaccard_similarity():
    """Test Jaccard similarity calculation."""
    print("Testing Jaccard similarity...")

    matcher = ProductMatcher()

    set1 = {"maybelline", "fit", "me", "foundation"}
    set2 = {"maybelline", "fit", "me", "foundation"}
    sim = matcher.jaccard_similarity(set1, set2)
    assert sim == 1.0
    print("  ✓ Identical sets: 1.0")

    set1 = {"maybelline", "fit", "me", "foundation"}
    set2 = {"lakme", "absolute", "lipstick"}
    sim = matcher.jaccard_similarity(set1, set2)
    assert sim == 0.0
    print("  ✓ Disjoint sets: 0.0")

    set1 = {"maybelline", "fit", "me"}
    set2 = {"maybelline", "superstay", "matte"}
    sim = matcher.jaccard_similarity(set1, set2)
    assert 0 < sim < 1
    print(f"  ✓ Partial overlap: {sim:.3f}")

    print("✓ Jaccard similarity tests passed\n")


def test_confidence_buckets():
    """Test confidence bucket assignment."""
    print("Testing confidence buckets...")

    matcher = ProductMatcher()

    # Test each bucket
    conf, label = matcher.get_confidence_bucket(0.98, False)
    assert conf == 100 and label == "exact_match"
    print("  ✓ 0.98 → exact_match")

    conf, label = matcher.get_confidence_bucket(0.92, False)
    assert conf == 90 and label == "high_confidence"
    print("  ✓ 0.92 → high_confidence")

    conf, label = matcher.get_confidence_bucket(0.85, False)
    assert conf == 80 and label == "good_match"
    print("  ✓ 0.85 → good_match")

    conf, label = matcher.get_confidence_bucket(0.75, False)
    assert conf == 70 and label == "likely_match"
    print("  ✓ 0.75 → likely_match")

    conf, label = matcher.get_confidence_bucket(0.60, False)
    assert conf == 50 and label == "manual_review"
    print("  ✓ 0.60 → manual_review")

    conf, label = matcher.get_confidence_bucket(0.30, False)
    assert conf == 0 and label == "no_confident_match"
    print("  ✓ 0.30 → no_confident_match")

    # Test exact match override
    conf, label = matcher.get_confidence_bucket(0.70, True)
    assert conf == 100 and label == "exact_match"
    print("  ✓ Exact match override works")

    print("✓ Confidence bucket tests passed\n")


def test_exact_match_detection():
    """Test exact match detection logic."""
    print("Testing exact match detection...")

    matcher = ProductMatcher()
    processor = TextProcessor()

    # Create two identical products with same brand + product code
    prod_a = ProductRecord(
        url="https://site-a.com/product",
        title="Maybelline Fit Me Foundation SKU123",
        brand="maybelline",
        category="foundation",
        title_tokens=processor.tokenize("Maybelline Fit Me Foundation SKU123"),
        normalized_title=processor.normalize_text("Maybelline Fit Me Foundation SKU123"),
        product_code="SKU123",
        attributes={}
    )

    prod_b = ProductRecord(
        url="https://site-b.com/product",
        title="Maybelline New York Fit Me Foundation SKU123",
        brand="maybelline",
        category="foundation",
        title_tokens=processor.tokenize("Maybelline New York Fit Me Foundation SKU123"),
        normalized_title=processor.normalize_text("Maybelline New York Fit Me Foundation SKU123"),
        product_code="SKU123",
        attributes={}
    )

    is_exact = matcher.check_exact_match(prod_a, prod_b)
    assert is_exact == True
    print("  ✓ Same brand + product code → exact match")

    # Different product codes
    prod_b.product_code = "SKU456"
    is_exact = matcher.check_exact_match(prod_a, prod_b)
    assert is_exact == False
    print("  ✓ Different product codes → not exact")

    print("✓ Exact match detection tests passed\n")


def test_attribute_matching():
    """Test attribute matching scoring."""
    print("Testing attribute matching...")

    matcher = ProductMatcher()
    processor = TextProcessor()

    # Products with matching attributes
    prod_a = ProductRecord(
        url="https://site-a.com/product",
        title="Maybelline Lipstick 128 Red Matte",
        brand="maybelline",
        category="lipstick",
        title_tokens=set(),
        normalized_title="",
        product_code="128",
        attributes={"shade": "128", "color": "red", "finish": "matte"}
    )

    prod_b = ProductRecord(
        url="https://site-b.com/product",
        title="Maybelline Lipstick 128 Red Matte",
        brand="maybelline",
        category="lipstick",
        title_tokens=set(),
        normalized_title="",
        product_code="128",
        attributes={"shade": "128", "color": "red", "finish": "matte"}
    )

    score = matcher.attribute_match_score(prod_a, prod_b)
    assert score == 1.0
    print(f"  ✓ Perfect attribute match: {score:.2f}")

    # Different brand
    prod_b.brand = "lakme"
    score = matcher.attribute_match_score(prod_a, prod_b)
    assert score < 1.0
    print(f"  ✓ Different brand reduces score: {score:.2f}")

    print("✓ Attribute matching tests passed\n")


def test_explanation_generation():
    """Test 'why not 100%' explanation generation."""
    print("Testing explanation generation...")

    matcher = ProductMatcher()
    processor = TextProcessor()

    prod_a = ProductRecord(
        url="https://site-a.com/product",
        title="Maybelline Lipstick 128 Red",
        brand="maybelline",
        category="lipstick",
        title_tokens=processor.tokenize("Maybelline Lipstick 128 Red"),
        normalized_title=processor.normalize_text("Maybelline Lipstick 128 Red"),
        product_code="128",
        attributes={"shade": "128", "color": "red"}
    )

    prod_b = ProductRecord(
        url="https://site-b.com/product",
        title="Lakme Lipstick 130 Pink",
        brand="lakme",
        category="lipstick",
        title_tokens=processor.tokenize("Lakme Lipstick 130 Pink"),
        normalized_title=processor.normalize_text("Lakme Lipstick 130 Pink"),
        product_code="130",
        attributes={"shade": "130", "color": "pink"}
    )

    explanation = matcher.explain_why_not_100(prod_a, prod_b, 0.65)

    assert "brand" in explanation.lower()
    assert "maybelline" in explanation.lower() and "lakme" in explanation.lower()
    print(f"  ✓ Explanation generated: {explanation[:60]}...")

    print("✓ Explanation generation tests passed\n")


def test_csv_loading():
    """Test CSV loading functionality."""
    print("Testing CSV loading...")

    # Create temporary test CSV
    test_data = pd.DataFrame({
        'url': ['https://example.com/p1', 'https://example.com/p2'],
        'title': ['Product 1', 'Product 2'],
        'brand': ['Brand A', 'Brand B'],
        'category': ['Category 1', 'Category 2']
    })

    test_csv = Path('test_temp.csv')
    test_data.to_csv(test_csv, index=False)

    try:
        matcher = ProductMatcher()
        products, embeddings = matcher.load_products(test_csv, "Test")

        assert len(products) == 2
        assert embeddings.shape[0] == 2
        assert embeddings.shape[1] > 0  # Has embedding dimensions
        print(f"  ✓ Loaded {len(products)} products")
        print(f"  ✓ Generated embeddings: {embeddings.shape}")

        print("✓ CSV loading tests passed\n")

    finally:
        # Cleanup
        if test_csv.exists():
            test_csv.unlink()


def test_multi_signal_scoring():
    """Test complete multi-signal scoring."""
    print("Testing multi-signal scoring...")

    matcher = ProductMatcher()
    processor = TextProcessor()

    # Very similar products
    prod_a = ProductRecord(
        url="https://site-a.com/product",
        title="Maybelline Fit Me Foundation 128",
        brand="maybelline",
        category="foundation",
        title_tokens=processor.tokenize("Maybelline Fit Me Foundation 128"),
        normalized_title=processor.normalize_text("Maybelline Fit Me Foundation 128"),
        product_code="128",
        attributes={"shade": "128"}
    )

    prod_b = ProductRecord(
        url="https://site-b.com/product",
        title="Maybelline Fit Me Foundation 128 Warm Nude",
        brand="maybelline",
        category="foundation",
        title_tokens=processor.tokenize("Maybelline Fit Me Foundation 128 Warm Nude"),
        normalized_title=processor.normalize_text("Maybelline Fit Me Foundation 128 Warm Nude"),
        product_code="128",
        attributes={"shade": "128"}
    )

    # High semantic similarity (assume 0.95 for this test)
    semantic_sim = 0.95
    score = matcher.compute_multi_signal_score(prod_a, prod_b, semantic_sim)

    assert 0.8 < score <= 1.0  # Should be high
    print(f"  ✓ Similar products score: {score:.3f}")

    # Very different products
    prod_c = ProductRecord(
        url="https://site-b.com/product2",
        title="Different Brand Lipstick Red",
        brand="different",
        category="lipstick",
        title_tokens=processor.tokenize("Different Brand Lipstick Red"),
        normalized_title=processor.normalize_text("Different Brand Lipstick Red"),
        product_code="999",
        attributes={"shade": "999", "color": "red"}
    )

    semantic_sim = 0.30
    score = matcher.compute_multi_signal_score(prod_a, prod_c, semantic_sim)

    assert score < 0.5  # Should be low
    print(f"  ✓ Different products score: {score:.3f}")

    print("✓ Multi-signal scoring tests passed\n")


def run_all_tests():
    """Run all unit tests."""
    print("="*60)
    print("URL MAPPER - UNIT TESTS")
    print("="*60)
    print()

    try:
        test_text_processor()
        test_product_record_creation()
        test_jaccard_similarity()
        test_confidence_buckets()
        test_exact_match_detection()
        test_attribute_matching()
        test_explanation_generation()
        test_csv_loading()
        test_multi_signal_scoring()

        print("="*60)
        print("ALL TESTS PASSED!")
        print("="*60)
        return 0

    except AssertionError as e:
        print(f"\n✗ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
