"""
Image Matcher Service
Provides OCR text extraction and visual similarity for product matching.

This service adds a 15% weight to the overall product matching score by:
1. Extracting text from product images using OCR (pytesseract)
2. Computing visual similarity (CLIP - stubbed for now)

Dependencies:
- pytesseract: Python wrapper for Tesseract OCR
- Pillow: Image processing
- tesseract-ocr: System package (must be installed separately)

Installation:
- Ubuntu/Debian: sudo apt-get install tesseract-ocr
- macOS: brew install tesseract
- Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki
"""

import io
import logging
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class ImageAnalysisResult:
    """Result of image analysis."""
    extracted_text: str = ""
    text_confidence: float = 0.0
    visual_features: Optional[List[float]] = None
    image_hash: str = ""
    success: bool = True
    error: str = ""


@dataclass
class ImageSimilarityResult:
    """Result of image comparison."""
    text_similarity: float = 0.0
    visual_similarity: float = 0.0
    combined_score: float = 0.0
    source_text: str = ""
    target_text: str = ""
    success: bool = True
    error: str = ""


@dataclass
class ImageMatcherConfig:
    """Configuration for image matcher."""
    text_weight: float = 0.60  # Weight for OCR text similarity
    visual_weight: float = 0.40  # Weight for visual/CLIP similarity
    min_text_length: int = 3  # Minimum text length to consider
    request_timeout: float = 30.0  # HTTP request timeout
    max_image_size: int = 10 * 1024 * 1024  # 10MB max image size
    enable_caching: bool = True  # Cache OCR results


class ImageMatcher:
    """
    Image-based product matching using OCR and visual similarity.

    This service provides:
    1. OCR text extraction from product images
    2. Text similarity computation between extracted texts
    3. Visual similarity using CLIP embeddings (stubbed)
    4. Combined image similarity score

    The combined score contributes 15% to the overall product match score:
    Final Score = (0.50 x Semantic) + (0.20 x Token) + (0.15 x Attr) + (0.15 x Image)
    """

    # Default weights for combining signals
    TEXT_WEIGHT = 0.60  # OCR text similarity
    VISUAL_WEIGHT = 0.40  # Visual/CLIP similarity

    def __init__(self, config: Optional[ImageMatcherConfig] = None):
        """
        Initialize the image matcher.

        Args:
            config: Optional configuration for the matcher
        """
        self.config = config or ImageMatcherConfig()
        self._ocr_enabled = False
        self._visual_enabled = False
        self._http_client = None
        self._ocr_cache: Dict[str, ImageAnalysisResult] = {}
        self._initialize()

    def _initialize(self):
        """Initialize available features based on installed packages."""
        # Check for pytesseract
        try:
            import pytesseract
            from PIL import Image

            # Test that tesseract binary is available
            pytesseract.get_tesseract_version()
            self._ocr_enabled = True
            logger.info("OCR enabled (pytesseract + tesseract)")
        except ImportError:
            logger.warning("pytesseract not installed - OCR disabled. Install with: pip install pytesseract Pillow")
        except Exception as e:
            logger.warning(f"Tesseract binary not found - OCR disabled. Error: {e}")
            logger.warning("Install tesseract: brew install tesseract (macOS) or apt-get install tesseract-ocr (Ubuntu)")

        # CLIP is optional and resource-intensive, default to disabled
        # Can be enabled later with proper CLIP integration
        self._visual_enabled = False
        logger.info("Visual similarity disabled (CLIP not configured)")

    @property
    def is_available(self) -> bool:
        """Check if any image features are available."""
        return self._ocr_enabled or self._visual_enabled

    @property
    def ocr_enabled(self) -> bool:
        """Check if OCR is enabled."""
        return self._ocr_enabled

    @property
    def visual_enabled(self) -> bool:
        """Check if visual similarity is enabled."""
        return self._visual_enabled

    def get_status(self) -> Dict[str, Any]:
        """Get the current status of the image matcher."""
        return {
            "available": self.is_available,
            "ocr_enabled": self._ocr_enabled,
            "visual_enabled": self._visual_enabled,
            "text_weight": self.config.text_weight,
            "visual_weight": self.config.visual_weight,
            "cache_size": len(self._ocr_cache) if self.config.enable_caching else 0
        }

    async def _get_http_client(self):
        """Get or create HTTP client for image downloads."""
        if self._http_client is None:
            import httpx
            self._http_client = httpx.AsyncClient(
                timeout=self.config.request_timeout,
                follow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0 (compatible; ProductMatcher/1.0)"
                }
            )
        return self._http_client

    def _compute_image_hash(self, image_bytes: bytes) -> str:
        """Compute a hash for image bytes for caching."""
        return hashlib.md5(image_bytes).hexdigest()

    async def download_image(self, image_url: str) -> Optional[bytes]:
        """
        Download image from URL.

        Args:
            image_url: URL of the image to download

        Returns:
            Image bytes or None if download failed
        """
        if not image_url:
            return None

        try:
            client = await self._get_http_client()
            response = await client.get(image_url)
            response.raise_for_status()

            # Check content length
            content_length = int(response.headers.get('content-length', 0))
            if content_length > self.config.max_image_size:
                logger.warning(f"Image too large ({content_length} bytes): {image_url[:50]}...")
                return None

            image_bytes = response.content

            # Double check actual size
            if len(image_bytes) > self.config.max_image_size:
                logger.warning(f"Image too large ({len(image_bytes)} bytes): {image_url[:50]}...")
                return None

            return image_bytes

        except Exception as e:
            logger.warning(f"Failed to download image {image_url[:50]}...: {e}")
            return None

    async def extract_text_from_image(self, image_url: str) -> ImageAnalysisResult:
        """
        Download image and extract text via OCR.

        Args:
            image_url: URL of the product image

        Returns:
            ImageAnalysisResult with extracted text and confidence
        """
        if not self._ocr_enabled:
            return ImageAnalysisResult(
                success=False,
                error="OCR not available - pytesseract or tesseract not installed"
            )

        if not image_url:
            return ImageAnalysisResult(
                success=False,
                error="No image URL provided"
            )

        try:
            # Download image
            image_bytes = await self.download_image(image_url)
            if not image_bytes:
                return ImageAnalysisResult(
                    success=False,
                    error="Failed to download image"
                )

            # Check cache
            image_hash = self._compute_image_hash(image_bytes)
            if self.config.enable_caching and image_hash in self._ocr_cache:
                logger.debug(f"OCR cache hit for {image_url[:50]}...")
                return self._ocr_cache[image_hash]

            # Import here to avoid startup issues if not installed
            import pytesseract
            from PIL import Image

            # Open image
            img = Image.open(io.BytesIO(image_bytes))

            # Convert to RGB if necessary (handles RGBA, P, L modes)
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            # Extract text with confidence data
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)

            # Combine text and calculate average confidence
            texts = []
            confidences = []
            for i, text in enumerate(data['text']):
                text = text.strip()
                if text and len(text) >= self.config.min_text_length:
                    texts.append(text)
                    conf = data['conf'][i]
                    if conf > 0:  # -1 means no confidence available
                        confidences.append(conf)

            extracted_text = " ".join(texts)
            avg_confidence = sum(confidences) / len(confidences) / 100 if confidences else 0.0

            result = ImageAnalysisResult(
                extracted_text=extracted_text,
                text_confidence=avg_confidence,
                image_hash=image_hash,
                success=True
            )

            # Cache result
            if self.config.enable_caching:
                self._ocr_cache[image_hash] = result

            return result

        except Exception as e:
            logger.error(f"OCR failed for {image_url[:50]}...: {e}")
            return ImageAnalysisResult(
                success=False,
                error=str(e)[:100]
            )

    async def extract_text_from_bytes(self, image_bytes: bytes) -> ImageAnalysisResult:
        """
        Extract text from image bytes directly.

        Args:
            image_bytes: Raw image bytes

        Returns:
            ImageAnalysisResult with extracted text
        """
        if not self._ocr_enabled:
            return ImageAnalysisResult(
                success=False,
                error="OCR not available"
            )

        if not image_bytes:
            return ImageAnalysisResult(
                success=False,
                error="No image bytes provided"
            )

        try:
            # Check cache
            image_hash = self._compute_image_hash(image_bytes)
            if self.config.enable_caching and image_hash in self._ocr_cache:
                return self._ocr_cache[image_hash]

            import pytesseract
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes))
            if img.mode not in ('RGB', 'L'):
                img = img.convert('RGB')

            # Simple text extraction
            text = pytesseract.image_to_string(img)

            result = ImageAnalysisResult(
                extracted_text=text.strip(),
                text_confidence=0.8,  # Assume reasonable confidence for simple extraction
                image_hash=image_hash,
                success=True
            )

            # Cache result
            if self.config.enable_caching:
                self._ocr_cache[image_hash] = result

            return result

        except Exception as e:
            logger.error(f"OCR from bytes failed: {e}")
            return ImageAnalysisResult(
                success=False,
                error=str(e)[:100]
            )

    def compute_text_similarity(self, text1: str, text2: str) -> float:
        """
        Compute similarity between two OCR texts using Jaccard similarity.

        Args:
            text1: First text (from source product image)
            text2: Second text (from target product image)

        Returns:
            Similarity score between 0 and 1
        """
        if not text1 or not text2:
            return 0.0

        # Tokenize and clean
        tokens1 = set(text1.lower().split())
        tokens2 = set(text2.lower().split())

        # Remove common noise words that don't help matching
        noise_words = {
            'the', 'a', 'an', 'and', 'or', 'for', 'with', 'to', 'of', 'in', 'on',
            'ml', 'g', 'oz', 'fl', 'gm', 'kg', 'l', 'pack', 'pcs', 'set',
            'free', 'new', 'best', 'buy', 'sale', 'off', 'price', 'discount'
        }
        tokens1 = tokens1 - noise_words
        tokens2 = tokens2 - noise_words

        # Filter out very short tokens (likely noise)
        tokens1 = {t for t in tokens1 if len(t) >= self.config.min_text_length}
        tokens2 = {t for t in tokens2 if len(t) >= self.config.min_text_length}

        if not tokens1 or not tokens2:
            return 0.0

        intersection = len(tokens1 & tokens2)
        union = len(tokens1 | tokens2)

        return intersection / union if union > 0 else 0.0

    async def compute_visual_similarity(
        self,
        image_url_1: str,
        image_url_2: str
    ) -> float:
        """
        Compute visual similarity between two product images.

        Currently returns 0.5 as CLIP integration is not implemented.
        Future implementation will use CLIP embeddings for visual comparison.

        Args:
            image_url_1: URL of first product image
            image_url_2: URL of second product image

        Returns:
            Similarity score between 0 and 1 (currently always 0.5)
        """
        if not self._visual_enabled:
            # Return neutral score when visual similarity is disabled
            # This prevents the visual component from biasing results
            return 0.5

        # TODO: Implement CLIP-based visual similarity
        # Implementation steps:
        # 1. Download both images
        # 2. Preprocess images for CLIP (resize, normalize)
        # 3. Generate CLIP embeddings using clip-ViT-B-32 or similar
        # 4. Compute cosine similarity between embeddings
        # 5. Return normalized similarity score

        # Example future implementation:
        # image1_bytes = await self.download_image(image_url_1)
        # image2_bytes = await self.download_image(image_url_2)
        # if not image1_bytes or not image2_bytes:
        #     return 0.5
        #
        # from sentence_transformers import SentenceTransformer
        # model = SentenceTransformer('clip-ViT-B-32')
        #
        # img1 = Image.open(io.BytesIO(image1_bytes))
        # img2 = Image.open(io.BytesIO(image2_bytes))
        #
        # emb1 = model.encode(img1)
        # emb2 = model.encode(img2)
        #
        # from sklearn.metrics.pairwise import cosine_similarity
        # return float(cosine_similarity([emb1], [emb2])[0][0])

        return 0.5

    async def compare_images(
        self,
        source_image_url: str,
        target_image_url: str
    ) -> ImageSimilarityResult:
        """
        Compare two product images using OCR and visual similarity.

        This is the main method for image-based matching. It combines:
        1. OCR text similarity (60% weight by default)
        2. Visual/CLIP similarity (40% weight by default)

        The combined score can contribute 15% to the overall product match.

        Args:
            source_image_url: URL of source product image
            target_image_url: URL of target product image

        Returns:
            ImageSimilarityResult with similarity scores and metadata
        """
        if not self.is_available:
            return ImageSimilarityResult(
                success=False,
                error="Image matching not available - no features enabled"
            )

        if not source_image_url or not target_image_url:
            return ImageSimilarityResult(
                success=False,
                error="Missing image URLs"
            )

        try:
            text_sim = 0.0
            visual_sim = 0.5  # Neutral default when visual disabled
            source_text = ""
            target_text = ""

            # OCR comparison
            if self._ocr_enabled:
                source_result = await self.extract_text_from_image(source_image_url)
                target_result = await self.extract_text_from_image(target_image_url)

                if source_result.success and target_result.success:
                    source_text = source_result.extracted_text
                    target_text = target_result.extracted_text
                    text_sim = self.compute_text_similarity(source_text, target_text)
                    logger.debug(f"OCR similarity: {text_sim:.3f}")
                else:
                    # If OCR failed, use neutral text similarity
                    text_sim = 0.5
                    logger.debug("OCR failed for one or both images, using neutral score")

            # Visual comparison
            if self._visual_enabled:
                visual_sim = await self.compute_visual_similarity(
                    source_image_url,
                    target_image_url
                )
                logger.debug(f"Visual similarity: {visual_sim:.3f}")

            # Combine scores using configured weights
            combined = (
                text_sim * self.config.text_weight +
                visual_sim * self.config.visual_weight
            )

            return ImageSimilarityResult(
                text_similarity=text_sim,
                visual_similarity=visual_sim,
                combined_score=combined,
                source_text=source_text[:200] if source_text else "",  # Truncate for response
                target_text=target_text[:200] if target_text else "",
                success=True
            )

        except Exception as e:
            logger.error(f"Image comparison failed: {e}")
            return ImageSimilarityResult(
                success=False,
                error=str(e)[:100]
            )

    def clear_cache(self):
        """Clear the OCR cache."""
        self._ocr_cache.clear()
        logger.info("OCR cache cleared")

    async def close(self):
        """Clean up resources."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
        self._ocr_cache.clear()
        logger.info("ImageMatcher resources cleaned up")


# Singleton instance
_matcher: Optional[ImageMatcher] = None


def get_image_matcher(config: Optional[ImageMatcherConfig] = None) -> ImageMatcher:
    """
    Get the singleton image matcher instance.

    Args:
        config: Optional configuration (only used on first call)

    Returns:
        The singleton ImageMatcher instance
    """
    global _matcher
    if _matcher is None:
        _matcher = ImageMatcher(config)
    return _matcher


async def cleanup_image_matcher():
    """Clean up the singleton image matcher."""
    global _matcher
    if _matcher is not None:
        await _matcher.close()
        _matcher = None
