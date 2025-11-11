"""帽子配件 (caps/accessories) extractor (heuristic)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Any, Optional

import pdfplumber  # type: ignore
from app.utils.product_parser import determine_material

CODE_RE = re.compile(r"[A-Z]{1,3}\s*-?\s*\d{1,4}[SP]?")


def _normalize_code(raw: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", raw.upper())


def extract_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    pdf = Path(pdf_path)
    with pdfplumber.open(str(pdf)) as doc:
        for page_idx, page in enumerate(doc.pages, start=1):
            try:
                tables = page.extract_tables() or []
            except Exception:
                tables = []

            for table in tables:
                for row in table:
                    if not row:
                        continue
                    joined = " ".join(str(c or "") for c in row)
                    m = CODE_RE.search(joined.upper())
                    if not m:
                        continue
                    code = _normalize_code(m.group(0))
                    # Infer material from suffix or descriptive words (row text)
                    material = determine_material(code, joined)
                    if code.endswith("S"):
                        material = material or "SILICONE"
                    elif code.endswith("P"):
                        material = material or "PVC"
                    row_label = (str(row[0]).strip() if row and row[0] else None)

                    # best-effort highlight bbox for code text
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
                        "category": "帽子配件",
                        "source_pdf": pdf.name,
                        "source_page": page_idx,
                        "row_label": row_label,
                        "screenshot_bbox": bbox,
                    }
                    records.append(rec)

            if not tables:
                try:
                    text = page.extract_text() or ""
                except Exception:
                    text = ""
                for m in CODE_RE.finditer(text.upper()):
                    code = _normalize_code(m.group(0))
                    material = determine_material(code, text)
                    if code.endswith("S"):
                        material = material or "SILICONE"
                    elif code.endswith("P"):
                        material = material or "PVC"
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
                        "category": "帽子配件",
                        "source_pdf": pdf.name,
                        "source_page": page_idx,
                        "screenshot_bbox": bbox,
                    }
                    records.append(rec)

    seen = set()
    unique: List[Dict[str, Any]] = []
    for r in records:
        if r["product_code"] in seen:
            continue
        seen.add(r["product_code"])
        unique.append(r)
    return unique
