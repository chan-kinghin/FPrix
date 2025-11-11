"""潜水镜 (diving masks) extractor parsing structured price tables."""

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
        last_map: Optional[_ColumnMap] = None
        for page_idx, page in enumerate(doc.pages, start=1):
            try:
                tables = page.extract_tables() or []
            except Exception:
                tables = []

            for table in tables:
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
                    if last_map is None:
                        continue
                    colmap = last_map
                    data_rows = table
                else:
                    data_rows = table[header_idx + 1 :]

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
                    base_code, suffix = extract_base_code(raw_code)
                    name_text = cells[name_idx] if name_idx < len(cells) else ""
                    row_label = (cells[0] or "").strip()
                    # If suffix missing, infer from name + leftmost label
                    material = determine_material(base_code + (suffix or ""), f"{name_text} {row_label}".strip())
                    if suffix is None and material in ("SILICONE", "PVC"):
                        suffix = "S" if material == "SILICONE" else "P"
                    product_code = f"{base_code}{suffix or ''}"

                    base_cost = _to_float(cells[cost_idx]) if cost_idx is not None and cost_idx < len(cells) else None
                    a_std = _to_float(cells[std_start]) if std_start < len(cells) else None
                    b_std = _to_float(cells[std_start + 1]) if std_start + 1 < len(cells) else None
                    c_std = _to_float(cells[std_start + 2]) if std_start + 2 < len(cells) else None
                    d_std = _to_float(cells[std_start + 3]) if std_start + 3 < len(cells) else None
                    a_cus = _to_float(cells[cust_start]) if cust_start < len(cells) else None
                    b_cus = _to_float(cells[cust_start + 1]) if cust_start + 1 < len(cells) else None
                    c_cus = _to_float(cells[cust_start + 2]) if cust_start + 2 < len(cells) else None
                    d_cus = _to_float(cells[cust_start + 3]) if cust_start + 3 < len(cells) else None

                    # Best-effort highlight bbox for code cell
                    try:
                        def _norm(s: str) -> str:
                            return re.sub(r"[^A-Z0-9]", "", s.upper())
                        target = _norm(product_code) or _norm(base_code)
                        bbox = None
                        for w in page.extract_words() or []:
                            if _norm(w.get("text", "")) == target:
                                x0, y0, x1, y1 = w["x0"], w["top"], w["x1"], w["bottom"]
                                scale = 300.0 / 72.0
                                x, y, width, height = int(x0 * scale), int(y0 * scale), int((x1 - x0) * scale), int((y1 - y0) * scale)
                                bbox = {"x": x, "y": y, "w": width, "h": height, "page": page_idx}
                                break
                    except Exception:
                        bbox = None

                    rec: Dict[str, Any] = {
                        "product_code": product_code,
                        "base_code": base_code,
                        "product_name_cn": name_text.replace("\n", " ").strip() or None,
                        "category": "潜水镜",
                        "material_type": material,
                        "base_cost": base_cost,
                        "source_pdf": pdf.name,
                        "source_page": page_idx,
                        "row_label": row_label or None,
                        "screenshot_bbox": bbox,
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

    seen = set()
    unique: List[Dict[str, Any]] = []
    for r in records:
        pc = r.get("product_code")
        if not pc or pc in seen:
            continue
        seen.add(pc)
        unique.append(r)
    return unique
