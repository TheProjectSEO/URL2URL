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
    max_ai_validations_per_job: int = 100

    # Image matching settings
    enable_image_matching: bool = False

    # Scoring weights (must sum to 1.0)
    # Standard: 60% semantic + 25% token + 15% attributes
    # With images: 50% semantic + 20% token + 15% attributes + 15% visual
    semantic_weight: float = 0.60
    token_weight: float = 0.25
    attribute_weight: float = 0.15
    visual_weight: float = 0.0  # Set to 0.15 when image matching enabled
    # Text matching enhancements
    embed_enriched_text: bool = False
    token_norm_v2: bool = False


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

        # Per-job AI validation counter
        self._ai_validations_used: int = 0

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
            "image_comparisons": 0,
            "alias_hits": 0,
            "synonym_hits": 0,
            "variant_hits": 0
        }
        self._image_comparisons_used = 0

        # Load ontologies if enabled
        if getattr(self.config, 'use_brand_ontology', False) or getattr(self.config, 'use_category_ontology', False):
            try:
                import json, os
                base = os.path.dirname(os.path.abspath(__file__))
                root = os.path.abspath(os.path.join(base, '..'))
                if getattr(self.config, 'use_brand_ontology', False):
                    with open(os.path.join(root, 'ontologies', 'brand_aliases.json'), 'r') as f:
                        self._brand_aliases = json.load(f)
                else:
                    self._brand_aliases = {}
                if getattr(self.config, 'use_category_ontology', False):
                    with open(os.path.join(root, 'ontologies', 'category_synonyms.json'), 'r') as f:
                        self._category_synonyms = json.load(f)
                else:
                    self._category_synonyms = {}
            except Exception as e:
                logger.warning(f"Failed to load ontologies: {e}")

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

    def _compose_text(self, p: Product) -> str:
        """Compose text for embeddings based on config (enriched vs title-only)."""
        if self.config and getattr(self.config, 'embed_enriched_text', False):
            parts = [p.title or ""]
            if p.brand:
                parts.append(p.brand)
            if p.category:
                parts.append(p.category)
            # Variant text will be added in a later step
            return " ".join(parts).strip()
        return p.title

    async def generate_embeddings_batch(
        self,
        products: List[Product]
    ) -> Dict[UUID, np.ndarray]:
        """Generate embeddings for multiple products."""
        if not products:
            return {}

        texts = [self._compose_text(p) for p in products]
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
        source_embedding = self.generate_embedding(self._compose_text(source))

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
            if self._image_matcher and self._image_matcher.is_available and getattr(self.config, 'use_ocr_text', False):
                # Respect per-job OCR cap
                cap = max(0, int(getattr(self.config, 'max_image_comparisons_per_job', 500)))
                if self._image_comparisons_used < cap:
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
                                self._image_comparisons_used += 1
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
                # Count a used validation for this job instance
                self._ai_validations_used += 1
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

        # Respect per-job validation cap
        if self._ai_validations_used >= max(0, int(self.config.max_ai_validations_per_job)):
            return False

        # Use configured min/max range
        return (
            self.config.ai_validation_min_score <= score <= self.config.ai_validation_max_score
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
        source_tokens = self._tokenize_text(source.title)
        target_tokens = self._tokenize_text(target.get('title', ''))
        intersection = len(source_tokens & target_tokens)
        union = len(source_tokens | target_tokens)
        token_score = (intersection / union if union else 0) * self.TOKEN_WEIGHT

        # Attribute matching
        attr_score = self._attribute_match(source, target) * self.ATTRIBUTE_WEIGHT

        # Phase 6: Visual similarity (only when enabled and available)
        visual_score = 0.0
        if visual_sim is not None and self.VISUAL_WEIGHT > 0:
            visual_score = visual_sim * self.VISUAL_WEIGHT

        combined = semantic_score + token_score + attr_score + visual_score
        # Brand mismatch penalty when ontologies enabled and brands differ
        if self.config and getattr(self.config, 'use_brand_ontology', False):
            sb = self._canonicalize_brand((source.brand or '').strip()) if hasattr(self, '_canonicalize_brand') else (source.brand or '').strip().lower()
            tb = self._canonicalize_brand((target.get('brand') or '').strip()) if hasattr(self, '_canonicalize_brand') else (target.get('brand') or '').strip().lower()
            if sb and tb and sb != tb:
                combined = max(0.0, combined - 0.05)
        return combined

    def _attribute_match(self, source: Product, target: dict) -> float:
        """Compare product attributes (brand, category, and optional variants)."""
        score = 0.0
        checks = 0

        # Brand (with optional ontology)
        src_brand = (source.brand or "").strip()
        tgt_brand = (target.get('brand') or "").strip()
        src_brand_c = self._canonicalize_brand(src_brand) if hasattr(self, '_canonicalize_brand') else src_brand.lower()
        tgt_brand_c = self._canonicalize_brand(tgt_brand) if hasattr(self, '_canonicalize_brand') else tgt_brand.lower()

        if src_brand_c and tgt_brand_c:
            checks += 1
            if src_brand_c == tgt_brand_c:
                score += 1.0
            elif src_brand_c in tgt_brand_c or tgt_brand_c in src_brand_c:
                score += 0.5

        # Category (with optional ontology)
        src_cat = (source.category or "").lower().strip()
        tgt_cat = (target.get('category') or "").lower().strip()
        if src_cat and tgt_cat:
            checks += 1
            if src_cat == tgt_cat:
                score += 1.0
            elif hasattr(self, '_categories_related') and self._categories_related(src_cat, tgt_cat):
                score += 0.5

        # Variants (optional)
        if self.config and getattr(self.config, 'use_variant_extractor', False):
            src_var = self._extract_variants(source.title) if hasattr(self, '_extract_variants') else {}
            tgt_var = self._extract_variants(target.get('title', '')) if hasattr(self, '_extract_variants') else {}
            var_score = self._compare_variants(src_var, tgt_var) if hasattr(self, '_compare_variants') else None
            if var_score is not None:
                checks += 1
                score += var_score

        return score / checks if checks else 0.0

    def _tokenize_text(self, text: str) -> set:
        """Tokenize text with optional normalization v2."""
        if not text:
            return set()
        raw = text.lower().strip()
        if not (self.config and getattr(self.config, 'token_norm_v2', False)):
            return set(raw.split())
        import re
        # Insert spaces before camelCase / digits boundaries (very light heuristic)
        raw = re.sub(r'([a-z])([A-Z0-9])', r'\1 \2', raw)
        raw = re.sub(r'([0-9])([a-zA-Z])', r'\1 \2', raw)
        # Replace non-alphanumeric with spaces
        raw = re.sub(r'[^a-z0-9]+', ' ', raw)
        # Collapse spaces
        raw = re.sub(r'\s+', ' ', raw).strip()
        tokens = set(raw.split())
        stop = {
            'the','a','an','and','or','for','with','by','of','to','on','in',
            'ml','g','gm','kg','oz','fl','pack','pcs','set','new','free','best',
            'sale','off','price'
        }
        return {t for t in tokens if t not in stop and len(t) >= 2}

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

    # ===== Ontology helpers =====
    def _canonicalize_brand(self, brand: str) -> str:
        b = (brand or '').lower().strip()
        if not b or not hasattr(self, '_brand_aliases'):
            return b
        # Exact canonical key
        if b in self._brand_aliases:
            self.metrics["alias_hits"] += 1
            return b
        for canon, aliases in self._brand_aliases.items():
            if b == canon or b in aliases:
                self.metrics["alias_hits"] += 1
                return canon
        return b

    def _categories_related(self, s: str, t: str) -> bool:
        if not hasattr(self, '_category_synonyms'):
            return False
        s = (s or '').lower().strip()
        t = (t or '').lower().strip()
        if s == t:
            return True
        syns = self._category_synonyms or {}
        if s in syns and t in syns[s]:
            self.metrics["synonym_hits"] += 1
            return True
        if t in syns and s in syns[t]:
            self.metrics["synonym_hits"] += 1
            return True
        return False

    def _extract_variants(self, text: str) -> dict:
        import re
        out = {"size_ml": None, "weight_g": None, "pack": None, "shade": None, "model": None}
        if not text:
            return out
        s = text.lower()
        m = re.search(r"(pack|set)\s*of\s*(\d+)", s)
        if m:
            out["pack"] = int(m.group(2))
        m = re.search(r"(\d+\.?\d*)\s*(ml|l)\b", s)
        if m:
            val = float(m.group(1)); unit = m.group(2)
            out["size_ml"] = val * 1000.0 if unit == 'l' else val
        m = re.search(r"(\d+\.?\d*)\s*(g|kg)\b", s)
        if m:
            val = float(m.group(1)); unit = m.group(2)
            out["weight_g"] = val * 1000.0 if unit == 'kg' else val
        m = re.search(r"(\d+\.?\d*)\s*oz\b", s)
        if m and out["size_ml"] is None:
            out["size_ml"] = float(m.group(1)) * 29.57
        m = re.search(r"\b([a-z]{1,2}\d{2,4}|\d{2,4})\b", s)
        if m:
            out["shade"] = m.group(1)
        m = re.search(r"\b([a-z]{2,3}-?\d{3,4}|iphone\s?\d{1,2}[a-z]?)\b", s)
        if m:
            out["model"] = m.group(1)
        return out

    def _compare_variants(self, a: dict, b: dict) -> Optional[float]:
        if not a and not b:
            return None
        checks, score = 0, 0.0
        def close(x, y, tol):
            return x is not None and y is not None and abs(x - y) <= tol
        if a.get('size_ml') or b.get('size_ml'):
            checks += 1
            if a.get('size_ml') and b.get('size_ml'):
                score += 1.0 if close(a['size_ml'], b['size_ml'], 1.0) else 0.0
        if a.get('weight_g') or b.get('weight_g'):
            checks += 1
            if a.get('weight_g') and b.get('weight_g'):
                score += 1.0 if close(a['weight_g'], b['weight_g'], 1.0) else 0.0
        if a.get('pack') or b.get('pack'):
            checks += 1
            if a.get('pack') and b.get('pack'):
                score += 1.0 if a['pack'] == b['pack'] else 0.0
        if a.get('shade') or b.get('shade'):
            checks += 1
            if a.get('shade') and b.get('shade'):
                score += 1.0 if a['shade'] == b['shade'] else 0.0
        if a.get('model') or b.get('model'):
            checks += 1
            if a.get('model') and b.get('model'):
                score += 1.0 if a['model'] == b['model'] else 0.0
        if checks == 0:
            return None
        if score > 0:
            self.metrics["variant_hits"] += 1
        return score / checks


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
