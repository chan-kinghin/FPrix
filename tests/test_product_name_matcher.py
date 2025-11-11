"""
Tests for product name matching service (description-based queries).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models import Base, Product, PricingTier
from app.services.product_name_matcher import (
    extract_description_from_query,
    normalize_chinese_text,
    search_by_description,
    match_product_by_description,
)
from app.services.wide_search import detect_wide_query, run_wide_search


def setup_mem_db():
    """Create in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:")

    # Register pick_price function for ALL connections from this engine
    from sqlite3 import Connection as SQLite3Connection
    from sqlalchemy import event

    @event.listens_for(engine, "connect")
    def receive_connect(dbapi_connection, connection_record):
        if isinstance(dbapi_connection, SQLite3Connection):
            dbapi_connection.create_function("pick_price", 3, _mock_pick_price)

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _mock_pick_price(product_id: int, tier: str, color_type: str) -> float:
    """Mock pick_price function for SQLite testing."""
    # Return mock prices based on product_id
    # Product 1 (GT10S): $0.90
    # Product 2 (GT10P): $0.70
    # Product 3 (2321P): $0.72
    price_map = {
        1: 0.90,
        2: 0.70,
        3: 0.72,
    }
    return price_map.get(product_id)


def seed_test_products(db):
    """Seed database with test products for description-based matching."""
    # Product 1: GT10S (Silicone version)
    p1 = Product(
        product_code="GT10S",
        base_code="GT10",
        product_name_cn="儿童分体简易 带扣 SILICONE",
        category="泳镜",
        material_type="SILICONE",
        base_cost=0.68,
        source_pdf="2025.10.28 泳镜.pdf",
        source_page=2,
        screenshot_url="screenshots/GT10S.png",
    )

    # Product 2: GT10P (PVC version, same base code)
    p2 = Product(
        product_code="GT10P",
        base_code="GT10",
        product_name_cn="儿童分体简易 带扣 PVC",
        category="泳镜",
        material_type="PVC",
        base_cost=0.55,
        source_pdf="2025.10.28 泳镜.pdf",
        source_page=2,
        screenshot_url="screenshots/GT10P.png",
    )

    # Product 3: 2321P (PVC version, different base code but similar name)
    p3 = Product(
        product_code="2321P",
        base_code="2321",
        product_name_cn="儿童分体简易 带扣 PVC",
        category="泳镜",
        material_type="PVC",
        base_cost=0.60,
        source_pdf="2025.10.28 泳镜.pdf",
        source_page=3,
        screenshot_url="screenshots/2321P.png",
    )

    db.add_all([p1, p2, p3])
    db.commit()

    # Add pricing tiers
    db.add_all([
        PricingTier(product_id=p1.product_id, tier="C级", color_type="标准色", price=0.90),
        PricingTier(product_id=p2.product_id, tier="C级", color_type="标准色", price=0.70),
        PricingTier(product_id=p3.product_id, tier="C级", color_type="标准色", price=0.72),
    ])
    db.commit()

    return p1, p2, p3


# === Tests for extract_description_from_query ===

def test_extract_description_basic():
    """Test basic Chinese description extraction."""
    query = "比 儿童分体简易 Silicone 便宜的"
    result = extract_description_from_query(query)
    assert result == "儿童分体简易"


def test_extract_description_no_space():
    """Test extraction without spaces."""
    query = "比儿童分体简易 PVC贵"
    result = extract_description_from_query(query)
    assert result == "儿童分体简易"


def test_extract_description_with_material():
    """Test extraction with material keywords."""
    query = "比 成人款大框 硅胶 便宜的"
    result = extract_description_from_query(query)
    assert result == "成人款大框"


def test_extract_description_none():
    """Test when no description can be extracted."""
    query = "比 GT10S 便宜的"
    result = extract_description_from_query(query)
    # Should return None since GT10S is not followed by material/comparison keywords
    assert result is None or result == "GT10S"  # May extract code as description


# === Tests for normalize_chinese_text ===

def test_normalize_chinese_text_basic():
    """Test basic text normalization."""
    text = "儿童分体简易 带扣 SILICONE"
    result = normalize_chinese_text(text)
    assert "儿童分体简易" in result
    assert "带扣" in result
    assert "silicone" in result  # Should be lowercased


def test_normalize_chinese_text_punctuation():
    """Test punctuation removal."""
    text = "儿童款、分体式（简易）"
    result = normalize_chinese_text(text)
    assert "儿童款" in result
    assert "分体式" in result
    assert "简易" in result
    assert "、" not in result
    assert "（" not in result


# === Tests for search_by_description ===

def test_search_by_description_with_material():
    """Test searching by description with material filter."""
    db = setup_mem_db()
    seed_test_products(db)

    # Search for Silicone products matching "儿童分体简易"
    results = search_by_description(db, "儿童分体简易", material="SILICONE", threshold=0.70)

    assert len(results) > 0
    codes = [prod.product_code for prod, score in results]
    assert "GT10S" in codes

    # Should NOT include PVC products
    assert "GT10P" not in codes
    assert "2321P" not in codes


def test_search_by_description_without_material():
    """Test searching without material filter returns all matches."""
    db = setup_mem_db()
    seed_test_products(db)

    # Search without material filter
    results = search_by_description(db, "儿童分体简易", material=None, threshold=0.70)

    assert len(results) >= 3  # Should find GT10S, GT10P, 2321P
    codes = [prod.product_code for prod, score in results]
    assert "GT10S" in codes
    assert "GT10P" in codes or "2321P" in codes  # At least one PVC version


def test_search_by_description_pvc_only():
    """Test searching for PVC products only."""
    db = setup_mem_db()
    seed_test_products(db)

    # Search for PVC products
    results = search_by_description(db, "儿童分体简易", material="PVC", threshold=0.70)

    assert len(results) >= 2  # GT10P and 2321P
    codes = [prod.product_code for prod, score in results]
    assert "GT10S" not in codes  # Silicone should not be included


def test_search_by_description_no_matches():
    """Test search with no matching products."""
    db = setup_mem_db()
    seed_test_products(db)

    # Search for non-existent product
    results = search_by_description(db, "不存在的产品描述", material=None, threshold=0.70)

    assert len(results) == 0


# === Tests for match_product_by_description ===

def test_match_product_by_description_full_flow():
    """Test the high-level matching function with full query."""
    db = setup_mem_db()
    seed_test_products(db)

    query = "比 儿童分体简易 Silicone 便宜的"
    results = match_product_by_description(db, query, threshold=0.70)

    assert len(results) > 0
    codes = [prod.product_code for prod, score in results]
    assert "GT10S" in codes


def test_match_product_by_description_with_pvc():
    """Test matching with PVC material hint."""
    db = setup_mem_db()
    seed_test_products(db)

    query = "比 儿童分体简易 PVC 便宜的"
    results = match_product_by_description(db, query, threshold=0.70)

    assert len(results) >= 2  # Should find GT10P and/or 2321P
    # Should not include Silicone
    codes = [prod.product_code for prod, score in results]
    assert "GT10S" not in codes


# === Integration tests with wide_search ===

def test_wide_search_description_based_detection():
    """Test that wide_search detects description-based queries."""
    query = "比 儿童分体简易 Silicone 便宜的"
    params = detect_wide_query(query)

    assert params is not None
    assert params.mode == "compare_lt"
    assert params.description_query is not None
    assert params.ref_code is None  # No product code extracted


@pytest.mark.skip(reason="Requires PostgreSQL (CROSS JOIN LATERAL not supported in SQLite)")
def test_wide_search_description_based_cheaper():
    """Test full wide_search flow for description-based 'cheaper than' query.

    NOTE: This test requires PostgreSQL because wide_search uses CROSS JOIN LATERAL.
    For actual testing, run against a real PostgreSQL database with test data.
    """
    pass


@pytest.mark.skip(reason="Requires PostgreSQL (CROSS JOIN LATERAL not supported in SQLite)")
def test_wide_search_code_based_still_works():
    """Test that traditional code-based queries still work.

    NOTE: This test requires PostgreSQL because wide_search uses CROSS JOIN LATERAL.
    For actual testing, run against a real PostgreSQL database with test data.
    """
    pass


@pytest.mark.skip(reason="Requires PostgreSQL (CROSS JOIN LATERAL not supported in SQLite)")
def test_wide_search_description_more_expensive():
    """Test description-based 'more expensive than' query.

    NOTE: This test requires PostgreSQL because wide_search uses CROSS JOIN LATERAL.
    For actual testing, run against a real PostgreSQL database with test data.
    """
    pass


def test_wide_search_description_no_matches():
    """Test description-based query with no matching products."""
    db = setup_mem_db()
    seed_test_products(db)

    query = "比 不存在的产品 便宜的"
    params = detect_wide_query(query)
    assert params is not None

    result = run_wide_search(db, params)

    assert result["status"] == "error"
    assert result["error_type"] == "reference_not_found"
