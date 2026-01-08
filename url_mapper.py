#!/usr/bin/env python3
"""
Semantic URL-to-URL Product Matching Engine
Uses sentence-transformers for multi-signal product matching across e-commerce sites.

Author: Aditya Aman
Created: 2026-01-07
"""

import argparse
import logging
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from tqdm import tqdm


# ============================================================================
# Configuration & Data Classes
# ============================================================================

@dataclass
class MatchResult:
    """Container for match results with confidence scoring."""
    source_url: str
    source_title: str
    best_match_url: str
    best_match_title: str
    confidence: int
    confidence_label: str
    raw_score: float
    why_not_100: str
    needs_review: bool
    top_5_candidates: str


@dataclass
class ProductRecord:
    """Structured product data with computed features."""
    url: str
    title: str
    brand: str
    category: str
    title_tokens: set
    normalized_title: str
    product_code: Optional[str]
    attributes: Dict[str, str]


# ============================================================================
# Logging Setup
# ============================================================================

def setup_logging(output_dir: Path) -> logging.Logger:
    """Configure logging to both console and file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    log_file = output_dir / "matching_log.txt"

    # Create logger
    logger = logging.getLogger("URLMapper")
    logger.setLevel(logging.INFO)

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(message)s',
        datefmt='%H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)

    # File handler
    file_handler = logging.FileHandler(log_file, mode='w')
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        '%(asctime)s | %(levelname)s | %(funcName)s:%(lineno)d | %(message)s'
    )
    file_handler.setFormatter(file_formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

    return logger


# ============================================================================
# Text Processing & Feature Extraction
# ============================================================================

class TextProcessor:
    """Handles text normalization and feature extraction."""

    # Common cosmetics attributes patterns
    SHADE_PATTERN = re.compile(r'\b(\d{1,3}[A-Z]?|\w+\s?\d+)\b', re.IGNORECASE)
    PRODUCT_CODE_PATTERN = re.compile(r'\b([A-Z]{2,}\d{3,}|\d{3,}[A-Z]{2,})\b')
    COLOR_KEYWORDS = {
        'red', 'blue', 'pink', 'nude', 'coral', 'berry', 'plum', 'brown',
        'black', 'white', 'gold', 'silver', 'bronze', 'copper', 'mauve'
    }
    FINISH_KEYWORDS = {
        'matte', 'glossy', 'satin', 'shimmer', 'metallic', 'cream',
        'powder', 'liquid', 'gel', 'balm'
    }

    @staticmethod
    def normalize_text(text: str) -> str:
        """Normalize text for consistent comparison."""
        if pd.isna(text):
            return ""
        text = str(text).lower().strip()
        # Remove special characters but keep alphanumeric and spaces
        text = re.sub(r'[^\w\s-]', ' ', text)
        # Collapse multiple spaces
        text = re.sub(r'\s+', ' ', text)
        return text

    @staticmethod
    def tokenize(text: str) -> set:
        """Create token set for Jaccard similarity."""
        normalized = TextProcessor.normalize_text(text)
        tokens = set(normalized.split())
        # Remove common stop words for beauty products
        stop_words = {'the', 'a', 'an', 'and', 'or', 'for', 'with', 'by', 'ml', 'g'}
        return tokens - stop_words

    @staticmethod
    def extract_product_code(text: str) -> Optional[str]:
        """Extract product/SKU code from title."""
        match = TextProcessor.PRODUCT_CODE_PATTERN.search(text)
        return match.group(1).upper() if match else None

    @staticmethod
    def extract_attributes(title: str) -> Dict[str, str]:
        """Extract product attributes (shade, color, finish)."""
        normalized = TextProcessor.normalize_text(title)
        attributes = {}

        # Extract shade number
        shade_match = TextProcessor.SHADE_PATTERN.search(title)
        if shade_match:
            attributes['shade'] = shade_match.group(1).lower()

        # Extract color
        tokens = set(normalized.split())
        found_colors = tokens & TextProcessor.COLOR_KEYWORDS
        if found_colors:
            attributes['color'] = ', '.join(sorted(found_colors))

        # Extract finish
        found_finish = tokens & TextProcessor.FINISH_KEYWORDS
        if found_finish:
            attributes['finish'] = ', '.join(sorted(found_finish))

        return attributes


# ============================================================================
# Product Matching Engine
# ============================================================================

class ProductMatcher:
    """Core matching engine using multi-signal scoring."""

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        logger: Optional[logging.Logger] = None
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.logger.info(f"Loading model: {model_name}")
        self.model = SentenceTransformer(model_name)
        self.text_processor = TextProcessor()

    def load_products(self, csv_path: Path, site_name: str) -> Tuple[List[ProductRecord], np.ndarray]:
        """Load and process products from CSV."""
        self.logger.info(f"Loading {site_name} products from {csv_path}")

        df = pd.read_csv(csv_path)
        required_cols = {'url', 'title', 'brand', 'category'}
        if not required_cols.issubset(df.columns):
            missing = required_cols - set(df.columns)
            raise ValueError(f"Missing columns in {csv_path}: {missing}")

        # Process records
        products = []
        for _, row in df.iterrows():
            title = str(row['title'])
            products.append(ProductRecord(
                url=str(row['url']),
                title=title,
                brand=str(row['brand']).lower().strip(),
                category=str(row['category']).lower().strip(),
                title_tokens=self.text_processor.tokenize(title),
                normalized_title=self.text_processor.normalize_text(title),
                product_code=self.text_processor.extract_product_code(title),
                attributes=self.text_processor.extract_attributes(title)
            ))

        # Generate embeddings
        self.logger.info(f"Generating embeddings for {len(products)} products...")
        titles = [p.title for p in products]
        embeddings = self.model.encode(
            titles,
            show_progress_bar=True,
            batch_size=32,
            normalize_embeddings=True  # Pre-normalize for cosine similarity
        )

        self.logger.info(f"Loaded {len(products)} products from {site_name}")
        return products, embeddings

    def jaccard_similarity(self, set1: set, set2: set) -> float:
        """Compute Jaccard similarity between token sets."""
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def attribute_match_score(self, prod_a: ProductRecord, prod_b: ProductRecord) -> float:
        """Calculate attribute matching score."""
        score = 0.0
        matches = 0
        total = 0

        # Brand match (most important)
        total += 1
        if prod_a.brand and prod_b.brand:
            if prod_a.brand == prod_b.brand:
                score += 1.0
                matches += 1
            elif prod_a.brand in prod_b.brand or prod_b.brand in prod_a.brand:
                score += 0.5
                matches += 0.5

        # Product code exact match (critical)
        if prod_a.product_code and prod_b.product_code:
            total += 1
            if prod_a.product_code == prod_b.product_code:
                score += 1.0
                matches += 1

        # Attribute matches
        for attr_key in ['shade', 'color', 'finish']:
            val_a = prod_a.attributes.get(attr_key)
            val_b = prod_b.attributes.get(attr_key)
            if val_a and val_b:
                total += 1
                if val_a == val_b:
                    score += 1.0
                    matches += 1
                elif val_a in val_b or val_b in val_a:
                    score += 0.5
                    matches += 0.5

        return score / total if total > 0 else 0.0

    def compute_multi_signal_score(
        self,
        prod_a: ProductRecord,
        prod_b: ProductRecord,
        semantic_sim: float
    ) -> float:
        """Compute weighted multi-signal score."""
        # 60% semantic similarity (already normalized)
        semantic_score = semantic_sim * 0.60

        # 25% token overlap (Jaccard)
        token_score = self.jaccard_similarity(
            prod_a.title_tokens,
            prod_b.title_tokens
        ) * 0.25

        # 15% attribute match
        attr_score = self.attribute_match_score(prod_a, prod_b) * 0.15

        return semantic_score + token_score + attr_score

    def check_exact_match(self, prod_a: ProductRecord, prod_b: ProductRecord) -> bool:
        """Check if products are exact matches."""
        # Exact match if brand + product code match
        if prod_a.product_code and prod_b.product_code:
            if (prod_a.brand == prod_b.brand and
                prod_a.product_code == prod_b.product_code):
                return True

        # Very high text similarity + brand match
        if prod_a.brand == prod_b.brand:
            if prod_a.normalized_title == prod_b.normalized_title:
                return True

        return False

    def get_confidence_bucket(self, score: float, is_exact: bool) -> Tuple[int, str]:
        """Map score to confidence bucket."""
        if is_exact:
            return (100, "exact_match")
        if score >= 0.95:
            return (100, "exact_match")
        if score >= 0.90:
            return (90, "high_confidence")
        if score >= 0.80:
            return (80, "good_match")
        if score >= 0.70:
            return (70, "likely_match")
        if score >= 0.50:
            return (50, "manual_review")
        return (0, "no_confident_match")

    def explain_why_not_100(
        self,
        prod_a: ProductRecord,
        prod_b: ProductRecord,
        score: float
    ) -> str:
        """Generate human-readable explanation for why match isn't 100%."""
        reasons = []

        # Check brand
        if prod_a.brand != prod_b.brand:
            reasons.append(f"Brand mismatch: {prod_a.brand} vs {prod_b.brand}")

        # Check product code
        if prod_a.product_code and prod_b.product_code:
            if prod_a.product_code != prod_b.product_code:
                reasons.append(
                    f"Product code differs: {prod_a.product_code} vs {prod_b.product_code}"
                )

        # Check attributes
        for attr_key in ['shade', 'color', 'finish']:
            val_a = prod_a.attributes.get(attr_key)
            val_b = prod_b.attributes.get(attr_key)
            if val_a and val_b and val_a != val_b:
                reasons.append(
                    f"{attr_key.capitalize()} differs: {val_a} vs {val_b}"
                )

        # Check semantic similarity
        if score < 0.95:
            reasons.append(f"Semantic similarity below threshold: {score:.2f}")

        # Check token overlap
        jaccard = self.jaccard_similarity(prod_a.title_tokens, prod_b.title_tokens)
        if jaccard < 0.7:
            reasons.append(f"Low text overlap: {jaccard:.2f}")

        if not reasons:
            reasons.append("Minor variations in product details")

        return "; ".join(reasons)

    def find_matches(
        self,
        site_a_products: List[ProductRecord],
        site_a_embeddings: np.ndarray,
        site_b_products: List[ProductRecord],
        site_b_embeddings: np.ndarray,
        top_k: int = 25
    ) -> List[MatchResult]:
        """Find best matches for each product in site A."""
        self.logger.info(f"Computing similarity matrix...")

        # Compute cosine similarity (embeddings are pre-normalized)
        similarity_matrix = cosine_similarity(site_a_embeddings, site_b_embeddings)

        results = []
        self.logger.info(f"Processing {len(site_a_products)} products...")

        for i, prod_a in enumerate(tqdm(site_a_products, desc="Matching products")):
            # Get top-k candidates by semantic similarity
            semantic_sims = similarity_matrix[i]
            top_k_indices = np.argsort(semantic_sims)[-top_k:][::-1]

            # Compute multi-signal scores for top candidates
            candidate_scores = []
            for j in top_k_indices:
                prod_b = site_b_products[j]
                semantic_sim = semantic_sims[j]

                # Check for exact match override
                is_exact = self.check_exact_match(prod_a, prod_b)

                if is_exact:
                    multi_score = 1.0
                else:
                    multi_score = self.compute_multi_signal_score(
                        prod_a, prod_b, semantic_sim
                    )

                candidate_scores.append({
                    'index': j,
                    'score': multi_score,
                    'is_exact': is_exact,
                    'semantic_sim': semantic_sim
                })

            # Sort by multi-signal score
            candidate_scores.sort(key=lambda x: x['score'], reverse=True)

            # Get best match
            best = candidate_scores[0]
            best_prod = site_b_products[best['index']]

            # Determine confidence
            confidence, label = self.get_confidence_bucket(
                best['score'],
                best['is_exact']
            )

            # Generate explanation
            why_not_100 = ""
            if confidence < 100:
                why_not_100 = self.explain_why_not_100(
                    prod_a,
                    best_prod,
                    best['score']
                )

            # Format top 5 candidates
            top_5 = []
            for c in candidate_scores[:5]:
                cand_prod = site_b_products[c['index']]
                top_5.append(
                    f"{cand_prod.title} (score: {c['score']:.3f}, "
                    f"semantic: {c['semantic_sim']:.3f})"
                )

            results.append(MatchResult(
                source_url=prod_a.url,
                source_title=prod_a.title,
                best_match_url=best_prod.url,
                best_match_title=best_prod.title,
                confidence=confidence,
                confidence_label=label,
                raw_score=best['score'],
                why_not_100=why_not_100,
                needs_review=(confidence < 80),
                top_5_candidates=" | ".join(top_5)
            ))

        return results


# ============================================================================
# Statistics & Output
# ============================================================================

def generate_statistics(results: List[MatchResult], logger: logging.Logger):
    """Generate and log matching statistics."""
    total = len(results)

    # Count by confidence bucket
    confidence_dist = {}
    for r in results:
        confidence_dist[r.confidence_label] = confidence_dist.get(r.confidence_label, 0) + 1

    # Count needs review
    needs_review = sum(1 for r in results if r.needs_review)

    # Average scores by bucket
    bucket_scores = {}
    for r in results:
        if r.confidence_label not in bucket_scores:
            bucket_scores[r.confidence_label] = []
        bucket_scores[r.confidence_label].append(r.raw_score)

    logger.info("\n" + "="*80)
    logger.info("MATCHING STATISTICS")
    logger.info("="*80)
    logger.info(f"Total products matched: {total}")
    logger.info(f"Products needing review: {needs_review} ({needs_review/total*100:.1f}%)")
    logger.info("\nConfidence Distribution:")

    for label in ["exact_match", "high_confidence", "good_match",
                   "likely_match", "manual_review", "no_confident_match"]:
        count = confidence_dist.get(label, 0)
        pct = count / total * 100
        avg_score = np.mean(bucket_scores.get(label, [0]))
        logger.info(f"  {label:20s}: {count:4d} ({pct:5.1f}%) | Avg Score: {avg_score:.3f}")

    # Score statistics
    all_scores = [r.raw_score for r in results]
    logger.info(f"\nScore Statistics:")
    logger.info(f"  Mean:   {np.mean(all_scores):.3f}")
    logger.info(f"  Median: {np.median(all_scores):.3f}")
    logger.info(f"  Min:    {np.min(all_scores):.3f}")
    logger.info(f"  Max:    {np.max(all_scores):.3f}")
    logger.info(f"  Std:    {np.std(all_scores):.3f}")
    logger.info("="*80 + "\n")


def save_results(results: List[MatchResult], output_path: Path, logger: logging.Logger):
    """Save matching results to CSV."""
    df = pd.DataFrame([
        {
            'source_url': r.source_url,
            'source_title': r.source_title,
            'best_match_url': r.best_match_url,
            'best_match_title': r.best_match_title,
            'confidence': r.confidence,
            'confidence_label': r.confidence_label,
            'raw_score': round(r.raw_score, 4),
            'why_not_100': r.why_not_100,
            'needs_review': r.needs_review,
            'top_5_candidates': r.top_5_candidates
        }
        for r in results
    ])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    logger.info(f"Results saved to: {output_path}")


# ============================================================================
# Main CLI
# ============================================================================

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Semantic URL-to-URL Product Matching Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python url_mapper.py --a data/nykaa.csv --b data/purplle.csv
  python url_mapper.py --a data/nykaa.csv --b data/purplle.csv --top_k 50
  python url_mapper.py --a data/nykaa.csv --b data/purplle.csv --out results/
        """
    )

    parser.add_argument(
        '--a',
        type=str,
        required=True,
        help='Path to Site A CSV (smaller dataset)'
    )
    parser.add_argument(
        '--b',
        type=str,
        required=True,
        help='Path to Site B CSV (larger dataset)'
    )
    parser.add_argument(
        '--out',
        type=str,
        default='output/',
        help='Output directory (default: output/)'
    )
    parser.add_argument(
        '--top_k',
        type=int,
        default=25,
        help='Number of top candidates to consider (default: 25)'
    )
    parser.add_argument(
        '--model',
        type=str,
        default='sentence-transformers/all-MiniLM-L6-v2',
        help='Sentence transformer model name'
    )

    return parser.parse_args()


def main():
    """Main execution function."""
    args = parse_args()

    # Setup paths
    site_a_path = Path(args.a)
    site_b_path = Path(args.b)
    output_dir = Path(args.out)
    output_csv = output_dir / "matches.csv"

    # Validate inputs
    if not site_a_path.exists():
        print(f"Error: Site A CSV not found: {site_a_path}")
        sys.exit(1)
    if not site_b_path.exists():
        print(f"Error: Site B CSV not found: {site_b_path}")
        sys.exit(1)

    # Setup logging
    logger = setup_logging(output_dir)
    logger.info("="*80)
    logger.info("SEMANTIC URL-TO-URL PRODUCT MATCHING ENGINE")
    logger.info("="*80)
    logger.info(f"Site A: {site_a_path}")
    logger.info(f"Site B: {site_b_path}")
    logger.info(f"Output: {output_csv}")
    logger.info(f"Top-K: {args.top_k}")
    logger.info(f"Model: {args.model}")
    logger.info("="*80 + "\n")

    try:
        # Initialize matcher
        matcher = ProductMatcher(model_name=args.model, logger=logger)

        # Load products
        site_a_products, site_a_embeddings = matcher.load_products(
            site_a_path, "Site A"
        )
        site_b_products, site_b_embeddings = matcher.load_products(
            site_b_path, "Site B"
        )

        # Find matches
        results = matcher.find_matches(
            site_a_products,
            site_a_embeddings,
            site_b_products,
            site_b_embeddings,
            top_k=args.top_k
        )

        # Generate statistics
        generate_statistics(results, logger)

        # Save results
        save_results(results, output_csv, logger)

        logger.info("✓ Matching completed successfully!")

    except Exception as e:
        logger.error(f"Error during matching: {str(e)}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
