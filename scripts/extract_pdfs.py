#!/usr/bin/env python
"""PDF extraction pipeline entry point (skeleton).

Steps (per TASKS.md):
- Detect category for each PDF in data/pdfs
- Route to category-specific extractor (to be implemented)
- Validate extracted data
- Optionally write to JSON/DB
"""

from pathlib import Path
import sys
import json
from typing import Any, Dict, List, Optional

DATA_DIR = Path("data/pdfs")

# Ensure project root is on sys.path so that `scripts.*` imports work
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def detect_category_from_filename(name: str) -> Optional[str]:
    if "泳镜" in name:
        return "泳镜"
    if "蛙鞋" in name:
        return "蛙鞋"
    if "潜水镜" in name:
        return "潜水镜"
    if "呼吸管" in name:
        return "呼吸管"
    if "帽子" in name:
        return "帽子配件"
    return None


def main() -> None:
    if not DATA_DIR.exists():
        print(f"No PDFs found at {DATA_DIR}. Place source PDFs there.")
        return

    pdfs = sorted(DATA_DIR.glob("*.pdf"))
    print(f"Found {len(pdfs)} PDFs")

    extracted: List[Dict[str, Any]] = []
    all_records: List[Dict[str, Any]] = []
    for pdf in pdfs:
        category = detect_category_from_filename(pdf.name) or "UNKNOWN"
        print(f"- {pdf.name} → {category}")
        records: List[Dict[str, Any]] = []
        try:
            if category == "泳镜":
                from scripts.extractors.swimming_goggles import extract_from_pdf as ex
                records = ex(str(pdf))
            elif category == "蛙鞋":
                from scripts.extractors.swim_fins import extract_from_pdf as ex
                records = ex(str(pdf))
            elif category == "潜水镜":
                from scripts.extractors.diving_masks import extract_from_pdf as ex
                records = ex(str(pdf))
            elif category == "呼吸管":
                from scripts.extractors.snorkels import extract_from_pdf as ex
                records = ex(str(pdf))
            elif category == "帽子配件":
                from scripts.extractors.caps import extract_from_pdf as ex
                records = ex(str(pdf))
        except Exception as e:
            print(f"  extractor error: {e}")

        # collect per-pdf summary
        extracted.append({
            "source_pdf": pdf.name,
            "category": category,
            "records": len(records),
        })

        # validate extracted records (non-blocking)
        try:
            from app.utils.validation import validate_product
            errs = 0
            for r in records:
                errs += 1 if validate_product(r) else 0
            if errs:
                print(f"  validation: {errs} records with issues (see validation script for details)")
        except Exception:
            pass

        # accumulate and write products to jsonl per PDF
        out_products = Path("data/reports/products.jsonl")
        out_products.parent.mkdir(parents=True, exist_ok=True)
        with out_products.open("a", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        all_records.extend(records)

    # write aggregated extracted json for validation/reporting
    extracted_json = Path("data/extracted/products.json")
    extracted_json.parent.mkdir(parents=True, exist_ok=True)
    extracted_json.write_text(json.dumps(all_records, ensure_ascii=False, indent=2))

    out = Path("data/reports/extraction_summary.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(extracted, ensure_ascii=False, indent=2))
    print(f"Summary written to {out}")


if __name__ == "__main__":
    main()
