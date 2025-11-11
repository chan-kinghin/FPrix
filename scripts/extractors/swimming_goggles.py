"""泳镜 (swimming goggles) PDF extractor.

Parses structured tables to extract:
- product name (CN), base code (款号), inferred material, and cost
- pricing tiers: A/B/C/D for 标准色 and 定制色

Heuristics:
- Header is two rows: a band row ("标准色价格"/"定制色价格") then labels row (款号/成本/A/B/C/D...)
- Material inferred from name cell text (contains "SILICONE"/"硅胶" or "PVC")
- Final product_code = base_code + suffix (S or P) when material known; else base_code
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Dict, Any, Optional, TypedDict

import pdfplumber  # type: ignore

from app.utils.product_parser import extract_base_code, determine_material


class _ColumnMap(TypedDict, total=False):
    name_idx: int
    code_idx: int
    cost_idx: int
    std_start: int
    cust_start: int


def _to_float(x: Any) -> Optional[float]:
    if x is None:
        return None
    try:
        s = str(x).strip().replace(",", "")
        return float(s) if s else None
    except Exception:
        return None


def extract_from_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    pdf = Path(pdf_path)
    with pdfplumber.open(str(pdf)) as doc:
        # Persist last detected header mapping across pages (for page breaks without header)
        last_map: Optional[_ColumnMap] = None
        for page_idx, page in enumerate(doc.pages, start=1):
            # extract tables
            try:
                tables = page.extract_tables() or []
            except Exception:
                tables = []

            for table in tables:
                # Try to find header row; if missing, reuse last_map
                header_idx: Optional[int] = None
                code_idx: Optional[int] = None
                cost_idx: Optional[int] = None
                name_idx: int = 0
                colmap: Optional[_ColumnMap] = None

                for i, row in enumerate(table):
                    if not row:
                        continue
                    row_norm = [str(c) if c is not None else "" for c in row]
                    if "款号" in row_norm and "成本" in row_norm:
                        header_idx = i
                        code_idx = row_norm.index("款号")
                        cost_idx = row_norm.index("成本")
                        name_idx = 0
                        # Try to detect A/B/C/D positions explicitly on header row
                        a_pos = [idx for idx, v in enumerate(row_norm) if "A级" in v]
                        if len(a_pos) >= 4:
                            std_start = a_pos[0]
                            cust_start = a_pos[4] if len(a_pos) >= 8 else (a_pos[0] + 4)
                        else:
                            std_start = (cost_idx or 2) + 1
                            cust_start = std_start + 4
                        colmap = {
                            "name_idx": name_idx,
                            "code_idx": code_idx or 0,
                            "cost_idx": cost_idx or 0,
                            "std_start": std_start,
                            "cust_start": cust_start,
                        }
                        last_map = colmap
                        break

                if header_idx is None:
                    # no header on this table; fall back to last_map if present
                    if last_map is None:
                        continue
                    colmap = last_map
                    # Start from the first row since there is no header row here
                    data_rows = table
                else:
                    data_rows = table[header_idx + 1 :]

                # iterate data rows using detected or persisted column map
                assert colmap is not None
                name_idx = int(colmap.get("name_idx", 0))
                code_idx = int(colmap.get("code_idx", 0))
                cost_idx = int(colmap.get("cost_idx", 0))
                std_start = int(colmap.get("std_start", (cost_idx or 2) + 1))
                cust_start = int(colmap.get("cust_start", std_start + 4))

                for row in data_rows:
                    if not row:
                        continue
                    cells = [str(c).strip() if c is not None else "" for c in row]
                    raw_code = cells[code_idx] if code_idx is not None and code_idx < len(cells) else ""
                    if not raw_code or raw_code in ("款号", "儿童款", "成人款"):
                        continue
                    base_code, _ = extract_base_code(raw_code)
                    name_text = cells[name_idx] if name_idx < len(cells) else ""
                    # left-most label (e.g., 儿童款/成人款/成人包胶款)
                    row_label = (cells[0] or "").strip()
                    material = determine_material(base_code, f"{name_text} {row_label}".strip())
                    # hard rule: GT61 is 成人包胶款 TPE
                    if base_code == "GT61":
                        material = "TPE"
                        if not row_label:
                            row_label = "成人包胶款"
                    suffix = "S" if material == "SILICONE" else ("P" if material == "PVC" else "")
                    product_code = f"{base_code}{suffix}"

                    base_cost = _to_float(cells[cost_idx]) if cost_idx is not None and cost_idx < len(cells) else None
                    a_std = _to_float(cells[std_start]) if std_start < len(cells) else None
                    b_std = _to_float(cells[std_start + 1]) if std_start + 1 < len(cells) else None
                    c_std = _to_float(cells[std_start + 2]) if std_start + 2 < len(cells) else None
                    d_std = _to_float(cells[std_start + 3]) if std_start + 3 < len(cells) else None
                    a_cus = _to_float(cells[cust_start]) if cust_start < len(cells) else None
                    b_cus = _to_float(cells[cust_start + 1]) if cust_start + 1 < len(cells) else None
                    c_cus = _to_float(cells[cust_start + 2]) if cust_start + 2 < len(cells) else None
                    d_cus = _to_float(cells[cust_start + 3]) if cust_start + 3 < len(cells) else None

                    # Locate the code cell on the page for screenshot highlight (best-effort)
                    try:
                        def _norm(s: str) -> str:
                            return re.sub(r"[^A-Z0-9]", "", s.upper())
                        target = _norm(product_code) or _norm(base_code)
                        bbox = None
                        for w in page.extract_words() or []:
                            if _norm(w.get("text", "")) == target:
                                x0, y0, x1, y1 = w["x0"], w["top"], w["x1"], w["bottom"]
                                # convert to PNG pixel coords (dpi=300, PDF points=72/in)
                                scale = 300.0 / 72.0
                                # pdf y origin is top in extract_words (top/bottom)
                                x, y, width, height = int(x0 * scale), int(y0 * scale), int((x1 - x0) * scale), int((y1 - y0) * scale)
                                bbox = {"x": x, "y": y, "w": width, "h": height, "page": page_idx}
                                break
                    except Exception:
                        bbox = None

                    rec: Dict[str, Any] = {
                        "product_code": product_code,
                        "base_code": base_code,
                        "product_name_cn": name_text.replace("\n", " ").strip() or None,
                        "category": "泳镜",
                        "material_type": material,
                        "base_cost": base_cost,
                        "source_pdf": pdf.name,
                        "source_page": page_idx,
                        "row_label": row_label or None,
                        "screenshot_bbox": bbox,
                        # pricing columns expected by seeder
                        "A级_标准": a_std,
                        "B级_标准": b_std,
                        "C级_标准": c_std,
                        "D级_标准": d_std,
                        "A级_定制": a_cus,
                        "B级_定制": b_cus,
                        "C级_定制": c_cus,
                        "D级_定制": d_cus,
                    }
                    records.append(rec)

    # de-duplicate by product_code, keep first occurrence
    seen = set()
    uniq: List[Dict[str, Any]] = []
    for r in records:
        pc = r.get("product_code")
        if not pc or pc in seen:
            continue
        seen.add(pc)
        uniq.append(r)
    return uniq
