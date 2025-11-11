#!/usr/bin/env python
"""Generate PNG screenshots from PDFs (skeleton).

Requires poppler installed for pdf2image backend.
"""

from pathlib import Path
from typing import List, Dict

try:
    from pdf2image import convert_from_path
except Exception:  # pragma: no cover
    convert_from_path = None  # type: ignore


PDF_DIR = Path("data/pdfs")
OUT_DIR = Path("data/screenshots")
META_FILE = OUT_DIR / "metadata.json"


def render_pdf(pdf_path: Path, dpi: int = 300) -> List[Path]:
    if convert_from_path is None:
        raise RuntimeError("pdf2image not available. Install dependencies.")
    images = convert_from_path(str(pdf_path), dpi=dpi)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_files: List[Path] = []
    for i, img in enumerate(images, start=1):
        out = OUT_DIR / f"{pdf_path.stem}_page_{i}.png"
        img.save(out, "PNG", optimize=True)
        out_files.append(out)
    return out_files


def main() -> None:
    if not PDF_DIR.exists():
        print(f"No PDFs found at {PDF_DIR}")
        return
    pdfs = sorted(PDF_DIR.glob("*.pdf"))
    mapping: Dict[str, List[str]] = {}
    for pdf in pdfs:
        files = render_pdf(pdf)
        mapping[pdf.name] = [str(p.relative_to(OUT_DIR)) for p in files]
        print(f"Rendered {pdf.name}: {len(files)} pages")
    # write metadata
    import json
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps({"base_url": "/api/screenshot/", "files": mapping}, ensure_ascii=False, indent=2))
    print(f"Wrote metadata to {META_FILE}")


if __name__ == "__main__":
    main()
