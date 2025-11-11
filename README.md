# CostChecker

FastAPI service for Chinese price queries with fuzzy matching, PDF extraction, and a plain admin dashboard.

## Quickstart

1) Create and fill `.env` from `.env.example` (note `CORS_ORIGINS` must be JSON, e.g. `["*"]`).
2) Create virtualenv and install deps:
   - `python3 -m venv venv && source venv/bin/activate`
   - `pip install -r requirements.txt`
3) Start PostgreSQL 15 via Docker:
   - `docker compose up -d db`
   - Port mapping: host `6543` -> container `5432` (see `docker-compose.yml`)
   - Connection URL default: `postgresql+psycopg2://postgres:postgres@127.0.0.1:6543/costchecker`
   - Verify DB in container: `docker exec -it costchecker-postgres psql -U postgres -c "\\l"`
4) Apply database migrations with Alembic (migrations already included):
   - `PYTHONPATH=. alembic upgrade head`
   - If you see `role "postgres" does not exist`, ensure you are connecting to the Docker DB on `127.0.0.1:6543` and the role exists in the container.
5) Run tests: `pytest -q`
6) Run API: `uvicorn app.main:app --reload`

API health check: `GET http://127.0.0.1:8000/api/health`

## What’s New (Extraction + Highlight)

- Unified extraction across categories (泳镜/呼吸管/潜水镜/蛙鞋/帽子配件):
  - Reuses detected header mapping across page breaks (no header on next page won’t block parsing).
  - Captures the leftmost column label per row and stores it as `Product.subcategory` (e.g., 儿童款/成人款/成人包胶款)。
  - Adds best-effort screenshot highlight for the code cell. Response now includes a `data.highlight` block:
    - `{ filename, x, y, w, h, page }` in pixels at 300 DPI, origin top-left.
  - Material inference updated to include TPE/包胶；并内置规则：`GT61` → 成人包胶款，材质 `TPE`。

- Seeder updates:
  - Updates existing `subcategory`、`material_type`、`notes`（包含 highlight 元数据）以便重复导入时修正数据。

## Prerequisites

- Python 3.9+ (tested on 3.9)
- Poppler utilities (for `pdf2image` screenshots)
- Docker (for local PostgreSQL)

Optional macOS note: if `pdf2image` cannot find poppler, pass `poppler_path` to `convert_from_path` or add poppler to PATH (Homebrew installs to `/opt/homebrew/bin`).

## API Reference (implemented)

- `POST /api/query` — Process a natural language query and return price info or confirmation options.
- `POST /api/confirm` — Confirmation flow using an in-memory store (5-minute TTL).
- `GET /api/screenshot/{filename}` — Serves PNG screenshots from `data/screenshots/` with cache headers.
- `GET /api/health` — Basic health status.

Analytics (HTTP Basic Auth):
- `GET /api/analytics/queries` — Query history (limit/offset/date filters).
- `GET /api/analytics/stats` — Metrics: totals, success rate, avg time, confirmation rate, top products, common errors.
- `GET /api/analytics/data_quality` — Product counts, per-category breakdown, screenshot coverage.

Admin (HTTP Basic Auth, use `ADMIN_USERNAME`/`ADMIN_PASSWORD`):
- `GET /api/analytics/queries` — Query history (limit/offset/date filters).
- `GET /api/analytics/stats` — Simple stats for last N days.
- `GET /api/analytics/data_quality` — Data quality overview.
- Static admin UI at `/admin` (protected).

Example request:
```
curl -X POST http://127.0.0.1:8000/api/query \
  -H 'Content-Type: application/json' \
  -d '{"query":"GT10S A级定制色"}'
```

### Playground UI (no auth)

- Open http://127.0.0.1:8000/playground/
- Type a query (e.g., `GT63 A级 定制色`) and click 查询
- The page shows raw JSON on the left and the screenshot on the right with overlay boxes:
  - Red box: code cell
  - Green box: price cell (when a tier/color is present)
- If the response needs confirmation, options will appear as clickable chips.

Admin API with Basic Auth:
```
curl -u admin:change-me 'http://127.0.0.1:8000/api/analytics/queries?limit=10'
```

### Response fields of interest

On success, the response contains a `data` object. New/important fields:

- `product_code`, `material`, `category`, `subcategory`
- `tier`, `color_type`, `price`
- `source.pdf`, `source.page`
- `highlight` (optional): `{ filename, x, y, w, h, page }`
  - Pixel coordinates for the code cell bounding box on the screenshot (300 DPI). Use to overlay a highlight rectangle.

## PDF and Screenshots

- Place source PDFs under `data/pdfs/`.
- Generate screenshots (requires poppler + pdf2image):
  - macOS: `brew install poppler`
  - Ubuntu/Debian: `sudo apt-get install -y poppler-utils`
  - `python scripts/generate_screenshots.py`
  - Outputs PNGs and `data/screenshots/metadata.json`.
  - Screenshot mapping: filenames follow `{pdf_name}_page_{N}.png`; the seeder derives `products.screenshot_url` from `source_pdf` + `source_page` if missing.
  - Highlight usage: draw a rectangle at `(x,y)` with size `(w,h)` on `filename` returned in `data.highlight`.

## Development Commands

- Start DB: `docker compose up -d db`
- Create migration: `PYTHONPATH=. alembic revision --autogenerate -m "init schema"`
- Apply migration: `PYTHONPATH=. alembic upgrade head`
- Run tests: `pytest -q`
- Run API: `uvicorn app.main:app --reload`

## Configuration

Environment variables (see `.env.example`):
- `DATABASE_URL` — SQLAlchemy URL for PostgreSQL.
- `DEEPSEEK_API_KEY` — If set, the service calls DeepSeek `chat/completions` to parse queries; if unset or a placeholder, it falls back to a fast heuristic parser.
- `ADMIN_USERNAME` / `ADMIN_PASSWORD` — Basic auth for admin and analytics endpoints.
- `CORS_ORIGINS` — JSON array of allowed origins (e.g. `["*"]`).

## Troubleshooting

- Postgres error `role "postgres" does not exist`: ensure you are connecting to the Docker DB at `127.0.0.1:6543`; check with `docker exec -it costchecker-postgres psql -U postgres -c "\\du"`.
- `CORS_ORIGINS` parsing error: must be JSON (e.g. `["*"]`), not a bare `*`.
- `pdf2image` errors: install poppler (`brew install poppler` or `apt-get install -y poppler-utils`) and ensure it’s on PATH.

- 500 errors on wide-search (e.g., “最贵的/便宜的/比X贵/便宜”): run `PYTHONPATH=. alembic upgrade head`. Migration `0003_wide_search_sql.py` defines the `pick_price(pid, tier, color)` function used by these queries.
- Restart sequence (safe): stop server `pkill -f "uvicorn app.main:app"`, restart DB `docker restart costchecker-postgres`, apply migrations `PYTHONPATH=. alembic upgrade head`, start server `uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload`.
- Health check: `curl http://127.0.0.1:8000/api/health`; logs: `tail -n 100 logs/server.log` (if you redirect logs there).

## Current Progress

Implemented:
- App scaffolding, CORS, error handlers, health endpoint.
- Request/response schemas, query processing (heuristic DeepSeek parser).
- Fuzzy matching utilities: normalization, exact/base/fuzzy matches; tests.
- Confirmation endpoint with in-memory session store (5-minute TTL).
- Category extractors (heuristic) + extraction pipeline, validation hook, aggregated export.
- Extractors unified: cross-page header reuse, leftmost column -> `subcategory`, best-effort code-cell highlight.
- Seeder: products, pricing tiers (A/B/C/D × 标准/定制), fins sizes; screenshot URL mapping; highlight metadata in `notes`; upserts subcategory/material.
- Screenshot service, analytics endpoints (queries, stats, data quality) and admin HTML pages.
- Validation utilities and tests; screenshot metadata generation.

Pending highlights (see TASKS.md for full list):
- Confirmation session persistence (Redis/DB) and confirmation decision heuristics.
- DeepSeek API integration (real API call + error handling).
- Performance benchmarking and indexing/caching.
- Deployment and re-extraction/update pipeline scripts.

## Data Pipeline

End-to-end steps to populate the DB from PDFs:
- Ensure PDFs are present under `data/pdfs/`.
- Generate screenshots: `python scripts/generate_screenshots.py`.
- Run extraction: `python scripts/extract_pdfs.py`.
  - Outputs per-PDF `data/reports/products.jsonl` and aggregated `data/extracted/products.json`.
  - Prints basic validation counts per PDF.
- Seed DB: `python scripts/seed_database.py`.
  - Prints counts of inserted products, pricing tiers, sizes.
  - Re-seeding updates `subcategory`, `material_type` and `notes` (highlight metadata) if present.

Verify data via admin endpoints (Basic Auth):
- `curl -u admin:change-me 'http://127.0.0.1:8000/api/analytics/data_quality'`
- `curl -u admin:change-me 'http://127.0.0.1:8000/api/analytics/stats?days=7'`

## Structure

See `IMPLEMENTATION_PLAN.md` and `TASKS.md` for details.

Key paths:
- `data/pdfs/` — source PDFs
- `data/screenshots/` — generated PNGs (+ metadata)
- `data/reports/` — validation/diff reports
- `scripts/` — extraction, screenshots, seeding, utils
- `app/` — API, models, services, utils
