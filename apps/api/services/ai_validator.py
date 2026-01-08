"""
AI Validator Service for URL-to-URL Product Matching
Uses Claude/LLM to validate borderline matches (70-90% score range).

Phase 6 Enhancement: AI-powered validation for matches in the borderline range
to improve accuracy and reduce false positives/negatives.
"""

import json
import logging
import os
from dataclasses import dataclass
from typing import Optional, Dict, Any
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationResultType(Enum):
    """Type of AI validation result."""
    CONFIRMED = "confirmed"      # AI confirms the match
    REJECTED = "rejected"        # AI rejects the match
    UNCERTAIN = "uncertain"      # AI is uncertain
    SKIPPED = "skipped"          # Validation was skipped (no API key, etc.)


@dataclass
class ValidationResult:
    """Result of AI validation (dataclass version for Phase 6)."""
    is_same_product: bool
    confidence: float
    adjusted_score: float
    reasoning: str
    validated: bool = True


@dataclass
class AIValidationResponse:
    """Response from AI validation (legacy compatibility)."""
    result: ValidationResultType
    confidence: float           # 0.0 to 1.0
    reasoning: str
    adjusted_score: Optional[float] = None
    error: Optional[str] = None


class AIValidator:
    """
    AI-powered validation for borderline product matches.

    Uses LLM to analyze product titles and determine if they're the same product.
    Validates scores in the 50-94% range, prioritizing 70-90% (borderline cases).

    Validation Rules:
        - Skip validation for score >= 95% (clearly exact match)
        - Skip validation for score < 50% (clearly no match)
        - Prioritize validation for 70-90% range (borderline cases)

    Cost Tracking:
        - Uses Claude 3 Haiku: ~$0.25/1M input tokens, ~$1.25/1M output tokens
        - Average validation: ~300 input tokens, ~100 output tokens
        - Estimated cost per validation: ~$0.0002
    """

    # Score range for AI validation
    MIN_SCORE_FOR_VALIDATION = 0.50   # Don't validate below 50%
    MAX_SCORE_FOR_VALIDATION = 0.94   # Don't validate above 94%
    OPTIMAL_RANGE_MIN = 0.70          # Prioritize 70-90% range
    OPTIMAL_RANGE_MAX = 0.90

    # Score adjustments
    CONFIRMED_BOOST = 0.08      # Add to score if AI confirms
    REJECTED_PENALTY = -0.15    # Subtract from score if AI rejects

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "claude-3-haiku-20240307",
        enabled: bool = True
    ):
        """
        Initialize AI Validator.

        Args:
            api_key: API key for the LLM provider. If None, reads from env.
            model: Model to use for validation.
            enabled: Whether AI validation is enabled.
        """
        self.api_key = api_key or os.getenv("ANTHROPIC_API_KEY") or os.getenv("OPENAI_API_KEY")
        self.model = model
        self.enabled = enabled and self.api_key is not None

        # Lazy-loaded client
        self._client = None

        # Metrics tracking
        self.metrics = {
            "total_validations": 0,
            "confirmed": 0,
            "rejected": 0,
            "uncertain": 0,
            "skipped": 0,
            "errors": 0
        }

        # Cost tracking
        self._total_tokens_used = 0

        if not self.enabled:
            logger.warning(
                "AI Validator disabled - no API key configured. "
                "Set ANTHROPIC_API_KEY or OPENAI_API_KEY to enable."
            )
        else:
            logger.info(f"AI Validator initialized with model: {model}")

    @property
    def client(self):
        """Lazy-load Anthropic client."""
        if self._client is None and self.enabled:
            if "claude" in self.model.lower() or "anthropic" in self.model.lower():
                try:
                    import anthropic
                    self._client = anthropic.AsyncAnthropic(api_key=self.api_key)
                    logger.info("Anthropic async client initialized successfully")
                except ImportError:
                    logger.warning(
                        "anthropic package not installed. "
                        "Install with: pip install anthropic>=0.18.0"
                    )
        return self._client

    def should_validate(self, score: float) -> bool:
        """
        Determine if a match should be AI validated.

        Args:
            score: Current similarity score (0-1)

        Returns:
            True if the match should be validated by AI
        """
        if not self.enabled:
            return False

        # Don't validate very high scores (clearly exact match)
        if score >= 0.95:
            return False

        # Don't validate very low scores (clearly no match)
        if score < self.MIN_SCORE_FOR_VALIDATION:
            return False

        # Prioritize borderline range (70-90%) but accept 50-94%
        return self.MIN_SCORE_FOR_VALIDATION <= score <= self.MAX_SCORE_FOR_VALIDATION

    async def validate_match(
        self,
        source_title: str,
        target_title: str,
        source_brand: Optional[str] = None,
        target_brand: Optional[str] = None,
        current_score: float = 0.0,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> AIValidationResponse:
        """
        Validate a product match using AI.

        Args:
            source_title: Title of the source product
            target_title: Title of the target product
            source_brand: Brand of source product (optional)
            target_brand: Brand of target product (optional)
            current_score: Current matching score
            additional_context: Any additional context for the AI

        Returns:
            AIValidationResponse with result and adjusted score
        """
        if not self.enabled:
            self.metrics["skipped"] += 1
            return AIValidationResponse(
                result=ValidationResultType.SKIPPED,
                confidence=0.0,
                reasoning="AI validation disabled"
            )

        if not self.should_validate(current_score):
            self.metrics["skipped"] += 1
            return AIValidationResponse(
                result=ValidationResultType.SKIPPED,
                confidence=0.0,
                reasoning=f"Score {current_score:.0%} outside validation range"
            )

        self.metrics["total_validations"] += 1

        try:
            # Build the prompt
            prompt = self._build_validation_prompt(
                source_title, target_title,
                source_brand, target_brand,
                additional_context
            )

            # Call the LLM
            response = await self._call_llm(prompt)

            # Parse the response
            result = self._parse_response(response)

            # Calculate adjusted score
            adjusted_score = self._adjust_score(current_score, result)
            result.adjusted_score = adjusted_score

            # Update metrics
            self.metrics[result.result.value] += 1

            logger.info(
                f"AI Validation: {result.result.value} | "
                f"Score: {current_score:.0%} -> {adjusted_score:.0%} | "
                f"Confidence: {result.confidence:.0%}"
            )

            return result

        except Exception as e:
            self.metrics["errors"] += 1
            logger.error(f"AI validation error: {e}")
            return AIValidationResponse(
                result=ValidationResultType.SKIPPED,
                confidence=0.0,
                reasoning="Validation error",
                error=str(e)
            )

    def _build_validation_prompt(
        self,
        source_title: str,
        target_title: str,
        source_brand: Optional[str],
        target_brand: Optional[str],
        source_category: str = "",
        target_category: str = "",
        source_price: Optional[float] = None,
        target_price: Optional[float] = None,
        additional_context: Optional[Dict[str, Any]] = None
    ) -> str:
        """Build the validation prompt for the LLM."""
        # Build brand info
        brand_info = ""
        if source_brand or target_brand:
            brand_info = f"\nSource Brand: {source_brand or 'Unknown'}\nTarget Brand: {target_brand or 'Unknown'}"

        # Build category info
        category_info = ""
        if source_category or target_category:
            category_info = f"\nCategories: {source_category or 'N/A'} vs {target_category or 'N/A'}"

        # Build price info
        price_info = ""
        if source_price and target_price:
            price_diff = abs(source_price - target_price) / max(source_price, target_price) * 100
            price_info = f"\nPrice comparison: {source_price:.0f} vs {target_price:.0f} ({price_diff:.0f}% difference)"

        # Build additional context
        context_info = ""
        if additional_context:
            context_info = f"\nAdditional Context: {additional_context}"

        return f"""You are a product matching expert. Determine if these two product listings refer to the SAME physical product.

Product A: {source_title}
Product B: {target_title}{brand_info}{category_info}{price_info}{context_info}

Consider:
1. Brand name match (must be same brand)
2. Product name/line match
3. Variant details (shade, size, color, etc.)
4. Minor wording differences are OK if same product

Respond in this exact format:
RESULT: [CONFIRMED/REJECTED/UNCERTAIN]
CONFIDENCE: [0.0-1.0]
REASONING: [Brief explanation]

Examples of CONFIRMED: Same product, different wording
Examples of REJECTED: Different brands, different variants, different products
Examples of UNCERTAIN: Can't determine from titles alone"""

    async def _call_llm(self, prompt: str) -> str:
        """Call the LLM API. Override this for different providers."""
        # Try Anthropic first, then OpenAI
        if "anthropic" in self.model.lower() or "claude" in self.model.lower():
            return await self._call_anthropic(prompt)
        else:
            return await self._call_openai(prompt)

    async def _call_anthropic(self, prompt: str) -> str:
        """Call Anthropic Claude API with token tracking."""
        try:
            import anthropic

            client = anthropic.AsyncAnthropic(api_key=self.api_key)
            response = await client.messages.create(
                model=self.model,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}]
            )

            # Track token usage for cost monitoring
            if hasattr(response, 'usage'):
                input_tokens = getattr(response.usage, 'input_tokens', 0)
                output_tokens = getattr(response.usage, 'output_tokens', 0)
                self._total_tokens_used += input_tokens + output_tokens
                logger.debug(
                    f"AI validation tokens: {input_tokens} input, "
                    f"{output_tokens} output (total: {self._total_tokens_used})"
                )

            return response.content[0].text
        except ImportError:
            logger.warning("anthropic package not installed, falling back to mock")
            return self._mock_response(prompt)
        except Exception as e:
            logger.error(f"Anthropic API error: {e}")
            raise

    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API."""
        try:
            import openai

            client = openai.AsyncOpenAI(api_key=self.api_key)
            response = await client.chat.completions.create(
                model=self.model,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}]
            )
            return response.choices[0].message.content
        except ImportError:
            logger.warning("openai package not installed, falling back to mock")
            return self._mock_response(prompt)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            raise

    def _mock_response(self, prompt: str) -> str:
        """Mock response for testing when no LLM is available."""
        return """RESULT: UNCERTAIN
CONFIDENCE: 0.5
REASONING: Mock response - LLM not available"""

    def _parse_response(self, response: str) -> AIValidationResponse:
        """Parse LLM response into structured format."""
        lines = response.strip().split("\n")

        result = ValidationResultType.UNCERTAIN
        confidence = 0.5
        reasoning = "Could not parse response"

        for line in lines:
            line = line.strip()
            if line.startswith("RESULT:"):
                result_str = line.replace("RESULT:", "").strip().upper()
                if result_str == "CONFIRMED":
                    result = ValidationResultType.CONFIRMED
                elif result_str == "REJECTED":
                    result = ValidationResultType.REJECTED
                else:
                    result = ValidationResultType.UNCERTAIN
            elif line.startswith("CONFIDENCE:"):
                try:
                    confidence = float(line.replace("CONFIDENCE:", "").strip())
                    confidence = max(0.0, min(1.0, confidence))
                except ValueError:
                    confidence = 0.5
            elif line.startswith("REASONING:"):
                reasoning = line.replace("REASONING:", "").strip()

        return AIValidationResponse(
            result=result,
            confidence=confidence,
            reasoning=reasoning
        )

    def _adjust_score(
        self,
        current_score: float,
        validation: AIValidationResponse
    ) -> float:
        """Adjust the matching score based on AI validation."""
        if validation.result == ValidationResultType.CONFIRMED:
            # Boost score based on AI confidence
            boost = self.CONFIRMED_BOOST * validation.confidence
            return min(1.0, current_score + boost)
        elif validation.result == ValidationResultType.REJECTED:
            # Penalize score based on AI confidence
            penalty = self.REJECTED_PENALTY * validation.confidence
            return max(0.0, current_score + penalty)
        else:
            # Uncertain or skipped - no change
            return current_score

    def get_metrics(self) -> Dict[str, int]:
        """Get validation metrics."""
        return self.metrics.copy()

    def get_usage_stats(self) -> Dict[str, Any]:
        """
        Get usage statistics for cost tracking.

        Returns:
            Dict with total_validations, total_tokens_used, and estimated_cost_usd
        """
        # Cost estimation based on Claude Haiku pricing
        # ~$0.25/1M input tokens, ~$1.25/1M output tokens
        # Average ~$0.50/1M tokens (rough estimate)
        estimated_cost = self._total_tokens_used * 0.0000005

        return {
            "total_validations": self.metrics["total_validations"],
            "total_tokens_used": self._total_tokens_used,
            "estimated_cost_usd": estimated_cost,
            "metrics": self.metrics.copy()
        }

    def reset_metrics(self):
        """Reset metrics counters."""
        self.metrics = {
            "total_validations": 0,
            "confirmed": 0,
            "rejected": 0,
            "uncertain": 0,
            "skipped": 0,
            "errors": 0
        }

    def reset_stats(self):
        """Reset all usage statistics including tokens."""
        self.reset_metrics()
        self._total_tokens_used = 0

    async def validate_match_v2(
        self,
        source_title: str,
        source_brand: str,
        target_title: str,
        target_brand: str,
        current_score: float,
        source_category: str = "",
        target_category: str = "",
        source_price: Optional[float] = None,
        target_price: Optional[float] = None
    ) -> ValidationResult:
        """
        Phase 6 API: Use AI to validate a borderline match.

        This is the new simplified API that returns ValidationResult dataclass.
        Matches the signature specified in Phase 6 requirements.

        Args:
            source_title: Title of source product
            source_brand: Brand of source product
            target_title: Title of target/candidate product
            target_brand: Brand of target product
            current_score: Current similarity score (0-1)
            source_category: Optional category
            target_category: Optional category
            source_price: Optional price
            target_price: Optional price

        Returns:
            ValidationResult with (is_same_product, adjusted_score, reasoning)
        """
        # Check if we should validate
        if not self.should_validate(current_score):
            skip_reason = (
                "Score too high (>=95%)" if current_score >= 0.95
                else "Score too low (<50%)" if current_score < 0.50
                else "Score outside validation range"
            )
            return ValidationResult(
                is_same_product=current_score >= 0.70,
                confidence=current_score,
                adjusted_score=current_score,
                reasoning=f"Skipped: {skip_reason}",
                validated=False
            )

        # Check if validation is enabled
        if not self.enabled:
            return ValidationResult(
                is_same_product=current_score >= 0.70,
                confidence=current_score,
                adjusted_score=current_score,
                reasoning="AI validation unavailable (no API key)",
                validated=False
            )

        self.metrics["total_validations"] += 1

        try:
            # Build the prompt with all available context
            prompt = self._build_validation_prompt(
                source_title=source_title,
                target_title=target_title,
                source_brand=source_brand,
                target_brand=target_brand,
                source_category=source_category,
                target_category=target_category,
                source_price=source_price,
                target_price=target_price
            )

            # Call the LLM
            response_text = await self._call_llm(prompt)

            # Parse the response
            response = self._parse_response(response_text)

            # Calculate adjusted score
            adjusted_score = self._adjust_score(current_score, response)

            # Update metrics
            self.metrics[response.result.value] += 1

            # Determine if it's a match
            is_match = response.result == ValidationResultType.CONFIRMED

            logger.info(
                f"AI Validation (v2): "
                f"'{source_title[:30]}...' vs '{target_title[:30]}...' | "
                f"Original: {current_score:.0%} -> Adjusted: {adjusted_score:.0%} | "
                f"Match: {is_match}"
            )

            return ValidationResult(
                is_same_product=is_match,
                confidence=response.confidence,
                adjusted_score=adjusted_score,
                reasoning=response.reasoning,
                validated=True
            )

        except Exception as e:
            self.metrics["errors"] += 1
            logger.error(f"AI validation error: {e}")
            return ValidationResult(
                is_same_product=current_score >= 0.70,
                confidence=current_score,
                adjusted_score=current_score,
                reasoning=f"Validation error: {str(e)[:50]}",
                validated=False
            )


# Global instance for dependency injection
_ai_validator: Optional[AIValidator] = None


def get_ai_validator(
    api_key: Optional[str] = None,
    enabled: bool = True
) -> AIValidator:
    """Get or create AIValidator service instance."""
    global _ai_validator
    if _ai_validator is None:
        _ai_validator = AIValidator(api_key=api_key, enabled=enabled)
    return _ai_validator
