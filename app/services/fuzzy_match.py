from __future__ import annotations

from typing import List, Tuple

from rapidfuzz import fuzz, process  # type: ignore
from sqlalchemy.orm import Session

from app.models import Product
from app.utils.product_parser import extract_base_code


def normalize_product_code(query: str) -> str:
    q = (query or "").upper()
    return "".join(ch for ch in q if ch.isalnum())


def exact_match(db: Session, normalized_code: str) -> Tuple[list[Product], float]:
    match = db.query(Product).filter(Product.product_code == normalized_code).all()
    return match, 1.0 if match else 0.0


def base_code_match(db: Session, normalized_code: str) -> Tuple[list[Product], float]:
    base, _ = extract_base_code(normalized_code)
    matches = db.query(Product).filter(Product.base_code == base).all()
    return matches, 0.95 if matches else 0.0


def fuzzy_string_match(db: Session, normalized_code: str, threshold: float = 0.85) -> list[tuple[Product, float]]:
    codes = db.query(Product.product_code).all()
    all_codes = [c[0] for c in codes]
    results = []
    for code in all_codes:
        score = fuzz.ratio(normalized_code, code) / 100.0
        if score >= threshold:
            prod = db.query(Product).filter(Product.product_code == code).one()
            results.append((prod, score))
    results.sort(key=lambda x: x[1], reverse=True)
    return results

