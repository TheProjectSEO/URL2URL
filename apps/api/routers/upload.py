"""
CSV Upload Router for URL-to-URL Product Matching API
Handles CSV file uploads for product URLs from both sites.
"""

import csv
import io
import logging
from typing import List
from uuid import UUID

from fastapi import APIRouter, UploadFile, File, HTTPException, BackgroundTasks
from pydantic import BaseModel, HttpUrl

from models.schemas import ProductCreate, Site
from services.supabase import get_supabase_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/upload", tags=["upload"])


class CSVUploadResponse(BaseModel):
    """Response for CSV upload endpoint"""
    uploaded: int
    failed: int
    job_id: str
    errors: List[str]


class ProductURL(BaseModel):
    """Single product URL from CSV"""
    url: str
    title: str = None
    brand: str = None
    category: str = None
    price: float = None


@router.post("/products/{job_id}/{site}", response_model=CSVUploadResponse)
async def upload_products_csv(
    job_id: UUID,
    site: str,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None
) -> CSVUploadResponse:
    """
    Upload CSV file with product URLs.

    Args:
        job_id: The job to add products to
        site: Either "site_a" (source products) or "site_b" (catalog to match against)
        file: CSV file with at least a 'url' column

    CSV Format:
        Required: url
        Optional: title, brand, category, price

    Example CSV:
        url,title,brand
        https://nykaa.com/product/123,Maybelline Fit Me,Maybelline
        https://nykaa.com/product/456,L'Oreal Paris Foundation,L'Oreal
    """
    # Validate site parameter
    if site not in ["site_a", "site_b"]:
        raise HTTPException(
            status_code=400,
            detail="site must be 'site_a' or 'site_b'"
        )

    # Validate file type
    if not file.filename.endswith('.csv'):
        raise HTTPException(
            status_code=400,
            detail="File must be a CSV file"
        )

    # Read and parse CSV
    content = await file.read()
    try:
        decoded = content.decode('utf-8')
        reader = csv.DictReader(io.StringIO(decoded))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid CSV file: {str(e)}"
        )

    # Validate CSV has required columns
    if 'url' not in reader.fieldnames:
        raise HTTPException(
            status_code=400,
            detail="CSV must have a 'url' column"
        )

    # Parse and validate URLs
    products: List[ProductURL] = []
    errors: List[str] = []

    for i, row in enumerate(reader, start=2):  # Start at 2 (header is row 1)
        url = row.get('url', '').strip()

        if not url:
            errors.append(f"Row {i}: Missing URL")
            continue

        if not url.startswith('http'):
            errors.append(f"Row {i}: Invalid URL format (must start with http/https)")
            continue

        # Parse optional fields
        price = None
        if row.get('price'):
            try:
                price = float(row['price'].replace('₹', '').replace(',', '').strip())
            except ValueError:
                pass  # Skip invalid prices silently

        products.append(ProductURL(
            url=url,
            title=row.get('title', '').strip() or None,
            brand=row.get('brand', '').strip() or None,
            category=row.get('category', '').strip() or None,
            price=price
        ))

    if not products:
        raise HTTPException(
            status_code=400,
            detail="No valid products found in CSV"
        )

    # Store products in database
    supabase = get_supabase_service()
    uploaded = 0

    for product_url in products:
        try:
            await supabase.create_product(ProductCreate(
                job_id=job_id,
                site=Site(site),
                url=product_url.url,
                title=product_url.title or "Pending crawl",
                brand=product_url.brand,
                category=product_url.category,
                price=product_url.price,
                metadata={"crawl_status": "pending" if not product_url.title else "provided"}
            ))
            uploaded += 1
        except Exception as e:
            errors.append(f"Failed to store {product_url.url}: {str(e)}")

    logger.info(f"CSV upload for job {job_id}: {uploaded} products uploaded, {len(errors)} errors")

    return CSVUploadResponse(
        uploaded=uploaded,
        failed=len(products) - uploaded,
        job_id=str(job_id),
        errors=errors[:10]  # Limit errors to first 10
    )


@router.get("/template")
async def get_csv_template():
    """Return example CSV template for product upload."""
    return {
        "format": "CSV with headers",
        "required_columns": ["url"],
        "optional_columns": ["title", "brand", "category", "price"],
        "example": "url,title,brand,category,price\nhttps://nykaa.com/product/123,Maybelline Fit Me Foundation,Maybelline,Foundation,599\nhttps://nykaa.com/product/456,L'Oreal Paris Serum,L'Oreal,Serum,899"
    }
