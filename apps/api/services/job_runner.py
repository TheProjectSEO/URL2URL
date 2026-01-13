"""
Background Job Runner for URL-to-URL Product Matching
Orchestrates the full pipeline: Crawl -> Embed -> Match

Integrates with ProgressTracker for real-time progress reporting
through all stages of the matching pipeline.
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Optional, Callable, Dict, Any
from uuid import UUID

from models.schemas import JobStatus, Site, Product, MatchStatus, ConfidenceTier
from services.supabase import get_supabase_service
from services.matcher_v2 import get_matcher_v2_service, MatchResult
from services.crawler import ProductCrawler
from services.progress import ProgressTracker, ProgressStage, create_progress_tracker
from services.matcher_v2 import MatcherConfig, get_matcher_v2_service

logger = logging.getLogger(__name__)


class JobRunner:
    """
    Background job orchestration with integrated progress tracking.

    Handles: Crawl -> Embed -> Match pipeline with real-time progress updates.

    Pipeline Stages:
    1. crawling_site_a - Crawling source products
    2. crawling_site_b - Crawling target products
    3. generating_embeddings - Creating vector embeddings
    4. matching - Finding product matches
    5. completed - Job finished

    Usage:
        runner = JobRunner()
        stats = await runner.run_job(job_id)
    """

    def __init__(self):
        """Initialize job runner with services."""
        self.supabase = get_supabase_service()
        self.matcher = get_matcher_v2_service()

    async def run_job(
        self,
        job_id: UUID,
        on_progress: Optional[Callable[[str, int, int], None]] = None
    ) -> Dict[str, Any]:
        """
        Execute full matching pipeline with progress tracking.

        Pipeline Steps:
        1. Update status to RUNNING
        2. Get products from both sites
        3. Crawl uncrawled products (if any have pending status)
        4. Generate embeddings for Site B catalog
        5. Match each Site A product against Site B
        6. Store match results with top 5 candidates
        7. Update status to COMPLETED

        Args:
            job_id: The job UUID to run
            on_progress: Optional legacy callback(stage, current, total)

        Returns:
            Dictionary with job completion statistics
        """
        # Create progress tracker for this job
        tracker = create_progress_tracker(job_id)

        try:
            # 1. Update status to RUNNING
            logger.info(f"Starting job {job_id}")
            await self.supabase.update_job_status(
                job_id, JobStatus.RUNNING, started_at=datetime.utcnow()
            )

            # Initialize progress tracking
            await tracker.start_stage(
                ProgressStage.STARTED,
                total=1,
                message="Initializing job..."
            )

            if on_progress:
                on_progress("started", 0, 0)

            # 2. Get products from both sites
            site_a_products = await self.supabase.get_products_by_site(
                job_id, Site.SITE_A
            )
            site_b_products = await self.supabase.get_products_by_site(
                job_id, Site.SITE_B
            )

            logger.info(
                f"Job {job_id}: {len(site_a_products)} source products, "
                f"{len(site_b_products)} target products"
            )

            if not site_a_products:
                raise ValueError("No source products (Site A) found for job")
            if not site_b_products:
                raise ValueError("No target products (Site B) found for job")

            # 3. Crawl products that need crawling
            await self._crawl_pending_products(
                job_id, site_a_products, Site.SITE_A, tracker, on_progress
            )
            await self._crawl_pending_products(
                job_id, site_b_products, Site.SITE_B, tracker, on_progress
            )

            # Refresh products after crawling (to get updated titles)
            site_a_products = await self.supabase.get_products_by_site(
                job_id, Site.SITE_A
            )
            site_b_products = await self.supabase.get_products_by_site(
                job_id, Site.SITE_B
            )

            # 3.5 Configure matcher from job config (AI validation toggle & cap)
            try:
                cfg = job.config if isinstance(job.config, dict) else {}
                ai_enabled = bool(cfg.get('ai_validation_enabled', False))
                ai_min = float(cfg.get('ai_validation_min', 0.70))
                ai_max = float(cfg.get('ai_validation_max', 0.90))
                ai_cap = int(cfg.get('ai_validation_cap', 100))
                embed_enriched = bool(cfg.get('embed_enriched_text', False))
                token_norm_v2 = bool(cfg.get('token_norm_v2', False))
                use_brand_onto = bool(cfg.get('use_brand_ontology', False))
                use_category_onto = bool(cfg.get('use_category_ontology', False))
                use_variant = bool(cfg.get('use_variant_extractor', False))
                use_ocr_text = bool(cfg.get('use_ocr_text', False))
                ocr_cap = int(cfg.get('ocr_max_comparisons', 500))
            except Exception:
                ai_enabled, ai_min, ai_max, ai_cap = False, 0.70, 0.90, 100
                embed_enriched, token_norm_v2 = False, False
                use_brand_onto, use_category_onto, use_variant = False, False, False
                use_ocr_text, ocr_cap = False, 500

            matcher_config = MatcherConfig(
                enable_ai_validation=ai_enabled,
                ai_validation_min_score=ai_min,
                ai_validation_max_score=ai_max,
                max_ai_validations_per_job=ai_cap,
                enable_image_matching=use_ocr_text,
                embed_enriched_text=embed_enriched,
                token_norm_v2=token_norm_v2,
                use_brand_ontology=use_brand_onto,
                use_category_ontology=use_category_onto,
                use_variant_extractor=use_variant,
                use_ocr_text=use_ocr_text,
                max_image_comparisons_per_job=ocr_cap
            )
            # Reset singleton with config for this job
            self.matcher = get_matcher_v2_service(config=matcher_config, reset=True)

            # 4. Generate and store Site B embeddings
            await tracker.start_stage(
                ProgressStage.GENERATING_EMBEDDINGS,
                total=len(site_b_products),
                message=f"Generating embeddings for {len(site_b_products)} products..."
            )

            if on_progress:
                on_progress("generating_embeddings", 0, len(site_b_products))

            logger.info(f"Generating embeddings for {len(site_b_products)} Site B products")
            embeddings = await self.matcher.generate_embeddings_batch(site_b_products)
            stored_count = await self.matcher.store_embeddings(embeddings)
            logger.info(f"Stored {stored_count} embeddings")

            await tracker.update_progress(
                stored_count,
                json.dumps({
                    "text": f"Generated {stored_count} embeddings",
                    "counters": {
                        "processed": 0,
                        "matched": 0,
                        "high_confidence": 0,
                        "no_match": 0,
                        "needs_review": 0,
                        "embedding_failed": max(len(site_b_products) - stored_count, 0),
                        "image_text_comparisons": 0
                    }
                }),
                force=True
            )
            await tracker.complete_stage("Embeddings generated")

            if on_progress:
                on_progress("generating_embeddings", stored_count, len(site_b_products))

            # 5. Match each Site A product
            await tracker.start_stage(
                ProgressStage.MATCHING,
                total=len(site_a_products),
                message=f"Matching {len(site_a_products)} products..."
            )

            results: list[MatchResult] = []
            logger.info(f"Matching {len(site_a_products)} products")

            # Live counters
            matched_count = 0
            high_confidence = 0
            no_match_count = 0
            needs_review_count = 0
            embedding_failed = max(len(site_b_products) - stored_count, 0)
            image_text_comparisons = 0

            for i, source in enumerate(site_a_products):
                # Update progress
                await tracker.update_progress(
                    i + 1,
                    json.dumps({
                        "text": f"Matching product {i + 1}/{len(site_a_products)}: {source.title[:50]}...",
                        "counters": {
                            "processed": i + 1,
                            "matched": matched_count,
                            "high_confidence": high_confidence,
                            "no_match": no_match_count,
                            "needs_review": needs_review_count,
                            "embedding_failed": embedding_failed,
                            "image_text_comparisons": image_text_comparisons
                        }
                    })
                )

                if on_progress:
                    on_progress("matching", i + 1, len(site_a_products))

                result = await self.matcher.match_product(source, job_id)
                results.append(result)
                # Update image comparisons counter from matcher metrics
                try:
                    image_text_comparisons = int(self.matcher.metrics.get("image_comparisons", image_text_comparisons))
                except Exception:
                    pass

                # 6. Store match result
                await self._store_match_result(job_id, result)

                # Update counters
                if result.is_no_match:
                    no_match_count += 1
                    needs_review_count += 1
                else:
                    matched_count += 1
                    # Confidence buckets
                    if result.confidence_tier in (ConfidenceTier.EXACT_MATCH, ConfidenceTier.HIGH_CONFIDENCE):
                        high_confidence += 1
                    elif result.confidence_tier in (ConfidenceTier.LIKELY_MATCH, ConfidenceTier.MANUAL_REVIEW):
                        needs_review_count += 1

                # Log progress every 10 products
                if (i + 1) % 10 == 0:
                    logger.info(f"Matched {i + 1}/{len(site_a_products)} products")

            await tracker.complete_stage(
                json.dumps({
                    "text": "Matching complete",
                    "counters": {
                        "processed": len(site_a_products),
                        "matched": matched_count,
                        "high_confidence": high_confidence,
                        "no_match": no_match_count,
                        "needs_review": needs_review_count,
                        "embedding_failed": embedding_failed,
                        "image_text_comparisons": image_text_comparisons
                    }
                })
            )

            # 7. Update status to COMPLETED
            await self.supabase.update_job_status(
                job_id, JobStatus.COMPLETED, completed_at=datetime.utcnow()
            )

            # Calculate statistics
            no_match_count = sum(1 for r in results if r.is_no_match)
            matched_count = len(results) - no_match_count
            high_confidence = sum(
                1 for r in results
                if not r.is_no_match and r.best_match and r.best_match.score >= 0.80
            )

            stats = {
                "status": "completed",
                "total_products": len(site_a_products),
                "matches_found": matched_count,
                "no_match": no_match_count,
                "high_confidence": high_confidence,
                "match_rate": f"{matched_count / len(site_a_products):.1%}" if site_a_products else "0%"
            }

            # Mark job as complete in progress tracker
            await tracker.finish_job(
                f"Completed: {matched_count} matches found ({high_confidence} high confidence)"
            )

            logger.info(f"Job {job_id} completed: {stats}")

            # Persist matcher metrics into job.config for observability
            try:
                metrics = self.matcher.get_matching_metrics() if hasattr(self.matcher, 'get_matching_metrics') else {}
                # Merge with existing job config
                job_after = await self.supabase.get_job(job_id)
                base_cfg = job_after.config if isinstance(job_after.config, dict) else {}
                base_cfg['metrics'] = metrics
                await self.supabase.update_job(job_id, CrawlJobUpdate(config=JobConfig().model_validate(base_cfg)))
            except Exception as e:
                logger.warning(f"Failed to persist matcher metrics for job {job_id}: {e}")

            return stats

        except Exception as e:
            logger.error(f"Job {job_id} failed: {e}", exc_info=True)

            # Update progress to failed state
            await tracker.fail(str(e))

            await self.supabase.update_job_status(job_id, JobStatus.FAILED)
            raise

    async def _crawl_pending_products(
        self,
        job_id: UUID,
        products: list[Product],
        site: Site,
        tracker: ProgressTracker,
        on_progress: Optional[Callable]
    ):
        """
        Crawl products that have pending crawl status.

        Args:
            job_id: Job UUID
            products: List of products to potentially crawl
            site: Which site (SITE_A or SITE_B)
            tracker: Progress tracker instance
            on_progress: Optional legacy callback
        """
        # Filter products that need crawling
        pending = [
            p for p in products
            if p.metadata.get('crawl_status') == 'pending'
        ]

        if not pending:
            logger.info(f"No pending products to crawl for {site.value}")
            return

        logger.info(f"Crawling {len(pending)} pending products for {site.value}")

        # Determine stage based on site
        stage = (
            ProgressStage.CRAWLING_SITE_A
            if site == Site.SITE_A
            else ProgressStage.CRAWLING_SITE_B
        )

        await tracker.start_stage(
            stage,
            total=len(pending),
            message=f"Crawling {len(pending)} products from {site.value}..."
        )

        if on_progress:
            on_progress(stage.value, 0, len(pending))

        try:
            async with ProductCrawler(headless=True, max_concurrent=3) as crawler:
                for i, product in enumerate(pending):
                    await tracker.update_progress(
                        i + 1,
                        f"Crawling {product.url[:50]}..."
                    )

                    if on_progress:
                        on_progress(stage.value, i + 1, len(pending))

                    data = await crawler.crawl_product(product.url)

                    if data.success and data.title:
                        # Update product with crawled data
                        try:
                            self.supabase.client.rpc('url_update_product', {
                                'p_product_id': str(product.id),
                                'p_title': data.title,
                                'p_brand': data.brand or product.brand,
                                'p_category': data.category or product.category,
                                'p_price': data.price,
                                'p_metadata': {
                                    **product.metadata,
                                    'crawl_status': 'completed',
                                    'crawl_source': data.metadata.get('source', 'unknown')
                                }
                            }).execute()
                        except Exception as e:
                            logger.warning(f"Failed to update product {product.id}: {e}")
                    else:
                        logger.warning(
                            f"Crawl failed for {product.url}: {data.error}"
                        )

            await tracker.complete_stage(f"Crawled {len(pending)} products")

        except Exception as e:
            logger.error(f"Crawler error for {site.value}: {e}")
            # Don't fail the entire job, just log the error
            await tracker.update_progress(
                len(pending),
                f"Crawling completed with errors: {str(e)[:100]}",
                force=True
            )

    async def _store_match_result(self, job_id: UUID, result: MatchResult):
        """Store match result in database with top 5 candidates."""
        try:
            # Convert candidates to JSON-serializable format
            candidates_json = [
                {
                    "product_id": str(c.product_id),
                    "title": c.title,
                    "url": c.url,
                    "score": round(c.score, 4),
                    "brand": c.brand,
                    "category": c.category
                }
                for c in result.top_5_candidates
            ]

            rpc_result = self.supabase.client.rpc('store_match_with_candidates', {
                'p_job_id': str(job_id),
                'p_source_product_id': str(result.source_product.id),
                'p_matched_product_id': str(result.best_match.product_id) if result.best_match else None,
                'p_score': round(result.best_match.score, 4) if result.best_match else 0,
                'p_confidence_tier': result.confidence_tier.value,
                'p_explanation': result.explanation,
                'p_top_5_candidates': candidates_json,
                'p_is_no_match': result.is_no_match,
                'p_no_match_reason': result.no_match_reason or None
            }).execute()

            # Auto-approve >= 0.90, auto-reject < 0.50
            try:
                data = rpc_result.data
                # Handle both list and single row
                match_row = None
                if isinstance(data, list) and data:
                    match_row = data[0]
                elif isinstance(data, dict):
                    match_row = data

                if match_row and match_row.get('id'):
                    match_id = match_row['id']
                    new_status: MatchStatus | None = None
                    if result.is_no_match or result.confidence_tier == ConfidenceTier.NO_MATCH:
                        new_status = MatchStatus.REJECTED
                    elif (
                        result.confidence_tier in (ConfidenceTier.EXACT_MATCH, ConfidenceTier.HIGH_CONFIDENCE)
                    ):
                        new_status = MatchStatus.APPROVED

                    if new_status is not None:
                        self.supabase.client.rpc('url_update_match_status', {
                            'p_match_id': str(match_id),
                            'p_status': new_status.value
                        }).execute()
            except Exception as e:
                logger.warning(f"Failed to apply auto-status for match: {e}")

        except Exception as e:
            logger.error(f"Failed to store match result: {e}")
            raise


# Background task wrapper for FastAPI
async def run_job_background(job_id: UUID):
    """
    Wrapper for running job as FastAPI background task.

    This function is designed to be used with FastAPI's BackgroundTasks
    or asyncio.create_task() for non-blocking job execution.

    Args:
        job_id: The job UUID to execute
    """
    runner = JobRunner()
    try:
        await runner.run_job(job_id)
    except Exception as e:
        logger.error(f"Background job {job_id} failed: {e}")
        # Progress tracker has already been updated in run_job
