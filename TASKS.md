# CostChecker Implementation Tasks

**Project Duration:** 16 days
**Start Date:** 2025-11-10
**Target Completion:** 2025-11-26

---

## Stage 1: PDF Data Extraction + Screenshot Generation
**Duration:** 4 days
**Goal:** Extract all 9 PDFs into PostgreSQL database with visual references

### Day 1: Project Setup & Database Schema

- [ ] **1.1 Project Initialization**
  - [x] Create project directory structure
  - [x] Initialize git repository
  - [x] Create `.gitignore` (exclude `data/screenshots/`, `logs/`, `.env`, `__pycache__/`)
  - [x] Create virtual environment: `python -m venv venv`
  - [x] Activate venv: `source venv/bin/activate`
  - [x] Create `requirements.txt` with all dependencies
  - [x] Install dependencies: `pip install -r requirements.txt`

- [ ] **1.2 Database Setup**
  - [x] Install PostgreSQL locally (or use Docker)
  - [x] Create database: `createdb costchecker`
  - [x] Initialize Alembic: `alembic init alembic`
  - [x] Configure `alembic.ini` with database URL
  - [x] Create initial migration with schema from IMPLEMENTATION_PLAN.md
  - [x] Run migration: `alembic upgrade head`
  - [x] Verify tables created: `psql costchecker -c "\dt"`

- [ ] **1.3 Configuration Management**
  - [x] Create `.env.example` with required variables
  - [x] Create `.env` with actual values (don't commit!)
  - [x] Create `app/core/config.py` using pydantic-settings
  - [x] Test config loading: `python -c "from app.core.config import settings; print(settings.DATABASE_URL)"`

### Day 2: PDF Extraction Engine

- [ ] **2.1 PDF Processing Setup**
  - [ ] Install system dependencies: `apt-get install poppler-utils` (for pdf2image)
  - [x] Create `scripts/extract_pdfs.py` skeleton
  - [x] Test pdfplumber on one sample PDF
  - [x] Verify table detection works

- [ ] **2.2 Product Code Parser**
  - [x] Create `app/utils/product_parser.py`
  - [x] Implement `extract_base_code(product_code)` function
    - [x] Extract base (e.g., "GT10S" → "GT10")
    - [x] Extract suffix (e.g., "GT10S" → "S")
  - [x] Implement `determine_material(product_code, material_column)` function
    - [x] If suffix "S" → SILICONE
    - [x] If suffix "P" → PVC
    - [x] Otherwise, use material_column
  - [x] Write unit tests for edge cases (GT10, GT-10S, GT 10 S)

- [ ] **2.3 Category-Specific Extractors**
  - [x] Create `scripts/extractors/` directory
  - [x] Implement `extractors/swimming_goggles.py` (泳镜)
    - [x] Parse table structure
    - [x] Extract columns: model, material, cost, A级标准, A级定制, B级标准, B级定制, etc.
    - [x] Handle merged cells
  - [x] Implement `extractors/swim_fins.py` (蛙鞋)
    - [x] Parse size variations (XXL, XL, M, S, XXS)
    - [x] Extract size ranges (44-46, 40-42)
  - [x] Implement `extractors/diving_masks.py` (潜水镜)
  - [x] Implement `extractors/snorkels.py` (呼吸管)
  - [x] Implement `extractors/caps.py` (帽子配件)

### Day 3: Data Validation & Screenshot Generation

- [ ] **3.1 Validation Framework**
  - [x] Create `app/utils/validation.py`
  - [x] Implement `validate_product(product_dict)`:
    - [x] Check required fields not null
    - [x] Verify suffix matches material (S→SILICONE, P→PVC)
    - [x] Check price ordering: Cost < A级 ≤ B级 ≤ C级 ≤ D级
    - [x] Verify 定制色 ≥ 标准色
  - [x] Return list of validation errors
  - [x] Write test cases for all validation rules

- [ ] **3.2 Screenshot Generation**
  - [x] Create `scripts/generate_screenshots.py`
  - [x] Implement PDF to PNG conversion (300 DPI)
    - [x] Use pdf2image: `convert_from_path(pdf_path, dpi=300)`
    - [x] Save to `data/screenshots/{pdf_name}_page_{N}.png`
  - [x] Create screenshot metadata mapping
    - [x] Map product → screenshot URL
    - [x] Store in database: `products.screenshot_url`
  - [x] Optimize PNG compression (reduce file size without quality loss)
  - [x] Test: Generate screenshots for one sample PDF

- [ ] **3.3 Validation Report Generator**
  - [x] Create `scripts/generate_validation_report.py`
  - [x] Extract all products and run validation
  - [x] Generate report: `data/reports/validation_{date}.txt`
  - [x] Format: List errors grouped by severity (ERROR, WARNING)
  - [x] Include statistics: total products, total errors, error rate

### Day 4: Full Extraction & Database Import

- [ ] **4.1 End-to-End Extraction Pipeline**
  - [x] Update `scripts/extract_pdfs.py` to process all 9 PDFs
  - [ ] For each PDF:
    - [x] Detect category (泳镜, 蛙鞋, etc.)
    - [x] Use appropriate extractor
    - [x] Validate extracted data
    - [x] Generate screenshots
  - [x] Collect all products into structured format (list of dicts)
  - [x] Run validation on all products
  - [x] Generate validation report

- [ ] **4.2 Database Import**
  - [x] Create `scripts/seed_database.py`
  - [x] Implement bulk insert:
    - [x] Start transaction
    - [x] Insert products (with screenshot URLs)
    - [x] Insert pricing_tiers (all A/B/C/D combinations)
    - [x] Insert product_sizes (for fins)
    - [x] Commit transaction (rollback on any error)
  - [x] Add logging: "Inserted 466 products, 1864 pricing tiers"

- [ ] **4.3 Manual Verification**
  - [ ] Query database: `SELECT COUNT(*) FROM products;` (should be ~466)
  - [ ] Randomly select 20 products
  - [ ] For each, compare database values with original PDF
  - [ ] Document accuracy: "18/20 exact match, 2/20 minor discrepancies"
  - [ ] Fix any systematic errors in extractors

**Stage 1 Success Criteria:**
- [ ] All 9 PDFs extracted (466 products in database)
- [ ] >95% accuracy verified manually (20 random samples)
- [ ] All products have screenshot URLs
- [ ] P/S suffix matches material_type 100%
- [ ] Validation report shows <5% error rate

---

## Stage 2: Advanced Fuzzy Matching Engine
**Duration:** 3 days
**Goal:** Handle typos and always confirm ambiguous queries

### Day 5: Fuzzy Matching Core

- [ ] **5.1 Product Code Normalization**
  - [x] Create `app/services/fuzzy_match.py`
  - [x] Implement `normalize_product_code(query)`:
    - [x] Remove whitespace: "GT 10S" → "GT10S"
    - [x] Remove hyphens: "GT-10S" → "GT10S"
    - [x] Uppercase: "gt10s" → "GT10S"
    - [x] Return normalized code
  - [ ] Write tests for 20+ variations

- [ ] **5.2 Matching Levels Implementation**
  - [x] Implement `exact_match(normalized_code)`:
    - [ ] Query: `SELECT * FROM products WHERE product_code = %s`
    - [x] Return confidence = 1.0
  - [x] Implement `base_code_match(normalized_code)`:
    - [ ] Extract base: "GT10S" → "GT10"
    - [ ] Query: `SELECT * FROM products WHERE base_code = %s`
    - [x] Return all matches (GT10S, GT10P) with confidence = 0.95
  - [x] Implement `fuzzy_string_match(normalized_code, threshold=0.85)`:
    - [x] Get all product codes from database
    - [x] Calculate Levenshtein similarity using rapidfuzz
    - [x] Return matches with similarity ≥ threshold
    - [x] Sort by confidence descending

- [ ] **5.3 Material Inference**
  - [x] Implement `infer_material_from_query(query)`:
    - [x] Detect keywords: "硅胶", "silicone", "矽膠" → SILICONE
    - [x] Detect keywords: "pvc", "PVC" → PVC
    - [x] Check suffix: ends with "S" → SILICONE, ends with "P" → PVC
    - [x] Return material or None
  - [x] Test with various queries: "GT10 硅胶", "GT10S", "GT10 PVC"

### Day 6: Confirmation Logic & Session Management

- [ ] **6.1 Confirmation Decision Engine**
  - [x] Implement `needs_confirmation(matches)`:
    - [x] If 0 matches → return False (will be error)
    - [x] If 1 match AND confidence = 1.0 → return False (direct response)
    - [x] If >1 match OR fuzzy match → return True
  - [x] Create confirmation ID generator: `generate_confirmation_id(user_session, timestamp)`
  - [x] Store confirmation state in Redis or database table:
    ```sql
    CREATE TABLE confirmation_sessions (
        confirmation_id VARCHAR(100) PRIMARY KEY,
        user_session VARCHAR(100),
        matches JSONB,
        created_at TIMESTAMP DEFAULT NOW(),
        expires_at TIMESTAMP
    );
    ```

- [ ] **6.2 Match Ranking & Presentation**
  - [x] Implement `rank_matches(matches, query)`:
    - [x] Sort by confidence descending
    - [x] Prefer material matches if material inferred from query
    - [x] Limit to top 5 matches
  - [x] Implement `format_confirmation_options(matches)`:
    - [x] Create user-friendly option list
    - [x] Include: product_code, material, category, confidence, match_reason
  - [x] Generate helpful match_reason messages:
    - [x] "移除了连字符" (removed hyphen)
    - [x] "模糊匹配" (fuzzy match)
    - [x] "找到基础代码的多个版本" (found multiple versions of base code)

### Day 7: Testing & Edge Cases

- [ ] **7.1 Test Suite for Fuzzy Matching**
  - [x] Create `tests/test_fuzzy_match.py`
  - [x] Test exact match: "GT10S" → GT10S (confidence: 1.0)
  - [x] Test case insensitive: "gt10s" → GT10S (confidence: 1.0)
  - [x] Test hyphen removal: "GT-10S" → GT10S
  - [x] Test space removal: "GT 10 S" → GT10S
  - [x] Test base code: "GT10" → [GT10S, GT10P] (confidence: 0.95 each)
  - [x] Test material inference: "GT10 硅胶" → SILICONE
  - [x] Test typos: "GT11" → GT10 variants (lower threshold)
  - [x] Test no match: "XYZ999" → [] (error)
  - [x] Test threshold: "GT99" vs "GT10" → below threshold, no match

- [ ] **7.2 Edge Cases**
  - [ ] Test products with no suffix: "F9970" (蛙鞋, no S/P)
  - [ ] Test similar codes: "GT10" vs "GT20" vs "GT30"
  - [ ] Test partial matches: "GT" → too many matches, error
  - [ ] Test special characters: "GT!10S" → normalize to "GT10S"
  - [ ] Test Chinese characters mixed: "GT10硅胶版" → extract "GT10", infer SILICONE

- [ ] **7.3 Performance Testing**
  - [ ] Benchmark fuzzy matching with 466 products
  - [ ] Target: <100ms for fuzzy string matching
  - [ ] Optimize: Create indexes on product_code and base_code
  - [ ] Consider: Cache frequently queried products in Redis

**Stage 2 Success Criteria:**
- [ ] 98% accuracy on 50 test variations (49/50 correct)
- [ ] Zero false positives verified manually
- [ ] Confirmation required for all ambiguous queries (100% tested)
- [ ] Performance: Fuzzy match completes in <100ms

---

## Stage 3: FastAPI with Text/Markdown Responses
**Duration:** 3 days
**Goal:** Production-ready API with clean text output and screenshot URLs

### Day 8: FastAPI Core & Query Endpoint

- [ ] **8.1 FastAPI Application Setup**
  - [x] Create `app/main.py`
  - [x] Initialize FastAPI app with metadata (title, version, description)
  - [x] Configure CORS middleware
  - [x] Add exception handlers (404, 500, validation errors)
  - [x] Create health check endpoint: `GET /api/health`
  - [x] Test: `uvicorn app.main:app --reload`

- [ ] **8.2 Database Connection**
  - [x] Create `app/core/database.py`
  - [x] Set up SQLAlchemy engine with connection pooling
  - [ ] Create async session maker (optional, use sync for simplicity)
  - [x] Create dependency: `get_db()` for FastAPI routes
  - [x] Test connection: Query one product from database

- [ ] **8.3 Pydantic Models (Request/Response)**
  - [x] Create `app/api/schemas.py`
  - [x] Define `QueryRequest`:
    ```python
    class QueryRequest(BaseModel):
        query: str
        user_session: str | None = None
        language: str = "zh"
    ```
  - [x] Define `QueryResponse` (success):
    ```python
    class QueryResponse(BaseModel):
        status: str  # "success"
        result_text: str
        result_markdown: str
        screenshot_url: str
        data: dict
        confidence: float
        execution_time_ms: int
    ```
  - [x] Define `ConfirmationResponse` (needs confirmation):
    ```python
    class ConfirmationOption(BaseModel):
        id: str
        product_code: str
        material: str
        category: str
        confidence: float
        match_reason: str

    class ConfirmationResponse(BaseModel):
        status: str  # "needs_confirmation"
        message: str
        options: list[ConfirmationOption]
        confirmation_id: str
        execution_time_ms: int
    ```
  - [x] Define `ErrorResponse`

### Day 9: DeepSeek Integration & Query Processing

- [ ] **9.1 DeepSeek API Client**
  - [x] Create `app/services/deepseek.py`
  - [x] Implement `DeepSeekClient` class
  - [x] Create system prompt (from IMPLEMENTATION_PLAN.md)
  - [x] Implement `extract_query_params(query: str) -> dict`:
    - [ ] Call DeepSeek API with query
    - [ ] Parse JSON response
    - [ ] Return: `{"product_code": "GT10S", "tier": "A级", "color_type": "定制色", ...}`
  - [ ] Handle API errors (timeout, invalid response)
  - [ ] Test with sample queries

- [ ] **9.2 Query Processor**
  - [x] Create `app/services/query_processor.py`
  - [x] Implement `process_query(query: str, db_session) -> QueryResult`:
    - [x] Step 1: Extract params using DeepSeek
    - [x] Step 2: Normalize product code
    - [x] Step 3: Fuzzy match products
    - [x] Step 4: Infer material if available
    - [x] Step 5: Filter by material if inferred
    - [x] Step 6: Check if confirmation needed
    - [x] Step 7: If direct match, fetch pricing data
    - [x] Step 8: Format response (text/markdown)
    - [x] Return result object

- [ ] **9.3 Response Formatter**
  - [x] Create `app/services/response_formatter.py`
  - [x] Implement `format_success_response(product, pricing, screenshot_url)`:
    - [x] Generate markdown text:
      ```markdown
      **产品：GT10S 儿童分体简易带扣 SILICONE**

      价格：$0.82 USD (A级定制色)

      来源：2025.10.28 泳镜.pdf (第2页)
      ```
    - [x] Include screenshot_url separately
    - [x] Return structured data dict
  - [x] Implement `format_confirmation_response(matches, confirmation_id)`
  - [x] Implement `format_error_response(error_type, message, suggestions)`

### Day 10: Confirmation Flow & Query Logging

- [ ] **10.1 Confirmation Endpoint**
  - [x] Create `POST /api/confirm` in `app/api/routes/query.py`
  - [x] Accept: `{"confirmation_id": "...", "selected_option": "1"}`
  - [x] Retrieve stored matches from confirmation_sessions table
  - [x] Validate confirmation_id not expired (<5 min)
  - [x] Get selected product from options
  - [x] Fetch full product data and pricing
  - [x] Format final response (same as success response)
  - [x] Clean up confirmation session

- [ ] **10.2 Query Logging**
  - [x] Create `app/services/logger.py`
  - [x] Implement `log_query(query_data) -> query_id`:
    - [x] Insert into query_logs table
    - [x] Include: query_text, fuzzy_matches, selected_product, result_text, screenshot_url, execution_time_ms, timestamp, user_session
    - [x] Return query_id
  - [x] Call logging in query endpoint (after response prepared)
  - [x] Handle logging errors gracefully (don't block response)

- [ ] **10.3 Screenshot Service**
  - [x] Create `GET /api/screenshot/{filename}` in `app/api/routes/screenshots.py`
  - [x] Serve static PNG files from `data/screenshots/`
  - [x] Set correct content-type: `image/png`
  - [x] Add cache headers: `Cache-Control: public, max-age=86400`
  - [x] Handle 404 if file not found
  - [x] Test: Access screenshot URL in browser

**Stage 3 Success Criteria:**
- [ ] API responds <1s for 95% of test queries (measure with 100 requests)
- [ ] 100% of queries logged to database (verify count)
- [ ] Text/markdown output clean and readable (manual review)
- [ ] Screenshots served successfully (test 10 URLs)
- [ ] Confirmation flow works end-to-end (test with "GT10" query)

---

## Stage 4: Plain HTML Admin Dashboard
**Duration:** 2 days
**Goal:** Simple internal analytics dashboard (backend-only, password protected)

### Day 11: Admin Analytics Endpoints

- [ ] **11.1 Authentication Middleware**
  - [x] Create `app/core/security.py`
  - [x] Implement HTTP Basic Auth
  - [x] Store credentials in environment variables
  - [x] Create dependency: `verify_admin(credentials: HTTPBasicCredentials)`
  - [x] Add to admin endpoints: `dependencies=[Depends(verify_admin)]`

- [ ] **11.2 Query History Endpoint**
  - [x] Create `GET /api/analytics/queries` in `app/api/routes/analytics.py`
  - [x] Accept query params: limit, offset, start_date, end_date, status
  - [x] Query database: `SELECT * FROM query_logs WHERE ... ORDER BY timestamp DESC LIMIT %s OFFSET %s`
  - [x] Return paginated results
  - [x] Test: `curl -u admin:password http://localhost:8000/api/analytics/queries?limit=10`

- [ ] **11.3 Statistics Endpoint**
  - [x] Create `GET /api/analytics/stats`
  - [x] Accept query param: days (default: 7)
  - [x] Calculate metrics:
    - [x] Total queries (last N days)
    - [x] Success rate: `successful_queries / total_queries`
    - [x] Avg response time: `AVG(execution_time_ms)`
    - [x] Confirmation rate: `COUNT(confirmation_required=true) / total`
    - [x] Top 10 products: `SELECT selected_product, COUNT(*) GROUP BY selected_product ORDER BY COUNT(*) DESC LIMIT 10`
    - [x] Common errors: `SELECT error_message, COUNT(*) GROUP BY error_message`
  - [x] Return JSON with all metrics
  - [ ] Test endpoint

### Day 12: Admin HTML Pages

- [ ] **12.1 Dashboard Structure**
  - [x] Create `admin/` directory
  - [x] Create `admin/index.html` (landing page with links)
  - [x] Create `admin/queries.html` (query monitor)
  - [x] Create `admin/analytics.html` (statistics)
  - [x] Create `admin/data.html` (data quality)
  - [x] Create `admin/static/css/style.css` (minimal styling)
  - [x] Create `admin/static/js/main.js` (shared utilities)

- [ ] **12.2 Query Monitor Page**
  - [x] HTML table with columns: Time, Query, Product, Response Time, Status
  - [x] JavaScript to fetch `/api/analytics/queries?limit=100`
  - [x] Render table rows dynamically
  - [x] Color-code status: green (success), red (error), yellow (confirmation)
  - [x] Add date range filter (start_date, end_date inputs)
  - [x] Add "Export CSV" button:
    - [x] Convert table data to CSV format
    - [x] Trigger download: `data:text/csv;charset=utf-8,...`
  - [x] Auto-refresh every 30 seconds: `setInterval(loadQueries, 30000)`

- [ ] **12.3 Analytics Page**
  - [x] Fetch `/api/analytics/stats?days=7`
  - [x] Display metric cards:
    ```
    ┌─────────────┬─────────────┬─────────────┐
    │ Total       │ Success     │ Avg Time    │
    │ Queries     │ Rate        │             │
    │ 1,247       │ 94.3%       │ 342ms       │
    └─────────────┴─────────────┴─────────────┘
    ```
  - [x] Display top 10 products as simple list:
    ```
    1. GT10S - 45 queries
    2. F9970 - 32 queries
    ...
    ```
  - [x] Display common errors (if any)
  - [x] No charts needed, just plain text/tables

- [ ] **12.4 Data Quality Page**
  - [x] Query database for counts:
    - [x] `SELECT COUNT(*) FROM products`
    - [x] `SELECT category, COUNT(*) FROM products GROUP BY category`
    - [x] `SELECT COUNT(*) FROM products WHERE screenshot_url IS NOT NULL`
  - [x] Display:
    ```
    Database Status
    ===============
    Last Updated: 2025-10-28
    Total Products: 466
    Products with Screenshots: 466 (100%)

    Product Breakdown:
    - 泳镜: 150 SKUs
    - 蛙鞋: 100 SKUs
    ...
    ```

- [ ] **12.5 Static File Serving**
  - [x] Mount admin directory in FastAPI:
    ```python
    from fastapi.staticfiles import StaticFiles
    app.mount("/admin", StaticFiles(directory="admin", html=True), name="admin")
    ```
  - [x] Test: Access `http://localhost:8000/admin/`
  - [x] Verify auth required

**Stage 4 Success Criteria:**
- [ ] Dashboard loads <2s (test with browser dev tools)
- [ ] CSV export downloads correctly
- [ ] Auth protects all admin pages (test without credentials → 401)
- [ ] Auto-refresh works (verify table updates after 30s)
- [ ] All metrics display correctly

---

## Stage 5: Re-extraction & Update Pipeline
**Duration:** 2 days
**Goal:** Handle half-yearly price updates reliably

### Day 13: Diff Generation & Price Comparison

- [ ] **13.1 Price Diff Calculator**
  - [ ] Create `scripts/generate_diff_report.py`
  - [ ] Accept two directories: `old_pdfs/` and `new_pdfs/`
  - [ ] Extract both sets of PDFs
  - [ ] Compare products:
    - [ ] Match by product_code
    - [ ] For each pricing tier, calculate: `new_price - old_price`
    - [ ] Calculate percentage change: `(new - old) / old * 100`
  - [ ] Identify:
    - [ ] Price changes (list all, highlight >10% changes)
    - [ ] New products (in new but not in old)
    - [ ] Discontinued products (in old but not in new)

- [ ] **13.2 Diff Report Format**
  - [ ] Generate text report: `data/reports/price_diff_{date}.txt`
  - [ ] Format:
    ```
    Price Update Report - 2025-04-28
    ================================

    SUMMARY:
    - Total products in old: 466
    - Total products in new: 475
    - Price changes: 34
    - New products: 12
    - Discontinued: 3

    PRICE CHANGES (>5% only):
    - GT10S A级定制色: $0.82 → $0.88 (+$0.06, +7.3%) ⚠️
    - F9970 XXL Cost: $3.20 → $3.35 (+$0.15, +4.7%)

    NEW PRODUCTS:
    - GT75S (泳镜 - 新款)
    - SN9999P (呼吸管)
    ...

    DISCONTINUED:
    - GT01 (泳镜 - 模具损坏)
    - ...

    ALL PRICE CHANGES (including <5%):
    [Full list...]
    ```
  - [ ] Also generate CSV: `data/reports/price_diff_{date}.csv` for Excel analysis

### Day 14: Atomic Update & Rollback

- [ ] **14.1 Update Application Script**
  - [ ] Create `scripts/apply_updates.py`
  - [ ] Accept: `--diff-report` path (must review report first!)
  - [ ] Require manual approval: `--approve` flag
  - [ ] If not approved, show report and exit
  - [ ] Extract new PDFs
  - [ ] Generate new screenshots
  - [ ] Start database transaction:
    ```python
    with db.begin():
        # Backup current pricing to pricing_history
        # Update existing products (prices)
        # Insert new products
        # Mark discontinued products (status='discontinued')
        # Update screenshot URLs if changed
    # Commit (or rollback on error)
    ```

- [ ] **14.2 Rollback Mechanism**
  - [ ] If transaction fails, all changes are automatically rolled back
  - [ ] Additionally, create manual rollback script: `scripts/rollback_update.py`
  - [ ] Accept: `--to-date` (restore to specific date)
  - [ ] Use pricing_history table to restore old prices
  - [ ] Re-extract old PDFs from backup

- [ ] **14.3 Testing Update Process**
  - [ ] Create test PDFs (modify a few prices manually)
  - [ ] Run diff report: `python scripts/generate_diff_report.py --old=data/pdfs/ --new=data/test_pdfs/`
  - [ ] Review report manually
  - [ ] Apply updates: `python scripts/apply_updates.py --diff-report=data/reports/price_diff_test.txt --approve`
  - [ ] Verify changes in database
  - [ ] Test rollback: `python scripts/rollback_update.py --to-date=2025-11-10`
  - [ ] Verify restored to original state

**Stage 5 Success Criteria:**
- [ ] Diff report shows all changes accurately (test with modified PDFs)
- [ ] Update completes without errors
- [ ] Zero downtime (database remains accessible during update)
- [ ] Rollback successfully restores old data
- [ ] Price history table records all changes

---

## Stage 6: Deployment to Tencent CloudBase
**Duration:** 2 days
**Goal:** Production deployment on TCB

### Day 15: TCB Environment Setup & Database Deployment

- [ ] **15.1 TCB Account Setup**
  - [ ] Create Tencent Cloud account (if not exists)
  - [ ] Enable CloudBase service
  - [ ] Create new environment: `costchecker-prod`
  - [ ] Note environment ID and region

- [ ] **15.2 Database Deployment**
  - [ ] **Option A: TCB Cloud Database for PostgreSQL**
    - [ ] Create PostgreSQL instance in TCB console
    - [ ] Configure instance: 1 core, 2GB memory (adjust as needed)
    - [ ] Note connection details (host, port, username, password)
  - [ ] **Option B: External PostgreSQL**
    - [ ] Use external provider (e.g., Supabase, Railway)
    - [ ] Get connection URL
  - [ ] Connect from local: `psql <connection_url>`
  - [ ] Run migrations: `alembic upgrade head`
  - [ ] Import data: `python scripts/seed_database.py` (using production DB URL)
  - [ ] Verify: `SELECT COUNT(*) FROM products;`

- [ ] **15.3 Cloud Storage for Screenshots**
  - [ ] Create TCB Cloud Storage bucket: `costchecker-screenshots`
  - [ ] Upload all screenshots: `tcb storage upload data/screenshots/ --remote-path=/screenshots/`
  - [ ] Set public read permissions
  - [ ] Get CDN URL: `https://xxxxxx.tcb.qcloud.la/screenshots/`
  - [ ] Update database screenshot_url column to use CDN URLs:
    ```sql
    UPDATE products
    SET screenshot_url = REPLACE(screenshot_url, '/data/screenshots/', 'https://xxxxxx.tcb.qcloud.la/screenshots/');
    ```
  - [ ] Test: Access one screenshot URL in browser

### Day 16: Application Deployment & Final Testing

- [ ] **16.1 Dockerize Application (Optional but Recommended)**
  - [ ] Create `Dockerfile`:
    ```dockerfile
    FROM python:3.11-slim
    WORKDIR /app
    COPY requirements.txt .
    RUN pip install --no-cache-dir -r requirements.txt
    COPY . .
    EXPOSE 8000
    CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
    ```
  - [ ] Build image: `docker build -t costchecker-api .`
  - [ ] Test locally: `docker run -p 8000:8000 --env-file .env costchecker-api`

- [ ] **16.2 Deploy to TCB**
  - [ ] **Option A: Cloud Run (Container-based)**
    - [ ] Push Docker image to TCB Container Registry
    - [ ] Deploy to Cloud Run service
    - [ ] Configure environment variables in TCB console
  - [ ] **Option B: Direct Deployment**
    - [ ] Package app: `zip -r app.zip app/ admin/ scripts/ requirements.txt`
    - [ ] Upload to TCB
    - [ ] Install dependencies: `pip install -r requirements.txt`
    - [ ] Start service: `uvicorn app.main:app --host 0.0.0.0 --port 8000`

- [ ] **16.3 Environment Variables Configuration**
  - [ ] Set in TCB console:
    ```
    DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
    DATABASE_URL=postgresql://user:pass@host:5432/costchecker
    SCREENSHOT_BASE_URL=https://xxxxxx.tcb.qcloud.la/screenshots/
    ADMIN_USERNAME=admin
    ADMIN_PASSWORD=<strong_password>
    CORS_ORIGINS=*
    ```

- [ ] **16.4 Domain & SSL Setup**
  - [ ] Configure custom domain (if desired): `api.costchecker.example.com`
  - [ ] Enable HTTPS (TCB auto SSL)
  - [ ] Update CORS_ORIGINS with actual domain

- [ ] **16.5 End-to-End Production Testing**
  - [ ] Test API health: `curl https://api.costchecker.example.com/api/health`
  - [ ] Test query endpoint:
    ```bash
    curl -X POST https://api.costchecker.example.com/api/query \
      -H "Content-Type: application/json" \
      -d '{"query": "GT10S A级定制色"}'
    ```
  - [ ] Verify response includes screenshot URL
  - [ ] Test screenshot loading: Open URL in browser
  - [ ] Test confirmation flow: Query "GT10" → confirm → get result
  - [ ] Test admin dashboard: `https://api.costchecker.example.com/admin/`
  - [ ] Verify auth required (401 without credentials)
  - [ ] Login with admin credentials
  - [ ] Check query monitor, analytics, data quality pages
  - [ ] Export CSV and verify data

- [ ] **16.6 Performance & Monitoring**
  - [ ] Run load test: 100 concurrent requests using `ab` or `wrk`
  - [ ] Verify: 95% of requests < 1s
  - [ ] Set up basic monitoring (TCB built-in or external)
  - [ ] Configure alerts:
    - [ ] Error rate > 10%
    - [ ] Response time > 2s
    - [ ] Database connection failures

- [ ] **16.7 Documentation & Handoff**
  - [ ] Update README.md with:
    - [ ] API base URL
    - [ ] Admin dashboard URL
    - [ ] Sample queries
    - [ ] Environment variables needed
    - [ ] Deployment instructions
  - [ ] Create user guide (Chinese):
    - [ ] How to query prices
    - [ ] Confirmation flow explanation
    - [ ] Screenshot interpretation
  - [ ] Create admin guide:
    - [ ] How to access dashboard
    - [ ] How to export data
    - [ ] How to update prices (run scripts)

**Stage 6 Success Criteria:**
- [ ] API accessible at production URL
- [ ] Health check returns 200 OK
- [ ] End-to-end query works (test 10 queries)
- [ ] Screenshots load from CDN (<500ms)
- [ ] Admin dashboard accessible with password
- [ ] Load test shows 95% < 1s response time
- [ ] Documentation complete

---

## Post-Deployment Tasks

- [ ] **Monitoring Setup**
  - [ ] Set up logging aggregation (CloudWatch, Datadog, etc.)
  - [ ] Create dashboards for key metrics
  - [ ] Configure alerts

- [ ] **Backup Strategy**
  - [ ] Automated daily database backups
  - [ ] Store backups for 30 days
  - [ ] Test restore procedure

- [ ] **Maintenance Plan**
  - [ ] Schedule monthly data quality review
  - [ ] Plan for next price update (6 months)
  - [ ] Monitor DeepSeek API usage and costs

---

## Summary Checklist

### Stage 1: PDF Extraction ✅
- [ ] All 9 PDFs extracted (466 products)
- [ ] >95% accuracy verified
- [ ] Screenshots generated
- [ ] Database seeded

### Stage 2: Fuzzy Matching ✅
- [ ] 98% test accuracy (50 variations)
- [ ] Zero false positives
- [ ] Confirmation logic working

### Stage 3: FastAPI ✅
- [ ] API responds <1s
- [ ] Query logging 100%
- [ ] Text/markdown output clean
- [ ] Screenshots served

### Stage 4: Admin Dashboard ✅
- [ ] Dashboard loads <2s
- [ ] CSV export works
- [ ] Auth protects pages

### Stage 5: Update Pipeline ✅
- [ ] Diff report accurate
- [ ] Update + rollback tested

### Stage 6: Deployment ✅
- [ ] Production API live
- [ ] End-to-end tested
- [ ] Documentation complete

**Project Status:** [ ] Not Started  [x] In Progress  [ ] Completed

---

## Notes & Issues Log

*Use this section to track any blockers, decisions, or important notes during implementation.*

### 2025-11-10
- Project initialized
- IMPLEMENTATION_PLAN.md created
- TASKS.md created
- Ready to begin Stage 1
  
Progress update (scaffold completed):
- Added project skeleton: config, database, models, utils, scripts
- Alembic initialized (env reads `DATABASE_URL` from `.env`)
- Added `docker-compose.yml` for local PostgreSQL 15
- Copied 9 source PDFs into `data/pdfs/`
- FastAPI app scaffolded with `GET /api/health`
- Implemented `product_parser` and initial `validation` utilities
- Added basic tests for `product_parser`

Runtime progress (automation + E2E checks):
- Ran Alembic migrations (0001, 0002); verified tables with psql.
- Fixed script import path issues (`scripts/__init__.py` + sys.path in `extract_pdfs.py`).
- Extracted all 9 PDFs; wrote `data/reports/products.jsonl` and aggregated `data/extracted/products.json`.
- Installed poppler via Homebrew; generated screenshots for all PDFs; wrote `data/screenshots/metadata.json`.
- Seeded database with products, pricing tiers, and sizes.
- Updated validation report to group by severity; generated `data/reports/validation_*.txt`.
- Started FastAPI with uvicorn; verified `/api/health` OK.
- Verified query flow: sample `GT10S A级定制色` returns success with screenshot URL.
- Verified screenshot service `GET /api/screenshot/{filename}` returns 200.
- Verified admin analytics endpoints (Basic Auth) and `/admin` static pages.
