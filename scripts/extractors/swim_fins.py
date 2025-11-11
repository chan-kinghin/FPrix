"""蛙鞋 (swim fins) extractor (heuristic).

Parses product codes and attempts to capture size variants if present.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

import pdfplumber  # type: ignore
from app.utils.product_parser import determine_material

CODE_RE = re.compile(r"[A-Z]{1,3}\s*-?\s*\d{1,4}[SP]?")
SIZE_CODE_RE = re.compile(r"\b(XXS|XS|S|M|L|XL|XXL)\b", re.IGNORECASE)
SIZE_RANGE_RE = re.compile(r"\b(\d{2}\s*[-~]\s*\d{2})\b")


def _normalize_code(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", raw.upper())


def _parse_sizes(text: str) -> List[Dict[str, Any]]:
    sizes: List[Dict[str, Any]] = []
    # collect all size codes and ranges in the text
    codes = [m.group(1).upper() for m in SIZE_CODE_RE.finditer(text)]
    ranges = [m.group(1).replace(" ", "") for m in SIZE_RANGE_RE.finditer(text)]
    # zip if counts match, else attach ranges without mapping
    if codes and ranges and len(codes) == len(ranges):
        for c, r in zip(codes, ranges):
            sizes.append({"size_code": c, "size_range": r})
    else:
        for c in codes:
            sizes.append({"size_code": c, "size_range": None})
        for r in ranges:
            sizes.append({"size_code": "", "size_range": r})
    return sizes


def extract_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    pdf = Path(pdf_path)
    with pdfplumber.open(str(pdf)) as doc:
        for page_idx, page in enumerate(doc.pages, start=1):
            try:
                tables = page.extract_tables() or []
            except Exception:
                tables = []

            page_sizes: List[Dict[str, Any]] = []

            # parse sizes from whole page text as a fallback context
            try:
                page_text = page.extract_text() or ""
            except Exception:
                page_text = ""
            if page_text:
                page_sizes = _parse_sizes(page_text)

            for table in tables:
                for row in table:
                    if not row:
                        continue
                    joined = " ".join(str(c or "") for c in row)
                    up = joined.upper()
                    m = CODE_RE.search(up)
                    if not m:
                        continue
                    code = _normalize_code(m.group(0))
                    # Derive material from suffix or descriptive words in the row/page
                    material = determine_material(code, joined)
                    if code.endswith("S"):
                        material = material or "SILICONE"
                    elif code.endswith("P"):
                        material = material or "PVC"
                    sizes = _parse_sizes(up) or page_sizes
                    # best-effort highlight bbox
                    bbox: Optional[Dict[str, int]] = None
                    try:
                        def _norm(s: str) -> str:
                            import re
                            return re.sub(r"[^A-Z0-9]", "", s.upper())
                        target = _norm(code)
                        for w in page.extract_words() or []:
                            if _norm(w.get("text", "")) == target:
                                x0, y0, x1, y1 = w["x0"], w["top"], w["x1"], w["bottom"]
                                scale = 300.0 / 72.0
                                x, y, width, height = int(x0 * scale), int(y0 * scale), int((x1 - x0) * scale), int((y1 - y0) * scale)
                                bbox = {"x": x, "y": y, "w": width, "h": height, "page": page_idx}
                                break
                    except Exception:
                        pass
                    rec: Dict[str, Any] = {
                        "product_code": code,
                        "base_code": code[:-1] if code and code[-1] in ("S", "P") else code,
                        "material_type": material,
                        "category": "蛙鞋",
                        "source_pdf": pdf.name,
                        "source_page": page_idx,
                        "screenshot_bbox": bbox,
                    }
                    if sizes:
                        rec["sizes"] = sizes
                    records.append(rec)

            if not tables and page_text:
                for m in CODE_RE.finditer(page_text.upper()):
                    code = _normalize_code(m.group(0))
                    material = determine_material(code, page_text)
                    if code.endswith("S"):
                        material = material or "SILICONE"
                    elif code.endswith("P"):
                        material = material or "PVC"
                    sizes = _parse_sizes(page_text)
                    bbox: Optional[Dict[str, int]] = None
                    try:
                        def _norm(s: str) -> str:
                            import re
                            return re.sub(r"[^A-Z0-9]", "", s.upper())
                        target = _norm(code)
                        for w in page.extract_words() or []:
                            if _norm(w.get("text", "")) == target:
                                x0, y0, x1, y1 = w["x0"], w["top"], w["x1"], w["bottom"]
                                scale = 300.0 / 72.0
                                x, y, width, height = int(x0 * scale), int(y0 * scale), int((x1 - x0) * scale), int((y1 - y0) * scale)
                                bbox = {"x": x, "y": y, "w": width, "h": height, "page": page_idx}
                                break
                    except Exception:
                        pass
                    rec = {
                        "product_code": code,
                        "base_code": code[:-1] if code and code[-1] in ("S", "P") else code,
                        "material_type": material,
                        "category": "蛙鞋",
                        "source_pdf": pdf.name,
                        "source_page": page_idx,
                        "screenshot_bbox": bbox,
                    }
                    if sizes:
                        rec["sizes"] = sizes
                    records.append(rec)

    # de-duplicate by product_code
    seen = set()
    unique: List[Dict[str, Any]] = []
    for r in records:
        if r["product_code"] in seen:
            continue
        seen.add(r["product_code"])
        unique.append(r)
    return unique
