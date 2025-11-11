#!/usr/bin/env python
"""Audit DB pricing tiers against extracted JSON.

Compares products in DB to `data/extracted/products.json` and reports mismatches
for A/B/C/D × 标准/定制.
"""

from __future__ import annotations

from pathlib import Path
import json
from typing import Dict, Any

from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import Product, PricingTier


def _load_extracted() -> Dict[str, Dict[str, Any]]:
    p = Path("data/extracted/products.json")
    if not p.exists():
        return {}
    data = json.loads(p.read_text(encoding="utf-8"))
    idx: Dict[str, Dict[str, Any]] = {}
    for r in data:
        code = r.get("product_code")
        if code:
            idx[code] = r
    return idx


def main() -> None:
    extracted = _load_extracted()
    if not extracted:
        print("No extracted data found. Run scripts/extract_pdfs.py first.")
        return
    db: Session = SessionLocal()
    mismatches = []
    try:
        for prod in db.query(Product).all():
            rec = extracted.get(prod.product_code)
            if not rec:
                continue
            # Build expected tier map from extracted record
            expect = {
                ("A级", "标准色"): rec.get("A级_标准"),
                ("A级", "定制色"): rec.get("A级_定制"),
                ("B级", "标准色"): rec.get("B级_标准"),
                ("B级", "定制色"): rec.get("B级_定制"),
                ("C级", "标准色"): rec.get("C级_标准"),
                ("C级", "定制色"): rec.get("C级_定制"),
                ("D级", "标准色"): rec.get("D级_标准"),
                ("D级", "定制色"): rec.get("D级_定制"),
            }
            # Read DB tiers
            rows = (
                db.query(PricingTier)
                .filter(PricingTier.product_id == prod.product_id)
                .all()
            )
            db_map = {(r.tier, r.color_type): float(r.price) for r in rows}
            for key, ev in expect.items():
                if ev is None:
                    continue
                try:
                    evf = float(ev)
                except Exception:
                    continue
                dv = db_map.get(key)
                if dv is None:
                    mismatches.append(f"[{prod.product_code}] missing in DB: {key} expected {evf}")
                    continue
                if abs(dv - evf) > 1e-9:
                    mismatches.append(
                        f"[{prod.product_code}] mismatch {key}: db={dv} extracted={evf}"
                    )
    finally:
        db.close()

    if mismatches:
        out = Path("data/reports") / "audit_db_vs_extracted.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(mismatches), encoding="utf-8")
        print(f"Found {len(mismatches)} mismatches. See {out}")
    else:
        print("Audit passed: DB matches extracted data.")


if __name__ == "__main__":
    main()

