"""
Product name matching service for description-based queries.

Enables matching products by Chinese product names (儿童分体简易)
rather than product codes (GT10S), with optional material filtering.
"""

from __future__ import annotations

from typing import List, Tuple, Optional
import re

from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from app.models import Product
from app.utils.inference import infer_material_from_query


def extract_description_from_query(query: str) -> Optional[str]:
    """
    Extract product description (Chinese text) from comparison query.

    Example queries:
        "比 儿童分体简易 Silicone 便宜的" -> "儿童分体简易"
        "比儿童分体简易 PVC贵" -> "儿童分体简易"

    Returns:
        Chinese product description or None if not found
    """
    q = (query or "").strip()

    # Pattern: 比 [description] [optional material] 便宜/贵
    # Look for Chinese characters after "比" and before material/comparison keywords
    pattern = r"比\s*([一-龥\s]+?)(?:\s*(?:SILICONE|PVC|TPE|硅胶|矽膠|便宜|贵|的))"
    match = re.search(pattern, q, re.IGNORECASE)

    if match:
        description = match.group(1).strip()
        # Remove common filler words
        description = description.replace("的", "").strip()
        return description if description else None

    return None


def normalize_chinese_text(text: str) -> str:
    """
    Normalize Chinese text for comparison.

    - Remove extra whitespace
    - Remove punctuation
    - Lowercase English characters
    """
    if not text:
        return ""

    # Remove common separators and punctuation
    text = re.sub(r'[，。、；：！？""''（）【】《》\s]+', ' ', text)
    text = text.strip().lower()

    return text


def search_by_description(
    db: Session,
    description: str,
    material: Optional[str] = None,
    threshold: float = 0.70
) -> List[Tuple[Product, float]]:
    """
    Search products by Chinese description with optional material filtering.

    Args:
        db: Database session
        description: Chinese product description (e.g., "儿童分体简易")
        material: Optional material filter ("SILICONE", "PVC", "TPE")
        threshold: Minimum fuzzy match score (0.0 - 1.0)

    Returns:
        List of (Product, confidence_score) tuples, sorted by score (highest first)

    Example:
        >>> matches = search_by_description(db, "儿童分体简易", "SILICONE", 0.70)
        >>> # Returns: [(GT10S product, 0.92), ...]
    """
    # Normalize the search description
    normalized_desc = normalize_chinese_text(description)

    if not normalized_desc:
        return []

    # Build base query
    query = db.query(Product)

    # Filter by material if provided
    if material:
        query = query.filter(Product.material_type == material.upper())

    # Get all products to fuzzy match
    all_products = query.all()

    results = []
    for product in all_products:
        if not product.product_name_cn:
            continue

        # Normalize product name from database
        normalized_product_name = normalize_chinese_text(product.product_name_cn)

        # Calculate fuzzy match scores using multiple algorithms
        # Use token_set_ratio for better partial matching (handles word order)
        score_token = fuzz.token_set_ratio(normalized_desc, normalized_product_name) / 100.0

        # Use partial_ratio for substring matching
        score_partial = fuzz.partial_ratio(normalized_desc, normalized_product_name) / 100.0

        # Take the maximum score (most generous match)
        score = max(score_token, score_partial)

        if score >= threshold:
            results.append((product, score))

    # Sort by confidence score (highest first)
    results.sort(key=lambda x: x[1], reverse=True)

    return results


def match_product_by_description(
    db: Session,
    query: str,
    threshold: float = 0.70
) -> List[Tuple[Product, float]]:
    """
    High-level function: extract description and material from query,
    then search for matching products.

    Args:
        db: Database session
        query: Full query text (e.g., "比儿童分体简易 Silicone便宜的")
        threshold: Minimum fuzzy match score

    Returns:
        List of (Product, confidence_score) tuples

    Example:
        >>> matches = match_product_by_description(db, "比儿童分体简易 Silicone便宜的")
        >>> # Returns: [(GT10S product, 0.92)]
    """
    # Extract description from query
    description = extract_description_from_query(query)

    if not description:
        return []

    # Infer material from query
    material = infer_material_from_query(query)

    # Search by description with material filter
    return search_by_description(db, description, material, threshold)
