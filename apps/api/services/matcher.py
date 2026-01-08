"""
Matcher Service for URL-to-URL Product Matching API
Wraps the core url_mapper.py matching engine for API use
"""

import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple
from uuid import UUID

import numpy as np

# Add parent directory to path for url_mapper import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from models.schemas import (
    ProductBase, Product, ProductCreate,
    MatchCreate, ConfidenceTier, Site
)

logger = logging.getLogger(__name__)


@dataclass
class MatchResultInternal:
    """Internal match result before database persistence."""
    source_index: int
    target_index: int
    score: float
    confidence_tier: ConfidenceTier
    explanation: str
    needs_review: bool


class MatcherService:
    """
    Service wrapping the url_mapper.py matching engine.
    Provides API-friendly interface for product matching.
    """

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        top_k: int = 25
    ):
        """
        Initialize the matcher service.

        Args:
            model_name: Sentence transformer model to use
            top_k: Number of top candidates to consider per product
        """
        self.model_name = model_name
        self.top_k = top_k
        self._matcher = None
        self._model_loaded = False

    def _ensure_loaded(self):
        """Lazy load the matcher and model."""
        if self._matcher is not None:
            return

        try:
            # Import the ProductMatcher from url_mapper.py
            from url_mapper import ProductMatcher, TextProcessor
            self._matcher = ProductMatcher(model_name=self.model_name, logger=logger)
            self._text_processor = TextProcessor()
            self._model_loaded = True
            logger.info(f"Matcher initialized with model: {self.model_name}")
        except ImportError as e:
            logger.error(f"Failed to import url_mapper: {e}")
            # Fallback: create a simplified matcher
            self._create_fallback_matcher()
        except Exception as e:
            logger.error(f"Error initializing matcher: {e}")
            raise

    def _create_fallback_matcher(self):
        """Create a fallback matcher if url_mapper.py is not available."""
        try:
            from sentence_transformers import SentenceTransformer
            from sklearn.metrics.pairwise import cosine_similarity
            import re

            class FallbackMatcher:
                """Fallback matcher with essential functionality."""

                def __init__(self, model_name: str):
                    self.model = SentenceTransformer(model_name)
                    self.logger = logger

                def encode(self, texts: List[str]) -> np.ndarray:
                    """Encode texts to embeddings."""
                    return self.model.encode(
                        texts,
                        show_progress_bar=False,
                        batch_size=32,
                        normalize_embeddings=True
                    )

            class FallbackTextProcessor:
                """Fallback text processor."""

                @staticmethod
                def normalize_text(text: str) -> str:
                    if not text:
                        return ""
                    text = str(text).lower().strip()
                    text = re.sub(r'[^\w\s-]', ' ', text)
                    text = re.sub(r'\s+', ' ', text)
                    return text

                @staticmethod
                def tokenize(text: str) -> set:
                    normalized = FallbackTextProcessor.normalize_text(text)
                    tokens = set(normalized.split())
                    stop_words = {'the', 'a', 'an', 'and', 'or', 'for', 'with', 'by', 'ml', 'g'}
                    return tokens - stop_words

            self._matcher = FallbackMatcher(self.model_name)
            self._text_processor = FallbackTextProcessor()
            self._model_loaded = True
            logger.info("Using fallback matcher implementation")

        except Exception as e:
            logger.error(f"Failed to create fallback matcher: {e}")
            raise

    @property
    def is_loaded(self) -> bool:
        """Check if model is loaded."""
        return self._model_loaded

    def match_products(
        self,
        site_a_products: List[ProductBase],
        site_b_products: List[ProductBase],
        job_id: Optional[UUID] = None
    ) -> Tuple[List[MatchResultInternal], Dict[str, Any]]:
        """
        Match products from Site A to Site B.

        Args:
            site_a_products: List of source products
            site_b_products: List of target products
            job_id: Optional job ID for logging

        Returns:
            Tuple of (match results, statistics)
        """
        self._ensure_loaded()

        logger.info(f"Starting matching: {len(site_a_products)} source products, {len(site_b_products)} target products")

        # Prepare data
        titles_a = [p.title for p in site_a_products]
        titles_b = [p.title for p in site_b_products]

        # Generate embeddings
        logger.info("Generating embeddings for source products...")
        embeddings_a = self._matcher.encode(titles_a) if hasattr(self._matcher, 'encode') else self._matcher.model.encode(
            titles_a, show_progress_bar=False, batch_size=32, normalize_embeddings=True
        )

        logger.info("Generating embeddings for target products...")
        embeddings_b = self._matcher.encode(titles_b) if hasattr(self._matcher, 'encode') else self._matcher.model.encode(
            titles_b, show_progress_bar=False, batch_size=32, normalize_embeddings=True
        )

        # Compute similarity matrix
        from sklearn.metrics.pairwise import cosine_similarity
        logger.info("Computing similarity matrix...")
        similarity_matrix = cosine_similarity(embeddings_a, embeddings_b)

        # Find matches
        results = []
        scores = []

        for i, prod_a in enumerate(site_a_products):
            # Get top-k candidates
            semantic_sims = similarity_matrix[i]
            top_indices = np.argsort(semantic_sims)[-self.top_k:][::-1]

            # Compute multi-signal scores
            best_score = 0
            best_index = top_indices[0]
            best_explanation = ""

            for j in top_indices:
                prod_b = site_b_products[j]
                semantic_sim = semantic_sims[j]

                # Multi-signal scoring
                score = self._compute_multi_signal_score(
                    prod_a, prod_b, semantic_sim
                )

                if score > best_score:
                    best_score = score
                    best_index = j
                    best_explanation = self._generate_explanation(
                        prod_a, prod_b, score, semantic_sim
                    )

            # Determine confidence tier
            confidence_tier = self._get_confidence_tier(best_score)
            needs_review = confidence_tier in [
                ConfidenceTier.LIKELY_MATCH,
                ConfidenceTier.MANUAL_REVIEW,
                ConfidenceTier.NO_MATCH
            ]

            results.append(MatchResultInternal(
                source_index=i,
                target_index=best_index,
                score=best_score,
                confidence_tier=confidence_tier,
                explanation=best_explanation,
                needs_review=needs_review
            ))
            scores.append(best_score)

        # Calculate statistics
        stats = self._calculate_statistics(results, scores)
        logger.info(f"Matching complete. {len(results)} matches found.")

        return results, stats

    def _compute_multi_signal_score(
        self,
        prod_a: ProductBase,
        prod_b: ProductBase,
        semantic_sim: float
    ) -> float:
        """Compute weighted multi-signal match score."""
        # 60% semantic similarity
        semantic_score = semantic_sim * 0.60

        # 25% token overlap (Jaccard)
        tokens_a = self._text_processor.tokenize(prod_a.title)
        tokens_b = self._text_processor.tokenize(prod_b.title)
        token_score = self._jaccard_similarity(tokens_a, tokens_b) * 0.25

        # 15% attribute match
        attr_score = self._attribute_match_score(prod_a, prod_b) * 0.15

        return semantic_score + token_score + attr_score

    def _jaccard_similarity(self, set1: set, set2: set) -> float:
        """Compute Jaccard similarity between token sets."""
        if not set1 or not set2:
            return 0.0
        intersection = len(set1 & set2)
        union = len(set1 | set2)
        return intersection / union if union > 0 else 0.0

    def _attribute_match_score(self, prod_a: ProductBase, prod_b: ProductBase) -> float:
        """Calculate attribute matching score."""
        score = 0.0
        total = 0

        # Brand match
        if prod_a.brand and prod_b.brand:
            total += 1
            brand_a = prod_a.brand.lower().strip()
            brand_b = prod_b.brand.lower().strip()
            if brand_a == brand_b:
                score += 1.0
            elif brand_a in brand_b or brand_b in brand_a:
                score += 0.5

        # Category match
        if prod_a.category and prod_b.category:
            total += 1
            cat_a = prod_a.category.lower().strip()
            cat_b = prod_b.category.lower().strip()
            if cat_a == cat_b:
                score += 1.0
            elif cat_a in cat_b or cat_b in cat_a:
                score += 0.5

        return score / total if total > 0 else 0.0

    def _get_confidence_tier(self, score: float) -> ConfidenceTier:
        """Map score to confidence tier."""
        if score >= 0.95:
            return ConfidenceTier.EXACT_MATCH
        if score >= 0.90:
            return ConfidenceTier.HIGH_CONFIDENCE
        if score >= 0.80:
            return ConfidenceTier.GOOD_MATCH
        if score >= 0.70:
            return ConfidenceTier.LIKELY_MATCH
        if score >= 0.50:
            return ConfidenceTier.MANUAL_REVIEW
        return ConfidenceTier.NO_MATCH

    def _generate_explanation(
        self,
        prod_a: ProductBase,
        prod_b: ProductBase,
        score: float,
        semantic_sim: float
    ) -> str:
        """Generate human-readable explanation for match."""
        if score >= 0.95:
            return ""  # No explanation needed for exact matches

        reasons = []

        # Check brand
        if prod_a.brand and prod_b.brand:
            brand_a = prod_a.brand.lower().strip()
            brand_b = prod_b.brand.lower().strip()
            if brand_a != brand_b:
                reasons.append(f"Brand mismatch: {prod_a.brand} vs {prod_b.brand}")

        # Check semantic similarity
        if semantic_sim < 0.90:
            reasons.append(f"Semantic similarity: {semantic_sim:.2f}")

        # Check token overlap
        tokens_a = self._text_processor.tokenize(prod_a.title)
        tokens_b = self._text_processor.tokenize(prod_b.title)
        jaccard = self._jaccard_similarity(tokens_a, tokens_b)
        if jaccard < 0.70:
            reasons.append(f"Low text overlap: {jaccard:.2f}")

        if not reasons:
            reasons.append("Minor variations in product details")

        return "; ".join(reasons)

    def _calculate_statistics(
        self,
        results: List[MatchResultInternal],
        scores: List[float]
    ) -> Dict[str, Any]:
        """Calculate matching statistics."""
        confidence_dist = {}
        needs_review_count = 0

        for r in results:
            tier = r.confidence_tier.value
            confidence_dist[tier] = confidence_dist.get(tier, 0) + 1
            if r.needs_review:
                needs_review_count += 1

        return {
            "total_matches": len(results),
            "confidence_distribution": confidence_dist,
            "avg_score": float(np.mean(scores)) if scores else 0,
            "median_score": float(np.median(scores)) if scores else 0,
            "min_score": float(np.min(scores)) if scores else 0,
            "max_score": float(np.max(scores)) if scores else 0,
            "std_score": float(np.std(scores)) if scores else 0,
            "needs_review_count": needs_review_count,
            "high_confidence_count": sum(1 for r in results if r.score >= 0.80)
        }


# Global instance for dependency injection
_matcher_service: Optional[MatcherService] = None


def get_matcher_service(
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    top_k: int = 25
) -> MatcherService:
    """Get or create matcher service instance."""
    global _matcher_service
    if _matcher_service is None:
        _matcher_service = MatcherService(model_name=model_name, top_k=top_k)
    return _matcher_service
