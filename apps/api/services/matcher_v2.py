"""
Multi-Candidate Matching Engine for URL-to-URL Product Matching
Uses pgvector for O(1) similarity search at scale.
Returns top 5 candidates per product or marks as NO MATCH.

Phase 6 Enhancements:
- AI validation for borderline matches (70-94% range)
- Image similarity as optional visual signal (15% weight when enabled)
"""

import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Tuple
from uuid import UUID
import numpy as np

from sentence_transformers import SentenceTransformer

from models.schemas import Product, ConfidenceTier, Site
from services.supabase import get_supabase_service

# Phase 6: AI validation and image matching imports
from services.ai_validator import (
    AIValidator,
    AIValidationResponse,
    ValidationResultType,
    get_ai_validator
)
from services.image_matcher import (
    ImageMatcher,
    ImageSimilarityResult,
    get_image_matcher
)

logger = logging.getLogger(__name__)


@dataclass
class MatcherConfig:
    """Configuration for Phase 6 enhanced matching."""
    # AI validation settings
    enable_ai_validation: bool = False
    ai_validation_min_score: float = 0.70
    ai_validation_max_score: float = 0.94

    # Image matching settings
    enable_image_matching: bool = False

    # Scoring weights (must sum to 1.0)
    # Standard: 60% semantic + 25% token + 15% attributes
    # With images: 50% semantic + 20% token + 15% attributes + 15% visual
    semantic_weight: float = 0.60
    token_weight: float = 0.25
    attribute_weight: float = 0.15
    visual_weight: float = 0.0  # Set to 0.15 when image matching enabled


@dataclass
class CandidateMatch:
    """A potential match candidate with score."""
    product_id: UUID
    title: str
    url: str
    score: float
    brand: str = ""
    category: str = ""
    # Phase 6: Additional fields
    image_url: str = ""
    ai_validated: bool = False
    ai_adjusted_score: Optional[float] = None
    ai_reasoning: str = ""


@dataclass
class MatchResult:
    """Result of matching a single product."""
    source_product: Product
    best_match: Optional[CandidateMatch]
    top_5_candidates: List[CandidateMatch]
    confidence_tier: ConfidenceTier
    explanation: str
    is_no_match: bool
    no_match_reason: str = ""
    # Phase 6: AI validation metadata
    ai_validated: bool = False
    ai_validation_result: Optional[str] = None
    original_score: Optional[float] = None


class MultiCandidateMatcher:
    """
    Multi-candidate matching engine optimized for scale.
    Uses pgvector for O(1) similarity search.

    Scoring Formula (standard):
        Final Score = (0.60 × Semantic) + (0.25 × Token Overlap) + (0.15 × Attributes)

    Scoring Formula (with visual signal - Phase 6):
        Final Score = (0.50 × Semantic) + (0.20 × Token) + (0.15 × Attr) + (0.15 × Visual)

    Phase 6 Enhancements:
        - AI validation for borderline matches (70-94% range)
        - Optional image similarity scoring
        - Metrics tracking for AI-validated matches

    Matching Rules:
        - 95-100%: Exact Match (single best match)
        - 90-94%: High Confidence (top 5 candidates)
        - 80-89%: Good Match (top 5 candidates)
        - 70-79%: Likely Match (top 5, needs review)
        - 50-69%: Manual Review (top 5, needs review)
        - <50%: NO MATCH (marked, not shown)
    """

    # Default scoring weights (standard - no visual)
    SEMANTIC_WEIGHT = 0.60
    TOKEN_WEIGHT = 0.25
    ATTRIBUTE_WEIGHT = 0.15
    VISUAL_WEIGHT = 0.0

    # Scoring weights with visual signal enabled
    SEMANTIC_WEIGHT_WITH_VISUAL = 0.50
    TOKEN_WEIGHT_WITH_VISUAL = 0.20
    ATTRIBUTE_WEIGHT_WITH_VISUAL = 0.15
    VISUAL_WEIGHT_WITH_VISUAL = 0.15

    # Thresholds
    NO_MATCH_THRESHOLD = 0.50
    TOP_CANDIDATES = 5
    PRE_FILTER_LIMIT = 100  # pgvector candidates before full scoring

    # AI validation range
    AI_VALIDATION_MIN_SCORE = 0.70
    AI_VALIDATION_MAX_SCORE = 0.94

    def __init__(
        self,
        model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
        config: Optional[MatcherConfig] = None
    ):
        """
        Initialize matcher with sentence-transformers model.

        Args:
            model_name: The sentence-transformer model to use for embeddings
            config: Optional Phase 6 configuration for AI validation and image matching
        """
        self.model_name = model_name
        self._model: Optional[SentenceTransformer] = None
        self.supabase = get_supabase_service()

        # Phase 6: Configuration
        self.config = config or MatcherConfig()

        # Phase 6: Initialize AI validator and image matcher if enabled
        self._ai_validator: Optional[AIValidator] = None
        self._image_matcher: Optional[ImageMatcher] = None

        if self.config.enable_ai_validation:
            self._ai_validator = get_ai_validator(enabled=True)
            logger.info("AI validation enabled for borderline matches (70-94%)")

        if self.config.enable_image_matching:
            self._image_matcher = get_image_matcher()
            if self._image_matcher.is_available:
                # Adjust weights for visual signal
                self.SEMANTIC_WEIGHT = self.SEMANTIC_WEIGHT_WITH_VISUAL
                self.TOKEN_WEIGHT = self.TOKEN_WEIGHT_WITH_VISUAL
                self.ATTRIBUTE_WEIGHT = self.ATTRIBUTE_WEIGHT_WITH_VISUAL
                self.VISUAL_WEIGHT = self.VISUAL_WEIGHT_WITH_VISUAL
                logger.info("Image matching enabled (15% visual weight)")
            else:
                logger.warning("Image matching requested but not available (missing dependencies)")
                self._image_matcher = None

        # Phase 6: Metrics tracking
        self.metrics = {
            "total_matches": 0,
            "ai_validations": 0,
            "ai_confirmed": 0,
            "ai_rejected": 0,
            "ai_score_adjustments": 0,
            "image_comparisons": 0
        }

        logger.info(f"MultiCandidateMatcher initialized with model: {model_name}")

    @property
    def model(self) -> SentenceTransformer:
        """Lazy load the model."""
        if self._model is None:
            logger.info(f"Loading model: {self.model_name}")
            self._model = SentenceTransformer(self.model_name)
            logger.info("Model loaded successfully")
        return self._model

    def _ensure_loaded(self):
        """Ensure model is loaded (used for preloading on startup)."""
        _ = self.model

    def generate_embedding(self, text: str) -> np.ndarray:
        """Generate normalized embedding for text."""
        return self.model.encode(
            text,
            normalize_embeddings=True,
            show_progress_bar=False
        )

    async def generate_embeddings_batch(
        self,
        products: List[Product]
    ) -> Dict[UUID, np.ndarray]:
        """Generate embeddings for multiple products."""
        if not products:
            return {}

        texts = [p.title for p in products]
        embeddings = self.model.encode(
            texts,
            normalize_embeddings=True,
            show_progress_bar=True,
            batch_size=32
        )
        return {p.id: emb for p, emb in zip(products, embeddings)}

    async def store_embeddings(
        self,
        embeddings: Dict[UUID, np.ndarray]
    ) -> int:
        """Store embeddings in database for pgvector search."""
        stored = 0
        for product_id, embedding in embeddings.items():
            try:
                emb_list = embedding.tolist()
                self.supabase.client.rpc('url_store_embedding', {
                    'p_product_id': str(product_id),
                    'p_embedding': emb_list
                }).execute()
                stored += 1
            except Exception as e:
                logger.error(f"Failed to store embedding for {product_id}: {e}")
        return stored

    async def search_candidates(
        self,
        embedding: np.ndarray,
        job_id: UUID,
        site: Site,
        limit: int = 100
    ) -> List[Tuple[dict, float]]:
        """Use pgvector to find top candidates by similarity."""
        try:
            result = self.supabase.client.rpc('search_similar_products', {
                'p_embedding': embedding.tolist(),
                'p_job_id': str(job_id),
                'p_site': site.value,
                'p_limit': limit
            }).execute()

            candidates = []
            for row in result.data or []:
                candidates.append((row, row.get('similarity', 0)))

            return candidates
        except Exception as e:
            logger.error(f"pgvector search failed: {e}")
            return []

    async def match_product(
        self,
        source: Product,
        job_id: UUID,
        target_site: Site = Site.SITE_B
    ) -> MatchResult:
        """
        Match single product against catalog.
        Returns top 5 candidates or NO MATCH.

        Phase 6 Enhancements:
        - Optional image similarity scoring (15% weight when enabled)
        - AI validation for borderline matches (70-94% range)
        """
        self.metrics["total_matches"] += 1

        # Generate embedding for source product
        source_embedding = self.generate_embedding(source.title)

        # pgvector search for top candidates
        candidates = await self.search_candidates(
            source_embedding, job_id, target_site, self.PRE_FILTER_LIMIT
        )

        if not candidates:
            return MatchResult(
                source_product=source,
                best_match=None,
                top_5_candidates=[],
                confidence_tier=ConfidenceTier.NO_MATCH,
                explanation="No products found in catalog",
                is_no_match=True,
                no_match_reason="Empty catalog or no embeddings generated"
            )

        # Multi-signal scoring on candidates
        scored_candidates = []
        for row, semantic_sim in candidates:
            # Phase 6: Get image similarity if enabled
            visual_sim = None
            if self._image_matcher and self._image_matcher.is_available:
                source_image = getattr(source, 'image_url', None) or source.metadata.get('image_url', '') if hasattr(source, 'metadata') else ''
                target_image = row.get('image_url') or row.get('metadata', {}).get('image_url', '')

                if source_image and target_image:
                    try:
                        image_result = await self._image_matcher.compare_images(
                            source_image, target_image
                        )
                        if image_result.success:
                            visual_sim = image_result.combined_score
                            self.metrics["image_comparisons"] += 1
                    except Exception as e:
                        logger.warning(f"Image comparison failed: {e}")

            score = self._compute_multi_signal_score(
                source, row, semantic_sim, visual_sim
            )
            scored_candidates.append(CandidateMatch(
                product_id=UUID(row['id']),
                title=row['title'],
                url=row['url'],
                score=score,
                brand=row.get('brand') or "",
                category=row.get('category') or "",
                image_url=row.get('image_url') or ""
            ))

        # Sort by score descending
        scored_candidates.sort(key=lambda x: x.score, reverse=True)

        # Apply matching rules
        best = scored_candidates[0]
        top_5 = scored_candidates[:self.TOP_CANDIDATES]

        # Check for NO MATCH
        if best.score < self.NO_MATCH_THRESHOLD:
            return MatchResult(
                source_product=source,
                best_match=None,
                top_5_candidates=[],
                confidence_tier=ConfidenceTier.NO_MATCH,
                explanation=f"Best match scored {best.score:.0%}, below 50% threshold",
                is_no_match=True,
                no_match_reason=f"Best candidate: {best.title} ({best.score:.0%})"
            )

        # Phase 6: AI validation for borderline matches (70-94%)
        ai_validated = False
        ai_validation_result = None
        original_score = best.score

        if self._should_ai_validate(best.score):
            ai_response = await self._run_ai_validation(source, best)
            if ai_response and ai_response.result != ValidationResultType.SKIPPED:
                ai_validated = True
                ai_validation_result = ai_response.result.value
                self.metrics["ai_validations"] += 1

                # Apply score adjustment if AI provides one
                if ai_response.adjusted_score is not None:
                    adjusted_score = ai_response.adjusted_score
                    if adjusted_score != best.score:
                        logger.info(
                            f"AI validation adjusted score: {best.score:.0%} -> {adjusted_score:.0%} "
                            f"({ai_response.result.value})"
                        )
                        best.ai_validated = True
                        best.ai_adjusted_score = adjusted_score
                        best.ai_reasoning = ai_response.reasoning
                        best.score = adjusted_score  # Update the score
                        self.metrics["ai_score_adjustments"] += 1

                        # Update metrics
                        if ai_response.result == ValidationResultType.CONFIRMED:
                            self.metrics["ai_confirmed"] += 1
                        elif ai_response.result == ValidationResultType.REJECTED:
                            self.metrics["ai_rejected"] += 1

                        # Re-sort candidates if score changed significantly
                        scored_candidates.sort(key=lambda x: x.score, reverse=True)
                        best = scored_candidates[0]
                        top_5 = scored_candidates[:self.TOP_CANDIDATES]

        # Determine confidence tier (may have changed after AI validation)
        confidence = self._get_confidence_tier(best.score)
        explanation = self._generate_explanation(source, best, confidence)

        # Add AI validation info to explanation if applicable
        if ai_validated and best.ai_reasoning:
            explanation = f"{explanation}; AI: {best.ai_reasoning}" if explanation else f"AI: {best.ai_reasoning}"

        return MatchResult(
            source_product=source,
            best_match=best,
            top_5_candidates=top_5,
            confidence_tier=confidence,
            explanation=explanation,
            is_no_match=False,
            ai_validated=ai_validated,
            ai_validation_result=ai_validation_result,
            original_score=original_score if ai_validated else None
        )

    def _should_ai_validate(self, score: float) -> bool:
        """
        Check if score is in the borderline range for AI validation.

        Args:
            score: Current matching score (0-1)

        Returns:
            True if AI validation should be run
        """
        if not self._ai_validator or not self.config.enable_ai_validation:
            return False

        return (
            self.AI_VALIDATION_MIN_SCORE <= score <= self.AI_VALIDATION_MAX_SCORE
        )

    async def _run_ai_validation(
        self,
        source: Product,
        candidate: CandidateMatch
    ) -> Optional[AIValidationResponse]:
        """
        Run AI validation on a match candidate.

        Args:
            source: Source product
            candidate: Best match candidate

        Returns:
            AIValidationResponse or None if validation failed
        """
        if not self._ai_validator:
            return None

        try:
            response = await self._ai_validator.validate_match(
                source_title=source.title,
                target_title=candidate.title,
                source_brand=source.brand,
                target_brand=candidate.brand,
                current_score=candidate.score,
                additional_context={
                    "source_category": source.category or "",
                    "target_category": candidate.category or ""
                }
            )
            return response
        except Exception as e:
            logger.error(f"AI validation failed: {e}")
            return None

    def get_matching_metrics(self) -> Dict[str, int]:
        """Get Phase 6 matching metrics."""
        return self.metrics.copy()

    def reset_metrics(self):
        """Reset Phase 6 metrics."""
        self.metrics = {
            "total_matches": 0,
            "ai_validations": 0,
            "ai_confirmed": 0,
            "ai_rejected": 0,
            "ai_score_adjustments": 0,
            "image_comparisons": 0
        }

    def _compute_multi_signal_score(
        self,
        source: Product,
        target: dict,
        semantic_sim: float,
        visual_sim: Optional[float] = None
    ) -> float:
        """
        Weighted multi-signal scoring.

        Standard Formula: (0.60 × Semantic) + (0.25 × Token) + (0.15 × Attributes)
        With Visual:      (0.50 × Semantic) + (0.20 × Token) + (0.15 × Attr) + (0.15 × Visual)

        Args:
            source: Source product
            target: Target product dict from database
            semantic_sim: Semantic similarity from embeddings
            visual_sim: Optional visual similarity from image matching (0-1)

        Returns:
            Combined multi-signal score (0-1)
        """
        # Semantic similarity
        semantic_score = semantic_sim * self.SEMANTIC_WEIGHT

        # Token overlap - Jaccard similarity
        source_tokens = set(source.title.lower().split())
        target_tokens = set(target.get('title', '').lower().split())
        intersection = len(source_tokens & target_tokens)
        union = len(source_tokens | target_tokens)
        token_score = (intersection / union if union else 0) * self.TOKEN_WEIGHT

        # Attribute matching
        attr_score = self._attribute_match(source, target) * self.ATTRIBUTE_WEIGHT

        # Phase 6: Visual similarity (only when enabled and available)
        visual_score = 0.0
        if visual_sim is not None and self.VISUAL_WEIGHT > 0:
            visual_score = visual_sim * self.VISUAL_WEIGHT

        return semantic_score + token_score + attr_score + visual_score

    def _attribute_match(self, source: Product, target: dict) -> float:
        """Compare product attributes (brand, category)."""
        score = 0.0
        checks = 0

        source_brand = (source.brand or "").lower().strip()
        target_brand = (target.get('brand') or "").lower().strip()

        if source_brand and target_brand:
            checks += 1
            if source_brand == target_brand:
                score += 1.0
            elif source_brand in target_brand or target_brand in source_brand:
                score += 0.5

        source_cat = (source.category or "").lower().strip()
        target_cat = (target.get('category') or "").lower().strip()

        if source_cat and target_cat:
            checks += 1
            if source_cat == target_cat:
                score += 1.0

        return score / checks if checks else 0.0

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
        source: Product,
        best: CandidateMatch,
        confidence: ConfidenceTier
    ) -> str:
        """Generate human-readable explanation for match."""
        if confidence == ConfidenceTier.EXACT_MATCH:
            return ""

        reasons = []

        # Brand comparison
        source_brand = (source.brand or "").strip()
        if source_brand and best.brand:
            if source_brand.lower() != best.brand.lower():
                reasons.append(f"Brand: {source_brand} → {best.brand}")

        # Score explanation
        if best.score < 0.90:
            reasons.append(f"Score: {best.score:.0%}")

        return "; ".join(reasons) if reasons else "Minor variations detected"


# Global instance for dependency injection
_matcher_service: Optional[MultiCandidateMatcher] = None


def get_matcher_v2_service(
    config: Optional[MatcherConfig] = None,
    reset: bool = False
) -> MultiCandidateMatcher:
    """
    Get or create MultiCandidateMatcher service instance.

    Args:
        config: Optional Phase 6 configuration. Only used when creating new instance.
        reset: If True, force creation of new instance with given config.

    Returns:
        The singleton MultiCandidateMatcher instance

    Example:
        # Standard usage (backward compatible)
        matcher = get_matcher_v2_service()

        # With Phase 6 features enabled
        config = MatcherConfig(
            enable_ai_validation=True,
            enable_image_matching=True
        )
        matcher = get_matcher_v2_service(config=config, reset=True)
    """
    global _matcher_service

    if reset or _matcher_service is None:
        _matcher_service = MultiCandidateMatcher(config=config)

    return _matcher_service
