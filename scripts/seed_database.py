#!/usr/bin/env python
"""Seed database with extracted data.

Reads products from `data/reports/products.jsonl` and bulk inserts into
products/pricing_tiers/product_sizes tables within a single transaction.
"""

from typing import Any, Dict

from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import SessionLocal
from app.models import Product, PricingTier, ProductSize, PricingHistory
from app.utils.product_parser import extract_base_code, determine_material


from typing import Dict, Tuple, Optional


def _validate_pricing_map(tier_map: Dict[Tuple[str, str], Optional[float]]) -> list[str]:
    errs: list[str] = []
    def _get(tier: str, color: str) -> Optional[float]:
        v = tier_map.get((tier, color))
        try:
            return None if v is None else float(v)
        except Exception:
            return None

    for color in ("标准色", "定制色"):
        vals = []
        present = []
        for t in ("A级", "B级", "C级", "D级"):
            v = _get(t, color)
            if v is not None:
                vals.append(v)
                present.append(t)
        if len(vals) >= 2:
            if vals != sorted(vals):
                errs.append(f"{color}: 非递增: {list(zip(present, vals))}")
    # 定制 >= 标准（逐级对比）
    for t in ("A级", "B级", "C级", "D级"):
        s = _get(t, "标准色")
        c = _get(t, "定制色")
        if s is not None and c is not None and c < s:
            errs.append(f"{t}: 定制色({c}) < 标准色({s})")
    return errs


def main() -> None:
    import json
    from pathlib import Path

    path = Path("data/reports/products.jsonl")
    if not path.exists():
        print(f"No extracted data found at {path}. Run scripts/extract_pdfs.py first.")
        return

    db: Session = SessionLocal()
    try:
        with db.begin():
            seen_tiers = set()
            inserted_products = 0
            inserted_tiers = 0
            updated_tiers = 0
            warnings: list[str] = []
            inserted_sizes = 0
            for line in path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                rec: Dict[str, Any] = json.loads(line)
                code = rec.get("product_code")
                if not code:
                    continue
                # skip if product already exists
                existing = db.query(Product).filter(Product.product_code == code).first()

                base, _ = extract_base_code(code)
                material = rec.get("material_type") or determine_material(code, None)
                # compute screenshot filename fallback based on pdf + page
                screenshot = rec.get("screenshot_url")
                try:
                    pdf_name = (rec.get("source_pdf") or "").rsplit(".", 1)[0]
                    page = int(rec.get("source_page") or 1)
                    if not screenshot:
                        screenshot = f"{pdf_name}_page_{page}.png"
                except Exception:
                    pass

                is_new = existing is None
                if existing:
                    prod = existing
                    # update subcategory/notes if provided
                    if rec.get("row_label"):
                        prod.subcategory = rec.get("row_label")
                    if rec.get("material_type"):
                        try:
                            prod.material_type = rec.get("material_type") or prod.material_type
                        except Exception:
                            pass
                    if rec.get("screenshot_bbox"):
                        import json as _json
                        try:
                            meta = {"highlight": rec.get("screenshot_bbox")}
                            prod.notes = _json.dumps(meta, ensure_ascii=False)
                        except Exception:
                            pass
                else:
                    prod = Product(
                        product_code=code,
                        base_code=base,
                        product_name_cn=rec.get("product_name_cn"),
                        category=rec.get("category") or "",
                        subcategory=rec.get("subcategory") or rec.get("row_label"),
                        material_type=material or "",
                        base_cost=float(rec.get("base_cost") or 0),
                        net_weight_grams=rec.get("net_weight_grams"),
                        status=rec.get("status") or "active",
                        source_pdf=rec.get("source_pdf") or "",
                        source_page=int(rec.get("source_page") or 1),
                        screenshot_url=screenshot,
                        notes=None,
                    )
                    if rec.get("screenshot_bbox"):
                        import json as _json
                        try:
                            meta = {"highlight": rec.get("screenshot_bbox")}
                            prod.notes = _json.dumps(meta, ensure_ascii=False)
                        except Exception:
                            pass
                    db.add(prod)
                    db.flush()  # assign product_id
                    inserted_products += 1

                # Insert pricing tiers if available
                tier_map = {
                    ("A级", "标准色"): rec.get("A级_标准"),
                    ("A级", "定制色"): rec.get("A级_定制"),
                    ("B级", "标准色"): rec.get("B级_标准"),
                    ("B级", "定制色"): rec.get("B级_定制"),
                    ("C级", "标准色"): rec.get("C级_标准"),
                    ("C级", "定制色"): rec.get("C级_定制"),
                    ("D级", "标准色"): rec.get("D级_标准"),
                    ("D级", "定制色"): rec.get("D级_定制"),
                }
                # Pricing sanity checks (non-blocking)
                _errs = _validate_pricing_map(tier_map)
                if _errs:
                    warnings.append(f"[{code}] " + "; ".join(_errs))
                for (tier, color), value in tier_map.items():
                    try:
                        if value is None:
                            continue
                        price = float(value)
                        # avoid duplicate inserts within this run and skip if exists in DB
                        key = (prod.product_code, tier, color)
                        if key in seen_tiers:
                            continue
                        exists = (
                            db.query(PricingTier)
                            .filter(
                                PricingTier.product_id == prod.product_id,
                                PricingTier.tier == tier,
                                PricingTier.color_type == color,
                            )
                            .first()
                        )
                        if exists is None:
                            db.add(
                                PricingTier(
                                    product_id=prod.product_id,
                                    tier=tier,
                                    color_type=color,
                                    price=price,
                                )
                            )
                            inserted_tiers += 1
                            seen_tiers.add(key)
                        else:
                            # Upsert: if price changed, update and record history
                            old = float(exists.price)
                            if abs(old - price) > 1e-9:
                                exists.price = price
                                db.add(
                                    PricingHistory(
                                        product_id=prod.product_id,
                                        tier=tier,
                                        color_type=color,
                                        old_price=old,
                                        new_price=price,
                                        change_reason="seed_update",
                                    )
                                )
                                updated_tiers += 1
                            seen_tiers.add(key)
                    except Exception:
                        continue

                # Insert size variants if present
                if is_new:
                    # de-duplicate size entries by (size_code, size_range)
                    seen_sizes = set()
                    for s in rec.get("sizes", []) or []:
                        size_code = (s.get("size_code") or "").upper()
                        size_range = s.get("size_range")
                        key = (size_code, size_range or "")
                        if (not size_code and not size_range) or key in seen_sizes:
                            continue
                        if not size_code:
                            # skip entries without a size_code to satisfy uniqueness
                            continue
                        seen_sizes.add(key)
                        try:
                            db.add(
                                ProductSize(
                                    product_id=prod.product_id,
                                    size_code=size_code,
                                    size_range=size_range,
                                )
                            )
                            inserted_sizes += 1
                        except Exception:
                            # ignore any unique constraint violations per product
                            pass

        print(f"Inserted {inserted_products} products, {inserted_tiers} inserted tiers, {updated_tiers} updated tiers, {inserted_sizes} sizes")
        if warnings:
            from datetime import datetime
            out_dir = Path("data/reports")
            out_dir.mkdir(parents=True, exist_ok=True)
            p = out_dir / f"seed_warnings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            p.write_text("\n".join(warnings))
            print(f"Seed warnings: {len(warnings)} (details: {p})")
    finally:
        db.close()


if __name__ == "__main__":
    main()
