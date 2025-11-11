# CostChecker: Natural Language Price Query System

## Project Overview

**Goal:** Build a robust natural language query API for Chinese price lists using DeepSeek LLM, with advanced fuzzy matching, visual PDF references, and comprehensive analytics.

**Deployment Target:** Tencent CloudBase (TCB)

---

## System Architecture

### Tech Stack

**Backend:**
- **Language:** Python 3.11+
- **API Framework:** FastAPI (async, high performance)
- **Database:** PostgreSQL 15+ (structured data, JSONB support)
- **LLM:** DeepSeek API (Chinese-optimized, cost-effective)
- **Fuzzy Matching:** rapidfuzz (Levenshtein distance)
- **PDF Processing:** pdfplumber (table extraction), pdf2image (screenshots)

**Frontend (Admin Only):**
- Plain HTML + CSS + JavaScript
- Bootstrap 5 (CDN)
- HTTP Basic Auth

**Deployment:**
- Tencent CloudBase
- Docker containerization (optional)
- TCB Cloud Storage for screenshots

---

## Data Architecture

### Database Schema

```sql
-- Core product table
CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    product_code VARCHAR(20) UNIQUE NOT NULL,  -- e.g., "GT10S", "GT10P"
    base_code VARCHAR(20) NOT NULL,            -- e.g., "GT10" (without suffix)
    product_name_cn VARCHAR(200),
    category VARCHAR(50) NOT NULL,             -- "泳镜", "蛙鞋", etc.
    subcategory VARCHAR(100),
    material_type VARCHAR(20) NOT NULL,        -- "SILICONE" or "PVC"
    base_cost DECIMAL(10,2) NOT NULL,
    net_weight_grams INT,
    status VARCHAR(20) DEFAULT 'active',       -- "active", "discontinued"
    source_pdf VARCHAR(200) NOT NULL,
    source_page INT NOT NULL,
    screenshot_url TEXT,                       -- URL to PDF page screenshot
    notes TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_product_code ON products(product_code);
CREATE INDEX idx_base_code ON products(base_code);
CREATE INDEX idx_category ON products(category);
CREATE INDEX idx_material ON products(material_type);

-- Pricing tiers
CREATE TABLE pricing_tiers (
    pricing_id SERIAL PRIMARY KEY,
    product_id INT REFERENCES products(product_id) ON DELETE CASCADE,
    tier VARCHAR(10) NOT NULL,                 -- "A级", "B级", "C级", "D级"
    color_type VARCHAR(20) NOT NULL,           -- "标准色", "定制色"
    price DECIMAL(10,2) NOT NULL,
    effective_date DATE DEFAULT CURRENT_DATE,

    UNIQUE(product_id, tier, color_type, effective_date)
);

CREATE INDEX idx_pricing_product ON pricing_tiers(product_id);

-- Product sizes (for fins)
CREATE TABLE product_sizes (
    size_id SERIAL PRIMARY KEY,
    product_id INT REFERENCES products(product_id) ON DELETE CASCADE,
    size_code VARCHAR(10) NOT NULL,            -- "XXL", "XL", "M", "S"
    size_range VARCHAR(20),                    -- "44-46", "40-42"
    cost_adjustment DECIMAL(10,2) DEFAULT 0,

    UNIQUE(product_id, size_code)
);

-- Query logging
CREATE TABLE query_logs (
    query_id SERIAL PRIMARY KEY,
    query_text TEXT NOT NULL,                  -- Original Chinese query
    normalized_query TEXT,                     -- Normalized version
    query_classification VARCHAR(50),          -- "product_lookup", "price_comparison"
    fuzzy_matches JSONB,                       -- All candidates found
    selected_product VARCHAR(20),              -- Final choice after confirmation
    confirmation_required BOOLEAN DEFAULT FALSE,
    user_confirmed BOOLEAN DEFAULT FALSE,
    sql_generated TEXT,                        -- Generated SQL (if applicable)
    result_text TEXT,                          -- Markdown response
    result_data JSONB,                         -- Structured result
    screenshot_url TEXT,                       -- Screenshot shown
    confidence_score DECIMAL(3,2),             -- 0.00 to 1.00
    execution_time_ms INT,
    success BOOLEAN DEFAULT TRUE,
    error_message TEXT,
    user_session VARCHAR(100),
    ip_address VARCHAR(45),
    timestamp TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_query_timestamp ON query_logs(timestamp);
CREATE INDEX idx_query_product ON query_logs(selected_product);
CREATE INDEX idx_query_session ON query_logs(user_session);

-- Aggregated daily metrics (for fast dashboard loading)
CREATE TABLE daily_metrics (
    date DATE PRIMARY KEY,
    total_queries INT DEFAULT 0,
    successful_queries INT DEFAULT 0,
    failed_queries INT DEFAULT 0,
    avg_response_time_ms INT,
    confirmation_rate DECIMAL(5,2),            -- % requiring confirmation
    unique_users INT DEFAULT 0,
    top_products JSONB                         -- Cache top 10 products
);

-- Price history (for tracking changes)
CREATE TABLE pricing_history (
    history_id SERIAL PRIMARY KEY,
    product_id INT REFERENCES products(product_id),
    tier VARCHAR(10),
    color_type VARCHAR(20),
    old_price DECIMAL(10,2),
    new_price DECIMAL(10,2),
    change_date TIMESTAMP DEFAULT NOW(),
    change_reason TEXT
);

CREATE INDEX idx_history_product ON pricing_history(product_id);
CREATE INDEX idx_history_date ON pricing_history(change_date);
```

---

## API Specification

### Base URL
```
https://your-domain.com/api
```

### Endpoints

#### 1. Main Query Endpoint

**POST /api/query**

Request:
```json
{
  "query": "GT-63 A类定制色",
  "user_session": "abc123",
  "language": "zh"
}
```

Response (Success - Direct Match):
```json
{
  "status": "success",
  "result_text": "**产品：GT10S 儿童分体简易带扣 SILICONE**\n\n价格：$0.82 USD (A级定制色)\n\n来源：2025.10.28 泳镜.pdf (第2页)",
  "result_markdown": "...",
  "screenshot_url": "https://storage.tcb.com/screenshots/泳镜_page_2.png",
  "data": {
    "product_code": "GT10S",
    "material": "SILICONE",
    "category": "泳镜",
    "tier": "A级",
    "color_type": "定制色",
    "price": 0.82,
    "source": {
      "pdf": "2025.10.28 泳镜.pdf",
      "page": 2
    }
  },
  "confidence": 1.0,
  "execution_time_ms": 245
}
```

Response (Needs Confirmation):
```json
{
  "status": "needs_confirmation",
  "message": "找到多个匹配产品，请确认您要查询的是哪一个：",
  "options": [
    {
      "id": "1",
      "product_code": "GT63S",
      "material": "SILICONE (硅胶款)",
      "category": "儿童分体简易带扣",
      "confidence": 0.95,
      "match_reason": "移除了连字符"
    },
    {
      "id": "2",
      "product_code": "GT63P",
      "material": "PVC",
      "category": "儿童分体简易带扣",
      "confidence": 0.95,
      "match_reason": "移除了连字符"
    }
  ],
  "confirmation_id": "conf_abc123_1699999999",
  "execution_time_ms": 198
}
```

Response (Error):
```json
{
  "status": "error",
  "error_type": "product_not_found",
  "message": "未找到匹配的产品。请检查产品代码是否正确。",
  "suggestions": [
    "GT10S",
    "GT20S",
    "GT30S"
  ],
  "execution_time_ms": 120
}
```

#### 2. Confirmation Endpoint

**POST /api/confirm**

Request:
```json
{
  "confirmation_id": "conf_abc123_1699999999",
  "selected_option": "1"
}
```

Response: (Same format as successful /api/query)

#### 3. Health Check

**GET /api/health**

Response:
```json
{
  "status": "healthy",
  "database": "connected",
  "deepseek_api": "ok",
  "timestamp": "2025-11-10T14:23:45Z"
}
```

#### 4. Screenshot Service

**GET /api/screenshot/{filename}**

Returns: PNG image file

#### 5. Admin Analytics Endpoints (Protected)

**GET /api/analytics/queries**

Query Parameters:
- `limit`: Number of queries (default: 100)
- `offset`: Pagination offset
- `start_date`: Filter from date
- `end_date`: Filter to date
- `status`: Filter by success/error

Response:
```json
{
  "total": 1247,
  "queries": [
    {
      "query_id": 12345,
      "query_text": "GT10S A级定制色",
      "selected_product": "GT10S",
      "execution_time_ms": 245,
      "success": true,
      "timestamp": "2025-11-10T14:23:45Z"
    }
  ]
}
```

**GET /api/analytics/stats**

Query Parameters:
- `days`: Number of days to analyze (default: 7)

Response:
```json
{
  "period": "last_7_days",
  "total_queries": 1247,
  "success_rate": 0.943,
  "avg_response_time_ms": 342,
  "confirmation_rate": 0.235,
  "top_products": [
    {"product_code": "GT10S", "count": 45},
    {"product_code": "F9970", "count": 32}
  ],
  "common_errors": [
    {"error": "product_not_found", "count": 12}
  ]
}
```

---

## Fuzzy Matching Algorithm

### Matching Levels

**Level 1: Exact Match**
- Input: "GT10S"
- Match: "GT10S" (confidence: 1.00)

**Level 2: Case-Insensitive**
- Input: "gt10s"
- Match: "GT10S" (confidence: 1.00)

**Level 3: Normalization (remove hyphens, spaces)**
- Input: "GT-10S", "GT 10S", "GT- 10 S"
- Normalized: "GT10S"
- Match: "GT10S" (confidence: 0.98)

**Level 4: Base Code Match**
- Input: "GT10" (no suffix)
- Matches: ["GT10S", "GT10P"] (confidence: 0.95)
- **Requires confirmation**

**Level 5: Material Inference**
- Input: "GT10 硅胶", "GT10 silicone"
- Match: "GT10S" (confidence: 0.97)

**Level 6: Fuzzy String Match (Levenshtein)**
- Input: "GT11" (typo)
- Match: "GT10" → ["GT10S", "GT10P"] (confidence: 0.85)
- Threshold: similarity ≥ 0.85
- **Requires confirmation**

### Product Code Suffix Logic

**Suffix Rules:**
- **S suffix** → SILICONE (硅胶款)
  - Examples: GT10S, MS26S, SN9810S
- **P suffix** → PVC
  - Examples: GT10P, MS26P, SN9810P
- **No suffix** → Check material column, or ambiguous (both S and P versions exist)

### Confirmation Decision Matrix

| Scenario | Action | Reason |
|----------|--------|--------|
| Single exact match (confidence = 1.0) | Direct response | No ambiguity |
| Single fuzzy match (confidence ≥ 0.95) | Direct response | High confidence |
| Multiple matches (same base code) | Confirmation required | User must choose S vs P |
| Multiple fuzzy matches | Confirmation required | Ambiguous input |
| Low confidence (< 0.85) | Error + suggestions | Too uncertain |

---

## DeepSeek Integration

### Query Understanding Prompt

```python
SYSTEM_PROMPT = """你是一个专业的价格查询助手。用户会用中文提问产品价格。

产品代码规则:
- 后缀 "S" 表示 SILICONE (硅胶款)
- 后缀 "P" 表示 PVC 款
- 无后缀可能表示两个版本都存在

定价层级:
- A级: 最优客户
- B级: 二级客户 (红线)
- C级: 一般客户
- D级: 四级客户

颜色类型:
- 标准色: 常规颜色
- 定制色: 客户定制颜色 (价格更高)

请分析用户查询，提取以下信息:
1. 产品代码 (如 GT10S, GT10P, 或 GT10)
2. 定价层级 (A/B/C/D 级)
3. 颜色类型 (标准色/定制色)
4. 材质偏好 (如果提到硅胶/PVC/silicone等)

示例:
用户: "GT10S B级定制色多少钱?"
提取: {"product_code": "GT10S", "tier": "B级", "color_type": "定制色", "material": "SILICONE"}

用户: "GT63硅胶A类"
提取: {"product_code": "GT63", "tier": "A级", "color_type": null, "material": "SILICONE"}

用户: "2美元以下的泳镜"
提取: {"product_code": null, "tier": null, "color_type": null, "filter": {"category": "泳镜", "max_price": 2.0}}

请以JSON格式返回提取结果。
"""
```

### Response Format

DeepSeek should return structured JSON:
```json
{
  "product_code": "GT10S",
  "tier": "A级",
  "color_type": "定制色",
  "material": "SILICONE",
  "category": null,
  "filters": null
}
```

---

## PDF Extraction Pipeline

### Process Flow

1. **Load PDF**
   - Use `pdfplumber` to open PDF
   - Extract all pages

2. **Table Detection**
   - Identify tables by category (泳镜, 蛙鞋, etc.)
   - Different parsers for different PDF structures

3. **Data Extraction**
   - Extract columns: product_code, material, cost, A级, B级, C级, D级, weight, etc.
   - Handle merged cells, split rows
   - Parse pricing tiers

4. **Product Code Processing**
   - Extract full code (e.g., "GT10S")
   - Extract base code (e.g., "GT10")
   - Determine material from suffix (S/P) or material column
   - Validate consistency

5. **Screenshot Generation**
   - Convert each PDF page to PNG (300 DPI)
   - Save to `/storage/screenshots/{pdf_name}_page_{N}.png`
   - Store URL in database

6. **Validation**
   - Check required fields not null
   - Verify price ordering: Cost < A级 ≤ B级 ≤ C级 ≤ D级
   - Verify 定制色 price ≥ 标准色 price
   - Check P/S suffix matches material column
   - Generate validation report

7. **Database Import**
   - Bulk insert products
   - Insert pricing tiers
   - Transaction-based (rollback on error)

### Validation Rules

```python
def validate_product(product: dict) -> list[str]:
    """Validate product data, return list of errors"""
    errors = []

    # Required fields
    if not product.get('product_code'):
        errors.append("Missing product_code")
    if not product.get('material_type'):
        errors.append("Missing material_type")
    if not product.get('base_cost'):
        errors.append("Missing base_cost")

    # Suffix logic
    if product['product_code'].endswith('S') and product['material_type'] != 'SILICONE':
        errors.append(f"Product {product['product_code']} has 'S' suffix but material is {product['material_type']}")
    if product['product_code'].endswith('P') and product['material_type'] != 'PVC':
        errors.append(f"Product {product['product_code']} has 'P' suffix but material is {product['material_type']}")

    # Price ordering
    tiers = ['cost', 'A级_标准', 'B级_标准', 'C级_标准', 'D级_标准']
    prices = [product.get(t, 0) for t in tiers]
    if prices != sorted(prices):
        errors.append(f"Price ordering violated: {prices}")

    # Custom vs standard color
    if product.get('A级_定制', 0) < product.get('A级_标准', 0):
        errors.append("定制色 price should be ≥ 标准色 price")

    return errors
```

---

## Admin Dashboard

### Pages

#### 1. Query Monitor (`/admin/queries.html`)

Features:
- Real-time query feed (last 100 queries)
- Columns: Timestamp, Query Text, Product, Time, Status
- Filter by: Date range, Success/Error, Product
- Export to CSV

```html
<!DOCTYPE html>
<html>
<head>
    <title>CostChecker - Query Monitor</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
</head>
<body>
    <div class="container mt-4">
        <h1>Query Monitor</h1>
        <table class="table table-striped">
            <thead>
                <tr>
                    <th>Time</th>
                    <th>Query</th>
                    <th>Product</th>
                    <th>Response Time</th>
                    <th>Status</th>
                </tr>
            </thead>
            <tbody id="query-table">
                <!-- Populated via JavaScript -->
            </tbody>
        </table>
        <button onclick="exportCSV()">Export CSV</button>
    </div>
    <script>
        async function loadQueries() {
            const response = await fetch('/api/analytics/queries?limit=100');
            const data = await response.json();
            // Render table...
        }
        setInterval(loadQueries, 30000); // Refresh every 30s
    </script>
</body>
</html>
```

#### 2. Analytics (`/admin/analytics.html`)

Features:
- Summary metrics (total queries, success rate, avg time)
- Top 10 products (bar chart using Chart.js)
- Confirmation rate
- Common errors

#### 3. Data Quality (`/admin/data.html`)

Features:
- Database status (last updated, total products)
- Product breakdown by category
- Screenshot coverage (% products with screenshots)
- Validation status

---

## Deployment on Tencent CloudBase

### Setup Steps

1. **Create CloudBase Environment**
   ```bash
   # Using TCB CLI
   tcb init
   tcb env create --name costchecker-prod
   ```

2. **Deploy PostgreSQL**
   - Use TCB CloudBase Database (MongoDB-like) OR
   - External PostgreSQL (recommended for relational data)
   - Alternative: TCB Cloud Database for PostgreSQL

3. **Upload Screenshots to Cloud Storage**
   ```bash
   tcb storage upload ./screenshots --remote-path=/screenshots/
   ```

4. **Deploy FastAPI Application**

   **Option A: Docker Container**
   ```dockerfile
   FROM python:3.11-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
   ```

   **Option B: Direct Deployment**
   ```bash
   tcb functions deploy --name costchecker-api --runtime python3.11
   ```

5. **Environment Variables**
   ```bash
   DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxx
   DATABASE_URL=postgresql://user:pass@host:5432/costchecker
   SCREENSHOT_BASE_URL=https://storage.tcb.com/screenshots/
   ADMIN_USERNAME=admin
   ADMIN_PASSWORD=secure_password_here
   CORS_ORIGINS=https://your-frontend-domain.com
   ```

6. **Configure Domain & SSL**
   - Set up custom domain in TCB console
   - Enable HTTPS (auto SSL)

---

## Development Workflow

### Initial Setup

1. Clone repository
2. Install dependencies: `pip install -r requirements.txt`
3. Set up local PostgreSQL database
4. Run migrations: `alembic upgrade head`
5. Extract PDFs: `python scripts/extract_pdfs.py`
6. Generate screenshots: `python scripts/generate_screenshots.py`
7. Start API: `uvicorn main:app --reload`
8. Access admin: `http://localhost:8000/admin/`

### Half-Yearly Update Process

1. Upload new PDFs to `/data/pdfs/new/`
2. Run extraction: `python scripts/extract_pdfs.py --input=data/pdfs/new/`
3. Review diff report: `cat data/reports/price_diff_2025-04-28.txt`
4. Approve changes: `python scripts/apply_updates.py --approve`
5. Verify: Check admin dashboard for new data

---

## Testing Strategy

### Unit Tests
- Fuzzy matching algorithm
- Product code normalization
- Price validation logic
- DeepSeek prompt parsing

### Integration Tests
- PDF extraction end-to-end
- API endpoints (query, confirm, analytics)
- Database operations

### End-to-End Tests
- Full query flow: user input → confirmation → result
- Screenshot serving
- Admin authentication

### Test Data
- Sample PDFs with known data
- Edge cases (missing fields, malformed codes)
- Typo variations for fuzzy matching

---

## Performance Targets

| Metric | Target | Measurement |
|--------|--------|-------------|
| API response time (95th percentile) | <1s | Prometheus + Grafana |
| Database query time | <200ms | PostgreSQL logs |
| Screenshot load time | <500ms | CDN metrics |
| Success rate | >95% | Query logs |
| PDF extraction accuracy | >95% | Manual validation |
| Fuzzy match accuracy | >98% | Test suite |

---

## Security Considerations

1. **SQL Injection Prevention**
   - Use parameterized queries
   - ORM-based queries (SQLAlchemy)
   - No direct SQL string concatenation

2. **Admin Access**
   - HTTP Basic Auth (username/password)
   - HTTPS only
   - Rate limiting on admin endpoints

3. **API Security**
   - CORS configuration (restrict origins)
   - Rate limiting (100 queries/min per IP)
   - Input validation (sanitize all inputs)

4. **Data Privacy**
   - No PII stored in query logs
   - User sessions anonymized
   - IP addresses hashed

5. **DeepSeek API Key**
   - Stored in environment variables
   - Never committed to git
   - Rotated quarterly

---

## Monitoring & Logging

### Application Logs
```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/app.log'),
        logging.StreamHandler()
    ]
)
```

### Metrics to Track
- Total queries per day
- Success/error rate
- Average response time
- Confirmation rate
- Top products queried
- DeepSeek API usage (token count)
- Database connection pool utilization

### Alerts
- Error rate > 10% (15 min window)
- Response time > 2s (95th percentile)
- Database connection failures
- DeepSeek API quota exceeded

---

## Cost Estimation

### DeepSeek API
- ~100 tokens per query (avg)
- 1000 queries/day
- DeepSeek pricing: ~$0.14 per 1M tokens
- **Monthly cost: ~$0.42**

### Tencent CloudBase
- Database: ~¥50-100/month (1GB storage, light traffic)
- Cloud Storage (screenshots): ~¥10/month (5GB)
- Compute: ~¥100-200/month (depends on traffic)
- **Total monthly: ~¥160-310 (~$22-43 USD)**

### Total Estimated Monthly Cost: **~$25-50 USD**

---

## Future Enhancements (Out of Scope)

1. Multi-language support (English queries)
2. Voice query input (speech-to-text)
3. Batch quote generation (upload product list → get full quote)
4. Customer tier management (assign customers to A/B/C/D)
5. Inventory integration (link to stock levels)
6. Order placement (full e-commerce flow)
7. Mobile app (iOS/Android)
8. Real-time price updates (webhook-based)

---

## File Structure

```
costchecker/
├── app/
│   ├── main.py                  # FastAPI application
│   ├── api/
│   │   ├── routes/
│   │   │   ├── query.py         # Query endpoints
│   │   │   ├── analytics.py    # Analytics endpoints
│   │   │   └── admin.py         # Admin endpoints
│   │   └── dependencies.py      # FastAPI dependencies
│   ├── core/
│   │   ├── config.py            # Configuration
│   │   ├── database.py          # Database connection
│   │   └── security.py          # Auth logic
│   ├── models/
│   │   ├── product.py           # SQLAlchemy models
│   │   ├── query_log.py
│   │   └── pricing.py
│   ├── services/
│   │   ├── fuzzy_match.py       # Fuzzy matching logic
│   │   ├── deepseek.py          # DeepSeek API client
│   │   ├── query_processor.py   # Main query processing
│   │   └── screenshot.py        # Screenshot service
│   └── utils/
│       ├── validation.py        # Data validation
│       └── helpers.py
├── scripts/
│   ├── extract_pdfs.py          # PDF extraction script
│   ├── generate_screenshots.py  # Screenshot generation
│   ├── apply_updates.py         # Apply price updates
│   └── seed_database.py         # Initial data load
├── admin/
│   ├── index.html               # Admin dashboard
│   ├── queries.html
│   ├── analytics.html
│   ├── data.html
│   └── static/
│       ├── css/
│       └── js/
├── data/
│   ├── pdfs/                    # Source PDFs
│   ├── screenshots/             # Generated screenshots
│   └── reports/                 # Validation/diff reports
├── tests/
│   ├── test_fuzzy_match.py
│   ├── test_api.py
│   └── test_extraction.py
├── alembic/                     # Database migrations
├── logs/
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── .gitignore
├── IMPLEMENTATION_PLAN.md       # This file
├── TASKS.md                     # Detailed task checklist
└── README.md
```

---

## Dependencies (requirements.txt)

```
fastapi==0.104.1
uvicorn[standard]==0.24.0
sqlalchemy==2.0.23
psycopg2-binary==2.9.9
alembic==1.12.1
pydantic==2.5.0
pydantic-settings==2.1.0
python-multipart==0.0.6

# PDF processing
pdfplumber==0.10.3
pdf2image==1.16.3
Pillow==10.1.0

# Fuzzy matching
rapidfuzz==3.5.2

# HTTP client
httpx==0.25.2

# Auth
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4

# Utilities
python-dotenv==1.0.0

# Testing
pytest==7.4.3
pytest-asyncio==0.21.1
pytest-cov==4.1.0
```

---

## Success Criteria

### Stage 1: PDF Extraction
- ✅ All 9 PDFs extracted successfully
- ✅ >95% accuracy vs manual review (20 random samples)
- ✅ All screenshots generated (1 per PDF page)
- ✅ P/S suffix logic validated

### Stage 2: Fuzzy Matching
- ✅ 98% accuracy on 50 test variations
- ✅ Zero false positives (incorrect matches)
- ✅ Confirmation required for all ambiguous queries

### Stage 3: API
- ✅ API responds <1s for 95% of queries
- ✅ 100% of queries logged to database
- ✅ Text/markdown responses formatted correctly
- ✅ Screenshots served successfully

### Stage 4: Admin Dashboard
- ✅ Dashboard loads <2s
- ✅ CSV export works
- ✅ Auth protects admin pages

### Stage 5: Re-extraction
- ✅ Diff report accurate
- ✅ Zero downtime during update
- ✅ Rollback works if errors

### Stage 6: Deployment
- ✅ API accessible on TCB
- ✅ Admin dashboard password-protected
- ✅ Screenshots load from CDN
- ✅ End-to-end test passes

---

## Timeline

| Stage | Duration | Dependencies |
|-------|----------|--------------|
| Stage 1: PDF Extraction | 4 days | None |
| Stage 2: Fuzzy Matching | 3 days | Stage 1 (database ready) |
| Stage 3: FastAPI | 3 days | Stage 1, 2 |
| Stage 4: Admin Dashboard | 2 days | Stage 3 |
| Stage 5: Re-extraction | 2 days | Stage 1 |
| Stage 6: Deployment | 2 days | All stages |
| **Total** | **16 days** | |

---

## Version History

- **v1.0** (2025-11-10): Initial implementation plan
