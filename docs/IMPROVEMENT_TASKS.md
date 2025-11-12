# CostChecker Improvement Task List

**Generated**: 2025-11-11
**Based on**: SCENARIO_TEST_RESULTS_20251111_205248.md
**Status**: Not Started

---

## Overview

This document outlines actionable improvements for the CostChecker product based on live API test results. Tasks are organized by priority and include specific file references, success criteria, and dependencies.

### Test Results Summary

**Observed Issues**:
1. ❌ Products (GT33, 2322, GS31) showing $0.00 prices in comparison queries
2. ❌ "比...便宜的" queries falling back to generic "cheapest" list instead of proper comparison
3. ⚠️ GT10 queries returning limited confirmation options (only GT10S, missing GT10P)
4. ⚠️ Non-existent product comparisons returning generic results instead of proper errors

**Success Rate**: 9/13 queries (69%) - needs improvement to >95%

---

## Priority 0: Critical Fixes (Data Integrity)

These issues cause incorrect data to be displayed to users and must be fixed immediately.

### Task P0.1: Fix $0.00 Price Display Bug

**Status**: Not Started
**Priority**: P0 - Critical
**Complexity**: Low (1-2 hours)

**Description**:
Products GT33, 2322, GS31 appear in comparison queries with $0.00 prices. This is either a data quality issue or a SQL filter gap.

**Root Cause**:
- `pick_price()` function returns 0.0 for missing pricing tiers
- Current SQL filter: `WHERE x.price IS NOT NULL` allows 0.0 values through
- No validation at application layer

**Files to Modify**:
- `app/services/wide_search.py` lines 193-220, 250-278, 285-315

**Changes Required**:

1. **Add Zero-Price Filter** (3 locations):
   ```python
   # Current (line 255):
   WHERE x.price IS NOT NULL

   # New:
   WHERE x.price IS NOT NULL AND x.price > 0
   ```

2. **Add Fallback Logic**:
   ```python
   # After query execution, validate results
   if not results:
       return {
           "status": "error",
           "error_type": "no_pricing_data",
           "message": "No valid pricing data found for the specified criteria."
       }
   ```

3. **Add Logging**:
   ```python
   # Before filtering
   logger.warning(f"Found {len(results)} products, filtering zero prices")
   results = [r for r in results if r.get('price', 0) > 0]
   logger.info(f"After filtering: {len(results)} products with valid pricing")
   ```

**Success Criteria**:
- [ ] Queries return NO products with $0.00 prices
- [ ] If all matched products have $0.00 prices, return clear error message
- [ ] Test cases #7, #9, #10 no longer show $0.00 entries
- [ ] Log entry generated when zero prices are filtered

**Testing Approach**:
```bash
# Test queries that previously showed $0.00
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "比 GT10S 便宜的"}'

# Verify GT33, 2322, GS31 are either:
# 1. Excluded from results, OR
# 2. Show valid prices > 0
```

**Dependencies**: None

**Rollback Plan**: Revert SQL filter change if legitimate $0.00 promotional prices exist

---

### Task P0.2: Verify PostgreSQL pick_price() Function

**Status**: Not Started
**Priority**: P0 - Critical
**Complexity**: Medium (2-4 hours)

**Description**:
The `pick_price()` function is called throughout wide_search.py but not defined in Python codebase. Need to verify it exists in database, document its behavior, and handle edge cases.

**Root Cause**:
- PostgreSQL function defined outside version control
- No documentation of function signature or behavior
- No fallback when function is missing or returns unexpected values

**Files to Investigate**:
- `app/services/wide_search.py` (lines 197, 244, 285 - all calls)
- Database migration files in `alembic/versions/`
- `app/db/base.py` or initialization scripts

**Changes Required**:

1. **Find or Create Function Definition**:
   ```sql
   -- Expected signature (to be verified):
   CREATE OR REPLACE FUNCTION pick_price(
       p_product_id INTEGER,
       p_tier VARCHAR,
       p_color_type VARCHAR
   ) RETURNS NUMERIC AS $$
   BEGIN
       -- Query pricing_tiers table with fallback logic
       RETURN (
           SELECT price
           FROM pricing_tiers
           WHERE product_id = p_product_id
             AND tier = COALESCE(p_tier, tier)
             AND color_type = COALESCE(p_color_type, color_type)
           ORDER BY
             CASE WHEN tier = p_tier THEN 0 ELSE 1 END,
             CASE WHEN color_type = p_color_type THEN 0 ELSE 1 END,
             effective_date DESC
           LIMIT 1
       );
   END;
   $$ LANGUAGE plpgsql;
   ```

2. **Create Alembic Migration**:
   ```bash
   alembic revision -m "add_pick_price_function"
   # Add function definition to upgrade(), DROP in downgrade()
   ```

3. **Document Function Behavior** in code comments:
   ```python
   # app/services/wide_search.py:197
   # pick_price() PostgreSQL function:
   # - Returns NULL if no matching tier/color combination
   # - Returns 0.0 if pricing_tiers record exists but price=0
   # - Fallback logic: exact match > partial match > latest effective_date
   ```

4. **Add Application-Level Fallback**:
   ```python
   # If pick_price() fails (function not found)
   try:
       result = db.execute(query_with_pick_price)
   except ProgrammingError as e:
       if "function pick_price does not exist" in str(e):
           logger.error("pick_price() function missing - using fallback query")
           result = db.execute(fallback_query_without_pick_price)
       else:
           raise
   ```

**Success Criteria**:
- [ ] `pick_price()` function exists in database and is version-controlled
- [ ] Function behavior documented in code comments
- [ ] Alembic migration created and tested (upgrade/downgrade)
- [ ] Application handles missing function gracefully with fallback
- [ ] Test on fresh database to verify migration works

**Testing Approach**:
```bash
# Test 1: Verify function exists
docker compose exec postgres psql -U costchecker -d costchecker \
  -c "\df pick_price"

# Test 2: Test function behavior
docker compose exec postgres psql -U costchecker -d costchecker \
  -c "SELECT pick_price(1, 'A', 'standard');"

# Test 3: Test with NULL inputs
docker compose exec postgres psql -U costchecker -d costchecker \
  -c "SELECT pick_price(1, NULL, NULL);"

# Test 4: Run migration on fresh DB
docker compose down -v
docker compose up -d
alembic upgrade head
pytest tests/test_price_function.py
```

**Dependencies**: None (but blocks P0.1 full verification)

---

### Task P0.3: Fix Description Match Error Propagation

**Status**: Not Started
**Priority**: P0 - Critical
**Complexity**: Low (1-2 hours)

**Description**:
When description-based comparison queries fail to match a product, the error dict is created but execution continues, causing fallback to generic "cheapest" list.

**Root Cause**:
- `wide_search.py:152-160` returns error dict but caller doesn't check status
- OR error dict structure is incorrect
- Control flow continues to default mode (top_asc)

**Files to Modify**:
- `app/services/wide_search.py` lines 152-178

**Changes Required**:

1. **Verify Error Return Format**:
   ```python
   # Line 152-160 (current)
   if params.description_query and not params.ref_code:
       matches = match_product_by_description(db, params.description_query, threshold=0.70)
       if not matches:
           return {  # ← Is this actually returned?
               "status": "error",
               "error_type": "reference_not_found",
               "message": f"未找到匹配描述的产品: {params.description_query}"
           }
   ```

2. **Add Explicit Return Check** in calling code:
   ```python
   # In process_query() or wherever run_wide_search is called
   result = run_wide_search(db, query_text, None)
   if result.get("status") == "error":
       return result  # Stop processing, return error to user
   ```

3. **Add Test for Error Path**:
   ```python
   # tests/test_wide_search.py
   def test_description_match_not_found():
       result = run_wide_search(db, "比 不存在的描述 便宜的", None)
       assert result["status"] == "error"
       assert result["error_type"] == "reference_not_found"
       assert "不存在的描述" in result["message"]
   ```

4. **Add Logging**:
   ```python
   # Before return
   logger.warning(f"Description-based match failed: {params.description_query}")
   logger.debug(f"Attempted match with threshold=0.70, zero results")
   ```

**Success Criteria**:
- [ ] Query "比 不存在的描述 便宜的" returns error, not generic cheapest list
- [ ] Error response includes descriptive message with the query text
- [ ] Test case added and passing
- [ ] Logs show clear indication of match failure

**Testing Approach**:
```bash
# Test with non-existent description
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "比 不存在的产品描述 便宜的"}'

# Expected response:
# {
#   "status": "error",
#   "error_type": "reference_not_found",
#   "message": "未找到匹配描述的产品: 不存在的产品描述"
# }

# Should NOT return generic cheapest list
```

**Dependencies**: None

---

## Priority 1: High Priority (User Experience)

These issues cause confusion or incorrect results but don't corrupt data.

### Task P1.1: Fix Description-Based Comparison Logic

**Status**: Not Started
**Priority**: P1 - High
**Complexity**: Medium (3-5 hours)

**Description**:
Query "比 儿童分体简易 Silicone 便宜的" should find GT10S via description matching and return products cheaper than GT10S. Currently falls back to generic cheapest list.

**Root Cause**:
- Regex pattern in `product_name_matcher.py:35` may not capture description correctly
- Threshold of 0.70 may be too strict
- Chinese text normalization issues (simplified vs traditional)

**Files to Modify**:
- `app/services/product_name_matcher.py` lines 20-44, 130-161
- `app/services/wide_search.py` lines 63-77, 152-160

**Changes Required**:

1. **Improve Regex Pattern** (product_name_matcher.py:35):
   ```python
   # Current pattern (too restrictive):
   pattern = r"比\s*([一-龥\s]+?)(?:\s*(?:SILICONE|PVC|TPE|硅胶|矽膠|便宜|贵|的))"

   # New pattern (more flexible):
   pattern = r"比\s*([一-龥\w\s]+?)(?:\s+(?:SILICONE|PVC|TPE|硅胶|矽膠|Silicone|silicone))?\s*(?:便宜|贵)"
   # Changes:
   # - Added \w to capture alphanumeric chars
   # - Made material matching optional with (?:...)?
   # - Case-insensitive material variants
   ```

2. **Add Fallback Threshold** (product_name_matcher.py:144):
   ```python
   # Try multiple thresholds
   thresholds = [0.70, 0.60, 0.50]
   for threshold in thresholds:
       matches = match_product_by_description(db, description, threshold=threshold)
       if matches:
           logger.info(f"Description matched at threshold={threshold}")
           break
   else:
       logger.warning(f"Description '{description}' matched no products at any threshold")
   ```

3. **Add Material-Aware Scoring** (product_name_matcher.py:157):
   ```python
   # If query includes material, boost score for matching material
   material_keywords = {
       'SILICONE': ['硅胶', '矽膠', 'silicone'],
       'PVC': ['pvc', 'PVC'],
       'TPE': ['tpe', 'TPE']
   }

   for product in candidates:
       score = fuzz.token_set_ratio(description, product.name_zh)
       # Boost score if materials match
       for mat, keywords in material_keywords.items():
           if product.material_type == mat and any(kw in query_text for kw in keywords):
               score += 10  # Boost by 10 points
       product.match_score = score
   ```

4. **Add Debug Logging**:
   ```python
   logger.debug(f"Extracted description: '{description}'")
   logger.debug(f"Matching against {len(candidates)} products")
   for candidate in candidates[:5]:  # Top 5
       logger.debug(f"  - {candidate.product_code}: score={candidate.match_score}")
   ```

**Success Criteria**:
- [ ] Query "比 儿童分体简易 Silicone 便宜的" correctly identifies GT10S
- [ ] Returns products cheaper than GT10S (not generic cheapest list)
- [ ] Test case #9 from scenario tests passes
- [ ] Material-aware matching improves precision

**Testing Approach**:
```python
# Test case to add to tests/test_product_name_matcher.py
def test_description_with_material():
    """Test description matching with material keyword."""
    query = "比 儿童分体简易 Silicone 便宜的"
    result = run_wide_search(db, query, None)

    assert result["status"] == "success"
    assert result["mode"] == "compare_lt"
    assert result["reference_product"]["product_code"] == "GT10S"
    assert all(p["price"] < result["reference_product"]["price"]
               for p in result["products"])
```

**Dependencies**: P0.3 (error propagation) should be fixed first

---

### Task P1.2: Improve GT10 Confirmation Options

**Status**: Not Started
**Priority**: P1 - High
**Complexity**: Medium (2-3 hours)

**Description**:
Queries for "GT10" should return both GT10S and GT10P as confirmation options, but currently only shows GT10S.

**Root Cause**:
- Material inference in `query_processor.py:95-100` filters from 2 variants → 1
- Base code matching works correctly (finds both)
- Overly aggressive filtering based on weak material signal

**Files to Modify**:
- `app/services/query_processor.py` lines 95-100
- `app/utils/inference.py` (material inference logic)

**Changes Required**:

1. **Add Confidence Threshold for Filtering** (query_processor.py:95):
   ```python
   # Current (filters if ANY material inferred):
   if material:
       filtered = [p for p in matches if p.material_type == material]
       if filtered:
           matches = filtered

   # New (only filter if high confidence):
   if material and material_confidence > 0.8:  # Require high confidence
       filtered = [p for p in matches if p.material_type == material]
       if filtered:
           logger.info(f"Filtered to {len(filtered)} products by material={material}")
           matches = filtered
       else:
           logger.warning(f"Material filter would exclude all matches, keeping all")
   else:
       logger.debug(f"Material inference confidence too low ({material_confidence}), keeping all variants")
   ```

2. **Return Confidence Score from Inference** (utils/inference.py):
   ```python
   def infer_material(query: str) -> tuple[Optional[str], float]:
       """
       Returns: (material, confidence)
       Confidence: 0.0-1.0
       """
       # Exact keyword match → high confidence
       if re.search(r'\b(SILICONE|硅胶|矽膠)\b', query, re.IGNORECASE):
           return ('SILICONE', 0.95)

       # Partial match → medium confidence
       if 'silicone' in query.lower():
           return ('SILICONE', 0.7)

       # No material mentioned → zero confidence
       return (None, 0.0)
   ```

3. **Preserve Multiple Options in Confirmation**:
   ```python
   # If base code match returns >1 variant and no high-confidence filter applies
   if len(matches) > 1 and not material_confidence > 0.8:
       return {
           "status": "needs_confirmation",
           "message": f"找到 {len(matches)} 个匹配的产品，请选择：",
           "options": [
               {
                   "product_code": m.product_code,
                   "name": m.name_zh,
                   "material": m.material_type,
                   "description": f"{m.name_zh} ({m.material_type})"
               } for m in matches
           ]
       }
   ```

**Success Criteria**:
- [ ] Query "GT10 多少钱" returns both GT10S and GT10P options
- [ ] Query "GT10 Silicone 多少钱" returns only GT10S (high confidence)
- [ ] Test cases #5 and #6 show all relevant options
- [ ] Confirmation messages clearly explain multiple variants

**Testing Approach**:
```bash
# Test 1: Ambiguous query (no material)
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "GT10 多少钱"}'
# Expected: needs_confirmation with GT10S and GT10P

# Test 2: Specific material (high confidence)
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "GT10 SILICONE 多少钱"}'
# Expected: direct result for GT10S only
```

**Dependencies**: None

---

### Task P1.3: Add Graceful Error for Non-Existent Product Comparisons

**Status**: Not Started
**Priority**: P1 - High
**Complexity**: Low (1-2 hours)

**Description**:
Query "比 XJ1234 便宜的" should return clear error that product doesn't exist, not fall back to generic list.

**Root Cause**:
- Similar to P0.3 - error handling gaps
- Product code extraction works but matching fails silently
- No distinction between "no matches" and "invalid product code"

**Files to Modify**:
- `app/services/wide_search.py` lines 140-178
- `app/services/query_processor.py` lines 54-76

**Changes Required**:

1. **Add Explicit Check After Product Matching**:
   ```python
   # In wide_search.py after ref_code is set (line 144)
   if params.ref_code:
       # Try to match the reference product
       ref_matches = match_product(db, params.ref_code)
       if not ref_matches:
           return {
               "status": "error",
               "error_type": "reference_not_found",
               "message": f"参考产品 {params.ref_code} 不存在，请检查产品代码。"
           }
       ref_product = ref_matches[0]
   ```

2. **Distinguish "Not Found" from "Multiple Matches"**:
   ```python
   # If multiple matches for reference product
   if len(ref_matches) > 1:
       return {
           "status": "needs_confirmation",
           "message": f"参考产品 {params.ref_code} 有多个匹配，请选择：",
           "options": [format_option(m) for m in ref_matches],
           "context": {
               "query_type": "comparison",
               "original_query": query_text
           }
       }
   ```

3. **Add Validation in Comparison Queries**:
   ```python
   # Before running comparison query
   if not ref_product or not hasattr(ref_product, 'product_id'):
       logger.error(f"Invalid reference product for comparison: {params.ref_code}")
       return {
           "status": "error",
           "error_type": "invalid_reference",
           "message": "参考产品无效，无法进行比较。"
       }
   ```

**Success Criteria**:
- [ ] Query "比 XJ1234 便宜的" returns error with clear message
- [ ] Query "比 不存在的产品 便宜的" returns error (not generic list)
- [ ] Error message includes the invalid product code
- [ ] Test case #12 shows proper error response

**Testing Approach**:
```bash
# Test invalid product code
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "比 XJ1234 便宜的"}'

# Expected:
# {
#   "status": "error",
#   "error_type": "reference_not_found",
#   "message": "参考产品 XJ1234 不存在，请检查产品代码。"
# }
```

**Dependencies**: P0.3 (error propagation)

---

### Task P1.4: Data Quality Audit and Cleanup

**Status**: Not Started
**Priority**: P1 - High
**Complexity**: High (4-6 hours)

**Description**:
Audit database for missing/invalid pricing data and product information. Fix data quality issues at the source.

**Root Cause**:
- Products GT33, 2322, GS31 have $0.00 prices (likely missing PricingTier records)
- No validation at data import time
- No ongoing data quality monitoring

**Files to Create/Modify**:
- `scripts/audit_data_quality.py` (new)
- `scripts/fix_missing_prices.py` (new)
- `app/models/product.py` (add validation)

**Changes Required**:

1. **Create Audit Script**:
   ```python
   # scripts/audit_data_quality.py
   """
   Audit database for data quality issues.

   Checks:
   - Products without any pricing data
   - PricingTier records with price=0 or NULL
   - Products without descriptions (name_zh)
   - Orphaned pricing records
   - Missing tier/color combinations
   """

   def audit_missing_prices(db):
       """Find products with no pricing data."""
       products_no_price = db.query(Product).outerjoin(PricingTier).filter(
           PricingTier.id == None
       ).all()

       print(f"\n❌ {len(products_no_price)} products with NO pricing data:")
       for p in products_no_price:
           print(f"  - {p.product_code}: {p.name_zh}")

   def audit_zero_prices(db):
       """Find pricing records with $0.00."""
       zero_prices = db.query(PricingTier).filter(
           PricingTier.price == 0
       ).all()

       print(f"\n⚠️  {len(zero_prices)} pricing records with $0.00:")
       for pt in zero_prices:
           print(f"  - {pt.product.product_code} ({pt.tier}, {pt.color_type}): ${pt.price}")
   ```

2. **Add Model-Level Validation** (app/models/product.py):
   ```python
   from sqlalchemy import CheckConstraint

   class PricingTier(Base):
       __tablename__ = "pricing_tiers"

       # ... existing fields ...

       __table_args__ = (
           CheckConstraint('price > 0', name='check_price_positive'),
           CheckConstraint('price < 1000', name='check_price_reasonable'),
       )
   ```

3. **Create Migration to Add Constraints**:
   ```bash
   alembic revision -m "add_price_validation_constraints"
   ```

4. **Create Fix Script**:
   ```python
   # scripts/fix_missing_prices.py
   """
   Strategies:
   1. Interpolate from similar products (same material, similar name)
   2. Set placeholder price (flag for manual review)
   3. Disable products with no recoverable pricing
   """

   def fix_zero_prices(db):
       zero_price_tiers = db.query(PricingTier).filter(
           PricingTier.price == 0
       ).all()

       for tier in zero_price_tiers:
           # Strategy: Find similar product's price
           similar = db.query(PricingTier).join(Product).filter(
               Product.material_type == tier.product.material_type,
               PricingTier.tier == tier.tier,
               PricingTier.color_type == tier.color_type,
               PricingTier.price > 0
           ).order_by(PricingTier.price).limit(10).all()

           if similar:
               median_price = sorted([s.price for s in similar])[len(similar)//2]
               print(f"Setting {tier.product.product_code} price to ${median_price} (median of similar)")
               # Don't auto-commit - generate SQL for review
           else:
               print(f"⚠️  No similar products found for {tier.product.product_code}")
   ```

**Success Criteria**:
- [ ] Audit script identifies all data quality issues
- [ ] Fix script generates SQL to resolve $0.00 prices
- [ ] Model validation prevents future $0.00 prices
- [ ] No products show $0.00 in API responses after fixes applied
- [ ] Documentation added explaining data quality standards

**Testing Approach**:
```bash
# Run audit
python scripts/audit_data_quality.py

# Review findings
# Manually fix critical issues or run fix script

# Re-run audit to verify
python scripts/audit_data_quality.py

# Test API queries
curl -X POST http://localhost:8000/api/query \
  -d '{"query": "最便宜的 泳镜 前10"}' | jq '.products[] | select(.price == 0)'
# Should return empty (no $0.00 prices)
```

**Dependencies**: P0.1 (SQL filtering prevents $0.00 from appearing while this is in progress)

---

## Priority 2: Medium Priority (Robustness)

These improvements enhance system reliability and maintainability.

### Task P2.1: Comprehensive Logging Infrastructure

**Status**: Not Started
**Priority**: P2 - Medium
**Complexity**: Medium (3-4 hours)

**Description**:
Add structured logging throughout query processing pipeline to enable debugging and monitoring.

**Files to Modify**:
- `app/services/query_processor.py`
- `app/services/wide_search.py`
- `app/services/product_name_matcher.py`
- `app/core/config.py` (log configuration)

**Changes Required**:

1. **Configure Structured Logging** (app/core/config.py):
   ```python
   import logging
   import json
   from pythonjsonlogger import jsonlogger

   def setup_logging():
       logHandler = logging.StreamHandler()
       formatter = jsonlogger.JsonFormatter(
           '%(asctime)s %(name)s %(levelname)s %(message)s'
       )
       logHandler.setFormatter(formatter)

       logger = logging.getLogger()
       logger.addHandler(logHandler)
       logger.setLevel(logging.INFO)
   ```

2. **Add Trace IDs** (app/api/routes/query.py):
   ```python
   import uuid

   @router.post("/query")
   async def query_price(request: QueryRequest):
       trace_id = str(uuid.uuid4())
       logger.info("Query received", extra={
           "trace_id": trace_id,
           "query": request.query,
           "user_id": request.user_id
       })

       # Pass trace_id through call stack
       result = process_query(db, request.query, trace_id=trace_id)

       logger.info("Query completed", extra={
           "trace_id": trace_id,
           "status": result.get("status"),
           "processing_time_ms": (time.time() - start) * 1000
       })
   ```

3. **Add Decision Point Logging** (throughout services):
   ```python
   # In query_processor.py
   logger.info("Product matching stage", extra={
       "trace_id": trace_id,
       "stage": "exact_match",
       "input_code": normalized_code,
       "matches_found": len(matches),
       "confidence": confidence
   })

   # In wide_search.py
   logger.info("Wide query detected", extra={
       "trace_id": trace_id,
       "mode": params.mode,
       "ref_code": params.ref_code,
       "description_query": params.description_query
   })
   ```

4. **Add Performance Timing**:
   ```python
   import time
   from contextlib import contextmanager

   @contextmanager
   def log_duration(operation: str, trace_id: str):
       start = time.time()
       try:
           yield
       finally:
           duration_ms = (time.time() - start) * 1000
           logger.info("Operation completed", extra={
               "trace_id": trace_id,
               "operation": operation,
               "duration_ms": duration_ms
           })

   # Usage:
   with log_duration("product_matching", trace_id):
       matches = match_product(db, code)
   ```

**Success Criteria**:
- [ ] All API requests have unique trace_id in logs
- [ ] Each decision point (exact match, fuzzy match, error) is logged
- [ ] Performance timings captured for major operations
- [ ] Logs are structured JSON for easy parsing
- [ ] Log aggregation tool (e.g., grep, jq) can filter by trace_id

**Testing Approach**:
```bash
# Run query and capture logs
docker compose logs -f api | jq 'select(.trace_id == "abc-123")'

# Verify all decision points logged
# Should see: query_received → wide_query_detected → product_matching →
#             price_resolution → response_formatted → query_completed
```

**Dependencies**: None

---

### Task P2.2: Enhanced Material Inference Logic

**Status**: Not Started
**Priority**: P2 - Medium
**Complexity**: Medium (2-3 hours)

**Description**:
Improve material inference to handle edge cases, abbreviations, and multi-language keywords.

**Files to Modify**:
- `app/utils/inference.py`

**Changes Required**:

1. **Expand Material Keyword Dictionary**:
   ```python
   MATERIAL_KEYWORDS = {
       'SILICONE': {
           'exact': ['SILICONE', '硅胶', '矽膠', 'silicone'],
           'partial': ['硅', '矽', 'silicon'],
           'confidence': 0.95
       },
       'PVC': {
           'exact': ['PVC', 'pvc'],
           'partial': ['塑料', '塑膠'],
           'confidence': 0.90
       },
       'TPE': {
           'exact': ['TPE', 'tpe'],
           'partial': ['橡胶', '橡膠', 'rubber'],
           'confidence': 0.85
       }
   }
   ```

2. **Implement Confidence Scoring**:
   ```python
   def infer_material(query: str) -> tuple[Optional[str], float]:
       query_lower = query.lower()
       query_clean = re.sub(r'\s+', '', query)  # Remove spaces

       best_material = None
       best_confidence = 0.0

       for material, keywords in MATERIAL_KEYWORDS.items():
           # Exact match → highest confidence
           for exact_kw in keywords['exact']:
               if re.search(rf'\b{re.escape(exact_kw)}\b', query, re.IGNORECASE):
                   if keywords['confidence'] > best_confidence:
                       best_material = material
                       best_confidence = keywords['confidence']

           # Partial match → medium confidence
           if best_confidence < 0.7:  # Only if no exact match found
               for partial_kw in keywords['partial']:
                   if partial_kw in query_lower or partial_kw in query_clean:
                       confidence = keywords['confidence'] * 0.7  # Reduce by 30%
                       if confidence > best_confidence:
                           best_material = material
                           best_confidence = confidence

       return best_material, best_confidence
   ```

3. **Add Context-Aware Inference**:
   ```python
   def infer_material_with_context(
       query: str,
       matched_products: List[Product]
   ) -> tuple[Optional[str], float]:
       """
       If query doesn't specify material but matched products all have
       same material, boost confidence.
       """
       material, confidence = infer_material(query)

       if not material and matched_products:
           materials = [p.material_type for p in matched_products]
           if len(set(materials)) == 1:
               # All matches are same material → boost confidence
               return materials[0], 0.6  # Medium confidence

       return material, confidence
   ```

**Success Criteria**:
- [ ] Handles both simplified and traditional Chinese
- [ ] Returns confidence scores for filtering decisions
- [ ] Recognizes common abbreviations and variations
- [ ] Test coverage for all supported materials and edge cases

**Testing Approach**:
```python
# tests/test_inference.py
def test_material_inference():
    assert infer_material("GT10S SILICONE") == ("SILICONE", 0.95)
    assert infer_material("GT10S 硅胶") == ("SILICONE", 0.95)
    assert infer_material("GT10S 矽膠") == ("SILICONE", 0.95)
    assert infer_material("GT10S silicon") == ("SILICONE", 0.665)  # partial

    mat, conf = infer_material("GT10S")
    assert mat is None
    assert conf == 0.0
```

**Dependencies**: Should be done before or alongside P1.2

---

### Task P2.3: Model-Level Validation Constraints

**Status**: Not Started
**Priority**: P2 - Medium
**Complexity**: Low (1-2 hours)

**Description**:
Add SQLAlchemy validators to prevent invalid data at model level.

**Files to Modify**:
- `app/models/product.py`

**Changes Required**:

1. **Add Field Validators**:
   ```python
   from sqlalchemy.orm import validates

   class PricingTier(Base):
       __tablename__ = "pricing_tiers"

       # ... existing fields ...

       @validates('price')
       def validate_price(self, key, value):
           if value is None:
               raise ValueError("Price cannot be NULL")
           if value <= 0:
               raise ValueError(f"Price must be positive, got {value}")
           if value > 10000:
               raise ValueError(f"Price seems unreasonably high: {value}")
           return value

       @validates('tier')
       def validate_tier(self, key, value):
           valid_tiers = ['A', 'B', 'C', 'D']
           if value not in valid_tiers:
               raise ValueError(f"Invalid tier '{value}', must be one of {valid_tiers}")
           return value

       @validates('color_type')
       def validate_color_type(self, key, value):
           valid_colors = ['standard', 'custom']
           if value not in valid_colors:
               raise ValueError(f"Invalid color_type '{value}', must be one of {valid_colors}")
           return value
   ```

2. **Add Database Constraints**:
   ```python
   # In table definition
   __table_args__ = (
       CheckConstraint('price > 0', name='check_price_positive'),
       CheckConstraint('tier IN ("A", "B", "C", "D")', name='check_tier_valid'),
       CheckConstraint('color_type IN ("standard", "custom")', name='check_color_valid'),
       UniqueConstraint('product_id', 'tier', 'color_type', 'effective_date',
                       name='uix_pricing_tier')
   )
   ```

3. **Create Migration**:
   ```bash
   alembic revision -m "add_model_validation_constraints"
   ```

**Success Criteria**:
- [ ] Cannot insert PricingTier with price ≤ 0
- [ ] Cannot insert invalid tier or color_type
- [ ] Validation errors are descriptive
- [ ] Migration applied successfully to dev/staging/prod

**Testing Approach**:
```python
# tests/test_models.py
def test_price_validation():
    with pytest.raises(ValueError, match="Price must be positive"):
        tier = PricingTier(
            product_id=1,
            tier='A',
            color_type='standard',
            price=0  # Invalid
        )
        db.add(tier)
        db.commit()
```

**Dependencies**: P1.4 (data cleanup should be done first)

---

### Task P2.4: Improve Description Matching Robustness

**Status**: Not Started
**Priority**: P2 - Medium
**Complexity**: Medium (3-4 hours)

**Description**:
Enhance fuzzy matching algorithm with better Chinese text handling and scoring.

**Files to Modify**:
- `app/services/product_name_matcher.py`

**Changes Required**:

1. **Add Text Normalization**:
   ```python
   from opencc import OpenCC

   cc = OpenCC('t2s')  # Traditional to Simplified

   def normalize_chinese_text(text: str) -> str:
       """Normalize Chinese text for matching."""
       # Convert traditional to simplified
       text = cc.convert(text)

       # Remove punctuation except spaces
       text = re.sub(r'[^\w\s]', '', text)

       # Normalize whitespace
       text = ' '.join(text.split())

       return text.strip()
   ```

2. **Implement Multi-Strategy Matching**:
   ```python
   def match_product_by_description_enhanced(
       db: Session,
       description: str,
       threshold: float = 0.70
   ) -> List[Product]:
       """
       Multi-strategy matching:
       1. Exact substring match (100% confidence)
       2. Token set ratio (fuzzy)
       3. Partial ratio (flexible)
       4. Phonetic similarity (experimental)
       """
       desc_norm = normalize_chinese_text(description)

       candidates = db.query(Product).all()
       matches = []

       for product in candidates:
           name_norm = normalize_chinese_text(product.name_zh or "")

           # Strategy 1: Exact substring
           if desc_norm in name_norm or name_norm in desc_norm:
               product.match_score = 100
               product.match_strategy = "exact_substring"
               matches.append(product)
               continue

           # Strategy 2: Token set ratio (order-independent)
           score_token_set = fuzz.token_set_ratio(desc_norm, name_norm)

           # Strategy 3: Partial ratio (flexible)
           score_partial = fuzz.partial_ratio(desc_norm, name_norm)

           # Take best score
           best_score = max(score_token_set, score_partial)

           if best_score >= threshold * 100:
               product.match_score = best_score
               product.match_strategy = "fuzzy"
               matches.append(product)

       # Sort by score descending
       matches.sort(key=lambda p: p.match_score, reverse=True)

       return matches
   ```

3. **Add Caching for Performance**:
   ```python
   from functools import lru_cache

   @lru_cache(maxsize=1000)
   def get_normalized_product_names(db_session_id: int) -> dict:
       """Cache normalized product names per session."""
       # In practice, use Redis or similar for multi-process caching
       return {
           p.product_id: normalize_chinese_text(p.name_zh)
           for p in db.query(Product).all()
       }
   ```

**Success Criteria**:
- [ ] Handles traditional/simplified Chinese interchangeably
- [ ] Multi-strategy matching improves recall
- [ ] Performance <100ms for full product catalog scan
- [ ] Test coverage for edge cases (punctuation, whitespace variants)

**Testing Approach**:
```python
# tests/test_product_name_matcher.py
def test_traditional_simplified_matching():
    # Traditional Chinese
    matches = match_product_by_description(db, "兒童分體簡易")
    assert len(matches) > 0

    # Simplified Chinese
    matches = match_product_by_description(db, "儿童分体简易")
    assert len(matches) > 0

    # Both should return same products
```

**Dependencies**: None (but enhances P1.1)

---

## Priority 3: Enhancement (Future Improvements)

Nice-to-have features that improve the product but aren't critical.

### Task P3.1: Expand Test Scenario Coverage

**Status**: Not Started
**Priority**: P3 - Enhancement
**Complexity**: Medium (2-3 hours)

**Description**:
Expand test scenarios from 13 to 23 cases covering more edge cases and query patterns.

**Files to Create/Modify**:
- `tests/test_scenarios.py` (new comprehensive test suite)
- `docs/TEST_SCENARIOS.md` (test case documentation)

**Changes Required**:

1. **Add Test Cases for Missing Scenarios**:
   ```
   Additional scenarios to test:
   14. Multi-product comparison (A vs B vs C)
   15. Price range with material filter
   16. Top N with combined filters (material + tier)
   17. Unicode edge cases (emoji, special chars)
   18. Very long product descriptions
   19. Ambiguous tier specifications (级 vs 等)
   20. Multiple materials in one query
   21. Price equality ("一样贵的")
   22. Percentile queries ("前10%")
   23. Batch queries (multiple products in one request)
   ```

2. **Create Automated Test Runner**:
   ```python
   # tests/test_scenarios.py
   import pytest
   from tests.fixtures.scenario_definitions import SCENARIOS

   @pytest.mark.parametrize("scenario", SCENARIOS, ids=lambda s: s["id"])
   def test_scenario(scenario, db, client):
       """Run all defined scenarios."""
       response = client.post("/api/query", json={"query": scenario["query"]})

       assert response.status_code == 200
       result = response.json()

       # Validate expected outcome
       if "expected_status" in scenario:
           assert result["status"] == scenario["expected_status"]

       if "expected_products" in scenario:
           actual_codes = [p["product_code"] for p in result["products"]]
           assert set(actual_codes) == set(scenario["expected_products"])
   ```

3. **Generate HTML Test Report**:
   ```bash
   pytest tests/test_scenarios.py --html=docs/test_report.html --self-contained-html
   ```

**Success Criteria**:
- [ ] 23 test scenarios defined and documented
- [ ] All scenarios pass (100% success rate)
- [ ] Test report generated showing results
- [ ] CI/CD integration runs scenarios on every commit

**Testing Approach**:
```bash
# Run all scenarios
pytest tests/test_scenarios.py -v

# Generate detailed report
python scripts/run_scenario_tests.py --output docs/SCENARIO_TEST_RESULTS_$(date +%Y%m%d_%H%M%S).md
```

**Dependencies**: P0.* and P1.* should be completed first

---

### Task P3.2: Query Performance Monitoring

**Status**: Not Started
**Priority**: P3 - Enhancement
**Complexity**: Medium (3-4 hours)

**Description**:
Add performance monitoring, metrics collection, and alerting for slow queries.

**Files to Create/Modify**:
- `app/middleware/metrics.py` (new)
- `app/api/routes/metrics.py` (new endpoint)
- `docker-compose.yml` (add Prometheus/Grafana)

**Changes Required**:

1. **Add Prometheus Metrics**:
   ```python
   # app/middleware/metrics.py
   from prometheus_client import Counter, Histogram, generate_latest

   query_count = Counter('queries_total', 'Total queries processed', ['status'])
   query_duration = Histogram('query_duration_seconds', 'Query processing time')

   @app.middleware("http")
   async def metrics_middleware(request: Request, call_next):
       if request.url.path == "/api/query":
           with query_duration.time():
               response = await call_next(request)

           status = response.headers.get('X-Query-Status', 'unknown')
           query_count.labels(status=status).inc()

           return response
       return await call_next(request)
   ```

2. **Add Metrics Endpoint**:
   ```python
   # app/api/routes/metrics.py
   from prometheus_client import generate_latest, CONTENT_TYPE_LATEST

   @router.get("/metrics")
   def metrics():
       return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)
   ```

3. **Configure Monitoring Stack**:
   ```yaml
   # docker-compose.yml
   prometheus:
     image: prom/prometheus
     volumes:
       - ./prometheus.yml:/etc/prometheus/prometheus.yml
     ports:
       - "9090:9090"

   grafana:
     image: grafana/grafana
     ports:
       - "3000:3000"
     environment:
       - GF_SECURITY_ADMIN_PASSWORD=admin
   ```

4. **Create Grafana Dashboard**:
   - Query rate (queries/sec)
   - P50, P95, P99 latency
   - Error rate by error_type
   - Top 10 slowest queries

**Success Criteria**:
- [ ] Metrics endpoint exposed at /metrics
- [ ] Prometheus scraping metrics successfully
- [ ] Grafana dashboard showing key metrics
- [ ] Alerting configured for high error rates or slow queries

**Dependencies**: P2.1 (logging) should be implemented first

---

### Task P3.3: Query Result Caching

**Status**: Not Started
**Priority**: P3 - Enhancement
**Complexity**: Medium (3-4 hours)

**Description**:
Implement Redis caching for frequent queries to reduce database load and improve response times.

**Files to Modify**:
- `app/services/cache.py` (new)
- `app/api/routes/query.py`
- `docker-compose.yml` (add Redis)
- `requirements.txt` (add redis-py)

**Changes Required**:

1. **Add Redis Service**:
   ```yaml
   # docker-compose.yml
   redis:
     image: redis:7-alpine
     ports:
       - "6379:6379"
     volumes:
       - redis-data:/data
   ```

2. **Implement Cache Layer**:
   ```python
   # app/services/cache.py
   import redis
   import json
   from hashlib import sha256

   redis_client = redis.Redis(host='redis', port=6379, decode_responses=True)

   def cache_key(query: str, user_context: dict = None) -> str:
       """Generate cache key from query and context."""
       key_parts = [query.lower().strip()]
       if user_context:
           key_parts.append(json.dumps(user_context, sort_keys=True))

       key_str = "|".join(key_parts)
       return f"query:{sha256(key_str.encode()).hexdigest()}"

   def get_cached_result(query: str, user_context: dict = None):
       """Retrieve cached query result."""
       key = cache_key(query, user_context)
       cached = redis_client.get(key)

       if cached:
           return json.loads(cached)
       return None

   def cache_result(query: str, result: dict, ttl: int = 300, user_context: dict = None):
       """Cache query result with TTL."""
       key = cache_key(query, user_context)
       redis_client.setex(key, ttl, json.dumps(result))
   ```

3. **Integrate with Query Endpoint**:
   ```python
   # app/api/routes/query.py
   @router.post("/query")
   async def query_price(request: QueryRequest):
       # Check cache first
       cached_result = get_cached_result(request.query)
       if cached_result:
           logger.info("Cache hit", extra={"query": request.query})
           return cached_result

       # Process query
       result = process_query(db, request.query)

       # Cache successful results
       if result.get("status") == "success":
           cache_result(request.query, result, ttl=300)  # 5 minutes

       return result
   ```

4. **Add Cache Invalidation**:
   ```python
   # Invalidate cache when prices update
   @router.post("/admin/pricing/update")
   def update_pricing(pricing_data: PricingUpdate):
       # Update database
       update_pricing_in_db(pricing_data)

       # Invalidate related cache entries
       pattern = f"query:*{pricing_data.product_code}*"
       for key in redis_client.scan_iter(pattern):
           redis_client.delete(key)
   ```

**Success Criteria**:
- [ ] Cache hit rate >50% for repeated queries
- [ ] Response time <50ms for cached queries
- [ ] Cache invalidation works correctly on data updates
- [ ] Redis memory usage stays under limits

**Dependencies**: None (independent enhancement)

---

### Task P3.4: Admin Data Quality Dashboard

**Status**: Not Started
**Priority**: P3 - Enhancement
**Complexity**: High (6-8 hours)

**Description**:
Create admin dashboard for monitoring data quality metrics and manually fixing issues.

**Files to Create**:
- `app/api/routes/admin.py` (admin endpoints)
- `app/templates/admin/dashboard.html` (UI)
- `app/services/data_quality.py` (metrics collection)

**Changes Required**:

1. **Create Data Quality Service**:
   ```python
   # app/services/data_quality.py
   class DataQualityMetrics:
       def __init__(self, db: Session):
           self.db = db

       def get_metrics(self) -> dict:
           return {
               "products_total": self.count_products(),
               "products_without_pricing": self.count_products_no_pricing(),
               "zero_price_entries": self.count_zero_prices(),
               "missing_descriptions": self.count_missing_descriptions(),
               "orphaned_pricing": self.count_orphaned_pricing(),
               "last_updated": datetime.now().isoformat()
           }

       def get_products_needing_review(self) -> List[dict]:
           """Get products with data quality issues."""
           issues = []

           # Products with no pricing
           no_pricing = self.db.query(Product).outerjoin(PricingTier).filter(
               PricingTier.id == None
           ).all()

           for product in no_pricing:
               issues.append({
                   "product_code": product.product_code,
                   "issue_type": "no_pricing",
                   "severity": "high"
               })

           return issues
   ```

2. **Create Admin API Endpoints**:
   ```python
   # app/api/routes/admin.py
   @router.get("/admin/data-quality/metrics")
   def get_data_quality_metrics(db: Session = Depends(get_db)):
       """Get data quality metrics."""
       metrics_service = DataQualityMetrics(db)
       return metrics_service.get_metrics()

   @router.get("/admin/data-quality/issues")
   def get_data_quality_issues(db: Session = Depends(get_db)):
       """Get list of products with issues."""
       metrics_service = DataQualityMetrics(db)
       return metrics_service.get_products_needing_review()

   @router.post("/admin/pricing/fix/{product_code}")
   def fix_product_pricing(
       product_code: str,
       pricing_data: PricingUpdate,
       db: Session = Depends(get_db)
   ):
       """Manually set pricing for a product."""
       # Validation + update logic
       pass
   ```

3. **Create Simple Dashboard UI** (optional):
   ```html
   <!-- app/templates/admin/dashboard.html -->
   <div class="dashboard">
     <h1>Data Quality Dashboard</h1>

     <div class="metrics">
       <div class="metric-card">
         <h3>Products Without Pricing</h3>
         <span class="value" id="no-pricing">-</span>
       </div>

       <div class="metric-card">
         <h3>Zero Price Entries</h3>
         <span class="value" id="zero-prices">-</span>
       </div>
     </div>

     <div class="issues-list">
       <h2>Products Needing Review</h2>
       <table id="issues-table">
         <!-- Populated via JS -->
       </table>
     </div>
   </div>
   ```

**Success Criteria**:
- [ ] Dashboard shows real-time data quality metrics
- [ ] Admin can view list of problematic products
- [ ] Admin can manually fix pricing issues via UI
- [ ] Audit log tracks all manual changes

**Dependencies**: P1.4 (data audit script) should be completed first

---

## Implementation Strategy

### Phase 1: Critical Fixes (Week 1)
**Goal**: Fix data integrity issues and prevent incorrect data display

- P0.1: Fix $0.00 price display (Day 1)
- P0.2: Verify pick_price() function (Day 2)
- P0.3: Fix error propagation (Day 1)
- P1.4: Data quality audit (Days 3-5)

**Success Criteria**: No $0.00 prices in API, all database functions documented

---

### Phase 2: User Experience (Week 2)
**Goal**: Fix query processing issues and improve result quality

- P1.1: Fix description-based comparison (Days 1-2)
- P1.2: Improve GT10 confirmation options (Day 3)
- P1.3: Add graceful errors (Day 1)
- P2.1: Add comprehensive logging (Day 4-5)

**Success Criteria**: >95% query success rate, clear error messages

---

### Phase 3: Robustness (Week 3)
**Goal**: Harden system against edge cases

- P2.2: Enhanced material inference (Days 1-2)
- P2.3: Model validation (Day 1)
- P2.4: Improve description matching (Days 2-3)
- P3.1: Expand test coverage (Day 4-5)

**Success Criteria**: All 23 test scenarios passing

---

### Phase 4: Enhancements (Week 4+)
**Goal**: Performance and operations improvements

- P3.2: Performance monitoring (Optional)
- P3.3: Query caching (Optional)
- P3.4: Admin dashboard (Optional)

**Success Criteria**: <100ms P95 latency, cache hit rate >50%

---

## Testing Strategy

### Continuous Validation

After each task completion:

1. **Run scenario tests**:
   ```bash
   python scripts/run_scenario_tests.py
   ```

2. **Check metrics**:
   - Success rate (target: >95%)
   - No $0.00 prices
   - Error messages are clear
   - Response times <500ms P95

3. **Manual smoke tests**:
   - Query in Chinese
   - Query with product code
   - Comparison query
   - Range query
   - Invalid product query

### Regression Prevention

- Add test case for each fixed bug
- Run full test suite before merging
- Monitor error rates in production

---

## Rollout Plan

### Development
1. Implement fixes on feature branches
2. Run test suite locally
3. Create PR with test results

### Staging
1. Deploy to staging environment
2. Run full scenario test suite
3. Manual QA testing
4. Performance testing (load test)

### Production
1. Deploy during low-traffic window
2. Monitor error rates and latency
3. Keep previous version ready for rollback
4. Gradual rollout (10% → 50% → 100%)

---

## Success Metrics

### Before Improvements
- Query success rate: 69% (9/13)
- Products with $0.00 prices: 3+
- Unclear error messages: Multiple cases
- Test coverage: 13 scenarios

### After Improvements (Targets)
- Query success rate: >95%
- Products with $0.00 prices: 0
- Clear error messages: 100%
- Test coverage: 23+ scenarios
- Response time P95: <500ms
- Cache hit rate: >50% (if caching implemented)

---

## Maintenance

### Weekly Tasks
- Review data quality metrics
- Check for new $0.00 price entries
- Monitor query error rates
- Review slow query logs

### Monthly Tasks
- Audit database for data quality
- Review and update test scenarios
- Performance optimization review
- Security audit

---

## Document Status

| Task ID | Priority | Status | Owner | ETA |
|---------|----------|--------|-------|-----|
| P0.1 | Critical | Not Started | - | - |
| P0.2 | Critical | Not Started | - | - |
| P0.3 | Critical | Not Started | - | - |
| P1.1 | High | Not Started | - | - |
| P1.2 | High | Not Started | - | - |
| P1.3 | High | Not Started | - | - |
| P1.4 | High | Not Started | - | - |
| P2.1 | Medium | Not Started | - | - |
| P2.2 | Medium | Not Started | - | - |
| P2.3 | Medium | Not Started | - | - |
| P2.4 | Medium | Not Started | - | - |
| P3.1 | Enhancement | Not Started | - | - |
| P3.2 | Enhancement | Not Started | - | - |
| P3.3 | Enhancement | Not Started | - | - |
| P3.4 | Enhancement | Not Started | - | - |

---

**Last Updated**: 2025-11-11
**Next Review**: After Phase 1 completion
