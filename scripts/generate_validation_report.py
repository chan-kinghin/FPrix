#!/usr/bin/env python
"""Run validations on extracted data and write a report.

Looks for JSON file at data/extracted/products.json with a list of product dicts.
Writes a text report to data/reports/validation_{timestamp}.txt
"""

from pathlib import Path
from datetime import datetime
import json

from app.utils.validation import validate_product


def main() -> None:
    out_dir = Path("data/reports")
    out_dir.mkdir(parents=True, exist_ok=True)
    extracted = Path("data/extracted/products.json")
    out = out_dir / f"validation_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    if not extracted.exists():
        out.write_text("No extracted data found at data/extracted/products.json\n")
        print(f"Wrote {out}")
        return

    products = json.loads(extracted.read_text())
    total = len(products)
    all_errors = []
    for p in products:
        errs = validate_product(p)
        if errs:
            all_errors.append((p.get("product_code", "UNKNOWN"), errs))

    # classify severities (simple heuristic)
    def classify(msg: str) -> str:
        m = (msg or "").lower()
        if "invalid price" in m:
            return "WARNING"
        return "ERROR"

    lines = []
    lines.append(f"Total products: {total}")
    lines.append(f"Products with issues: {len(all_errors)}")
    rate = (len(all_errors) / total * 100) if total else 0.0
    lines.append(f"Issue rate: {rate:.2f}%\n")

    # Group by severity
    grouped = {"ERROR": [], "WARNING": []}
    for code, errs in all_errors:
        for e in errs:
            grouped[classify(e)].append((code, e))

    for sev in ("ERROR", "WARNING"):
        lines.append(f"{sev}S:")
        for code, msg in grouped[sev]:
            lines.append(f"- [{code}] {msg}")
        lines.append("")

    out.write_text("\n".join(lines))
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
