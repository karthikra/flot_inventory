# Plan: Product Enrichment + Insurance Features

## Context

After detecting items via the vision pipeline, users currently get a name, description, category, and a rough AI-estimated value. For insurance and moving/packaging purposes, they need **real product data**: brand, model, replacement cost from actual retailers, and physical dimensions. The goal is to enrich detected items with web-sourced product details and add insurance-ready reporting.

## Phased Approach

### Phase 1: Enhanced Vision Prompt + Data Model (No new APIs, zero cost)

Qwen3-VL already sees the items — we just need to ask it for more detail (brand, model, material, estimated dimensions). Add fields to store this data.

#### 1A. Data Model — Add columns to `app/models/item.py`

```
brand              VARCHAR(200)   — manufacturer/brand
model_number       VARCHAR(200)   — model name or number
serial_number      VARCHAR(200)   — unique identifier (user-entered)
material           VARCHAR(200)   — primary material
width_cm           FLOAT          — for packaging
height_cm          FLOAT          — for packaging
depth_cm           FLOAT          — for packaging
weight_kg          FLOAT          — for shipping
replacement_cost   FLOAT          — current retail replacement price
purchase_date      VARCHAR(50)    — when they bought it
purchase_price     FLOAT          — what they paid
```

#### 1B. SQLite Migration — `app/main.py` lifespan

No Alembic — add a startup helper that runs `ALTER TABLE items ADD COLUMN ...` for each missing column (check via `PRAGMA table_info`). Safe to run repeatedly.

#### 1C. Schema Updates

- `app/schemas/capture.py` — Add `brand`, `model_number`, `material`, `estimated_dimensions` to `DetectedObject` and `CaptureConfirmItem`
- `app/schemas/item.py` — Add all new fields to `ItemCreate`, `ItemUpdate`, `ItemOut`

#### 1D. Enhanced Qwen3-VL Prompt — `app/services/local_vision.py`

Update `QWEN_PROMPT` to request:
- `brand` — manufacturer if visible/identifiable
- `model_number` — model name/number if visible
- `material` — primary material (wood, metal, plastic, fabric, etc.)
- `estimated_dimensions_cm` — `{width, height, depth}` estimated using nearby objects for scale

Update `_merge_detections` to carry these new fields through from Qwen results to DetectedObject.

#### 1E. Review Template — `app/templates/capture/review.html`

Add collapsible "Product Details" section per item with editable fields: brand, model, material, dimensions (W/H/D), replacement cost, purchase date/price.

#### 1F. Confirm Flow — `app/routers/capture.py` + `app/viewmodels/capture_vm.py`

Parse new form fields in `confirm_items` and persist to Item model.

#### 1G. Item Detail Page — `app/templates/items/detail.html` + `edit.html`

Show product details card and insurance info card. Add fields to edit form.

---

### Phase 2: Web Product Search (SerpAPI Google Shopping)

A "Look Up" button per item that searches retailers for pricing and specs.

#### 2A. New Service — `app/services/product_search.py`

```python
class ProductSearchService:
    async def search_product(query: str, category: str) -> list[ProductSearchResult]
    async def visual_search(image_path: str) -> list[ProductSearchResult]
```

**Primary backend**: SerpAPI Google Shopping ($50/mo, 5000 searches) — returns product listings with title, price, source, dimensions, specs from multiple retailers.

**Free fallback**: If no SerpAPI key configured, use Qwen3-VL with a "product research" prompt to estimate typical retail specs/pricing from its training data.

Config: `serpapi_api_key: str = ""` in `app/config.py`

#### 2B. New Schema — `app/schemas/product_search.py`

```python
class ProductSearchResult(BaseModel):
    title: str
    price: float | None
    source: str | None        # "Amazon", "Best Buy", etc.
    url: str | None
    thumbnail_url: str | None
    dimensions: dict | None   # {width_cm, height_cm, depth_cm}
    brand: str | None
    model_number: str | None
    specs: dict | None        # arbitrary key-value specs
```

#### 2C. HTMX "Look Up" Button

On review page and item detail page — `hx-get="/items/enrich?name=...&brand=...&category=..."` returns a partial with clickable result cards. Clicking a result fills the parent form fields via JS.

#### 2D. Enrichment Endpoint — `app/routers/items.py`

`GET /items/enrich` — searches product, returns partial template
`POST /items/{id}/enrich` — applies selected result to item

---

### Phase 3: Visual Product Search (SerpAPI Google Lens)

Use the captured frame crop for reverse image search to identify exact products.

- `app/services/image_service.py` — Add `crop_to_bbox()` method
- `app/services/product_search.py` — Add `visual_search()` using SerpAPI Google Lens endpoint
- "Visual Search" button on item detail page using item's primary image

---

### Phase 4: Insurance Reporting

#### 4A. Insurance Summary Page

New router `app/routers/insurance.py` + viewmodel + template:
- Total inventory value (sum of `replacement_cost` or `estimated_value` fallback)
- Value breakdown by room and by category
- Items missing key data (no replacement cost, no photo, no serial for electronics)
- High-value items (>$500) flagged for documentation completeness

#### 4B. Enhanced PDF/CSV Export — `app/services/export_service.py`

Insurance-mode export includes: brand, model, serial number, dimensions, replacement cost, purchase info, condition, photo evidence.

#### 4C. Depreciation Calculator — `app/services/value_estimator.py`

Pure calculation using category-based rates (electronics: ~25%/yr, furniture: ~10%/yr, etc.). Shown on item detail page: `actual_cash_value = replacement_cost × (1 - rate)^age`.

---

## Files Changed Summary

| Phase | Files | New | Modified |
|-------|-------|-----|----------|
| 1 | 10 | 0 | `item.py`, `main.py`, `capture.py` (schema), `item.py` (schema), `local_vision.py`, `review.html`, `capture.py` (router), `capture_vm.py`, `detail.html`, `edit.html` |
| 2 | 5 | `product_search.py` (service), `product_search.py` (schema), `enrich_results.html` | `config.py`, `items.py` (router) |
| 3 | 2 | 0 | `product_search.py`, `image_service.py` |
| 4 | 6 | `insurance.py` (router), `insurance_vm.py`, `summary.html` | `export_service.py`, `value_estimator.py`, `main.py` |

## Key Design Decisions

1. **All fields on Item model** — no separate enrichment table. Keeps queries simple, follows the Book subclass pattern.
2. **`replacement_cost` vs `estimated_value`** — keep both. `estimated_value` is the AI's quick guess; `replacement_cost` is the enriched market-based value. Insurance reports prefer `replacement_cost`, fall back to `estimated_value`.
3. **Dimensions in centimeters** — metric internally, can display inches in UI.
4. **Graceful degradation** — no SerpAPI key? LLM fallback. No enrichment? App works exactly as before. Missing data flagged in insurance summary, not blocked.
5. **Manual "Look Up" per item** — not auto-enriching everything. Keeps API costs predictable, lets user verify results.
6. **Depreciation is computed, not stored** — calculation from purchase_price + purchase_date + category rate. No stale data.

## Dependency

- `google-search-results` (SerpAPI Python client) — only for Phase 2+, optional

## Verification

1. Capture an item → review page shows brand/model/material/dimensions from Qwen
2. Edit dimensions on review page → saved to DB → visible on item detail
3. Click "Look Up" on item → SerpAPI results appear → click one → fields populated
4. Insurance summary page → shows total value by room, flags items missing data
5. Export PDF → includes brand, model, serial, dimensions, replacement cost
