# Home Inventory Application — Full Plan

## Vision

A mobile-first home inventory application where you walk through rooms recording video,
the system identifies objects in real-time via vision LLMs, and builds a rich database
of everything you own — complete with images, descriptions, locations, values, and
book metadata. When the system needs more detail (book spines, serial numbers, fine
print), it prompts you to switch to image capture mode for higher-resolution grabs.

---

## Architecture: MVVM (Model-View-ViewModel)

```
┌─────────────────────────────────────────────────────────────┐
│                        VIEW LAYER                           │
│  Jinja2 Templates + HTMX                                   │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │Dashboard │ │Room View │ │Item View │ │Video Capture │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│         ▲            ▲           ▲             ▲            │
│         │   HTMX requests / SSE streams       │            │
│─────────┼────────────┼───────────┼─────────────┼────────────│
│         ▼            ▼           ▼             ▼            │
│                   VIEWMODEL LAYER                           │
│  FastAPI Routers — transform models into view state         │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │dashboard │ │  rooms   │ │  items   │ │   capture    │   │
│  │_viewmodel│ │_viewmodel│ │_viewmodel│ │  _viewmodel  │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│         ▲            ▲           ▲             ▲            │
│─────────┼────────────┼───────────┼─────────────┼────────────│
│         ▼            ▼           ▼             ▼            │
│                    MODEL LAYER                              │
│  Domain logic, services, data access                        │
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────┐   │
│  │ SQLAlchemy│ │ Vision  │ │  Book   │ │   Video      │   │
│  │  Models   │ │ Service │ │ Service │ │  Processor   │   │
│  └──────────┘ └──────────┘ └──────────┘ └──────────────┘   │
│         ▲            ▲           ▲             ▲            │
│─────────┼────────────┼───────────┼─────────────┼────────────│
│         ▼            ▼           ▼             ▼            │
│                  DATA / INFRA LAYER                         │
│  SQLite DB │ Filesystem (images) │ External APIs            │
└─────────────────────────────────────────────────────────────┘
```

### MVVM Responsibilities

**Model** — Pure domain logic, zero knowledge of views:
- SQLAlchemy ORM models (Item, Book, Room, Tag, etc.)
- Service classes (VisionService, BookService, VideoProcessor, ExportService)
- Repository pattern for data access
- Business rules (duplicate detection, value estimation, condition tracking)

**ViewModel** — Bridges model and view, holds view state:
- One viewmodel module per feature (dashboard, rooms, items, capture, search)
- Transforms raw model data into display-ready structures
- Handles form validation via Pydantic schemas
- Manages capture session state (video vs image mode, current room, pending items)
- Exposes SSE event streams for real-time video processing feedback

**View** — Presentation only, no logic:
- Jinja2 templates rendering viewmodel output
- HTMX attributes for dynamic updates without JS
- SSE listeners for real-time feedback during video capture
- CSS in separate files, mobile-first responsive design

---

## Project Structure

```
inventory_analysis/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI app factory, lifespan, middleware
│   ├── config.py                  # Settings via pydantic-settings
│   ├── database.py                # Async SQLAlchemy engine, session factory
│   │
│   ├── models/                    # MODEL LAYER — domain models
│   │   ├── __init__.py
│   │   ├── base.py                # Declarative base, common mixins
│   │   ├── room.py                # Room model
│   │   ├── item.py                # Item model (polymorphic base)
│   │   ├── book.py                # Book model (extends Item)
│   │   ├── tag.py                 # Tag model + association table
│   │   └── capture_session.py     # Video/image capture session tracking
│   │
│   ├── schemas/                   # Pydantic schemas (shared by model & viewmodel)
│   │   ├── __init__.py
│   │   ├── room.py
│   │   ├── item.py
│   │   ├── book.py
│   │   ├── capture.py             # Video frame analysis results, mode switch signals
│   │   └── export.py              # Export format schemas
│   │
│   ├── repositories/              # Data access layer
│   │   ├── __init__.py
│   │   ├── base.py                # Generic async CRUD repository
│   │   ├── room_repo.py
│   │   ├── item_repo.py
│   │   └── book_repo.py
│   │
│   ├── services/                  # MODEL LAYER — business logic
│   │   ├── __init__.py
│   │   ├── vision.py              # VLM integration (Claude Vision API)
│   │   ├── video_processor.py     # Frame extraction, keyframe selection, batch analysis
│   │   ├── book_service.py        # ISBN lookup, Open Library API, barcode scanning
│   │   ├── duplicate_detector.py  # Embedding similarity for duplicate flagging
│   │   ├── value_estimator.py     # Replacement value estimation via VLM
│   │   ├── export_service.py      # CSV/PDF/insurance report generation
│   │   └── image_service.py       # Thumbnail generation, storage management
│   │
│   ├── viewmodels/                # VIEWMODEL LAYER
│   │   ├── __init__.py
│   │   ├── dashboard_vm.py        # Stats, recent items, room summary
│   │   ├── room_vm.py             # Room detail, item grid, floor plan state
│   │   ├── item_vm.py             # Item detail, edit form, multi-image management
│   │   ├── capture_vm.py          # Video/image capture session, mode switching logic
│   │   ├── search_vm.py           # Search/filter state, results formatting
│   │   └── export_vm.py           # Export options, progress tracking
│   │
│   ├── routers/                   # FastAPI routers (thin — delegate to viewmodels)
│   │   ├── __init__.py
│   │   ├── dashboard.py
│   │   ├── rooms.py
│   │   ├── items.py
│   │   ├── capture.py             # Upload, video stream, SSE endpoint
│   │   ├── search.py
│   │   └── export.py
│   │
│   ├── templates/                 # VIEW LAYER — Jinja2
│   │   ├── base.html              # Mobile-first shell, nav, HTMX + SSE setup
│   │   ├── dashboard.html
│   │   ├── rooms/
│   │   │   ├── list.html
│   │   │   ├── detail.html
│   │   │   └── floor_plan.html
│   │   ├── items/
│   │   │   ├── grid.html
│   │   │   ├── detail.html
│   │   │   └── edit.html
│   │   ├── capture/
│   │   │   ├── session.html       # Video + image capture UI
│   │   │   ├── review.html        # Review identified items before saving
│   │   │   └── partials/
│   │   │       ├── detected_item.html
│   │   │       └── mode_switch_prompt.html
│   │   ├── search/
│   │   │   └── results.html
│   │   └── export/
│   │       └── options.html
│   │
│   └── static/
│       ├── css/
│       │   ├── base.css           # Design system, variables, dark theme
│       │   ├── dashboard.css
│       │   ├── capture.css
│       │   └── components.css     # Cards, buttons, badges, modals
│       └── js/
│           └── capture.js         # Minimal JS: camera/video MediaStream API only
│
├── data/
│   ├── inventory.db               # SQLite database
│   └── images/                    # Stored images organized by room
│       ├── thumbnails/
│       └── originals/
│
├── tests/
│   ├── test_services/
│   ├── test_viewmodels/
│   └── test_routers/
│
├── pyproject.toml
└── PLAN.md
```

---

## Data Model

### Entity Relationship Diagram

```
┌──────────────┐       ┌──────────────────────────────────────┐
│    Room      │       │              Item                    │
├──────────────┤       ├──────────────────────────────────────┤
│ id (PK)      │──┐    │ id (PK)                              │
│ name         │  │    │ name                                 │
│ description  │  │    │ description                          │
│ floor        │  └───▶│ room_id (FK)                         │
│ created_at   │       │ category                             │
│ updated_at   │       │ image_path                           │
└──────────────┘       │ thumbnail_path                       │
                       │ confidence_score                     │
┌──────────────┐       │ estimated_value                      │
│    Tag       │       │ condition (new/good/fair/poor)       │
├──────────────┤       │ status (keep/sell/donate/trash/null) │
│ id (PK)      │◀─┐    │ source_type (video_frame/image)      │
│ name         │  │    │ source_session_id                    │
│ color        │  │    │ type (discriminator: item/book)      │
└──────────────┘  │    │ created_at                           │
                  │    │ updated_at                           │
┌──────────────┐  │    └──────────────────────────────────────┘
│  ItemTag     │  │                    ▲
│ (junction)   │──┘                    │ inheritance
├──────────────┤          ┌────────────┴──────────────┐
│ item_id (FK) │          │         Book              │
│ tag_id (FK)  │          ├───────────────────────────┤
└──────────────┘          │ id (PK, FK → Item.id)     │
                          │ title                     │
┌──────────────────┐      │ author                    │
│ CaptureSession   │      │ isbn                      │
├──────────────────┤      │ publisher                 │
│ id (PK)          │      │ genre                     │
│ room_id (FK)     │      │ page_count                │
│ mode (video/img) │      │ year_published            │
│ video_path       │      │ cover_image_path          │
│ frame_count      │      └───────────────────────────┘
│ items_found      │
│ started_at       │      ┌───────────────────────────┐
│ completed_at     │      │      ItemImage             │
└──────────────────┘      ├───────────────────────────┤
                          │ id (PK)                   │
                          │ item_id (FK)              │
                          │ image_path                │
                          │ image_type                │
                          │  (front/back/serial/      │
                          │   damage/receipt)         │
                          │ created_at                │
                          └───────────────────────────┘
```

---

## Video Walkthrough Pipeline

This is the core differentiating feature. The flow:

### Phase 1: Video Capture (on device)

```
User opens Capture → selects Room → starts video recording
         │
         ▼
Browser MediaStream API records video
         │
         ▼
Video chunks uploaded progressively via fetch()
(or full video uploaded after recording stops)
```

### Phase 2: Frame Extraction & Keyframe Selection (server)

```
Uploaded video
         │
         ▼
FFmpeg extracts frames (1-2 fps to avoid redundancy)
         │
         ▼
Keyframe selector filters out:
  - Blurry frames (Laplacian variance threshold)
  - Near-duplicate frames (perceptual hash / SSIM comparison)
  - Frames with excessive motion blur
         │
         ▼
Yields 10-30 quality keyframes per room walkthrough
```

### Phase 3: Batch VLM Analysis

```
Keyframes
         │
         ▼
Each keyframe sent to Claude Vision API with structured prompt:
  "Identify every distinct object in this image.
   For each object return JSON:
   {name, description, category, is_book, needs_closer_look, confidence}"
         │
         ▼
Results aggregated, cross-frame deduplication applied
  (same object seen from different angles → merged)
         │
         ▼
Items flagged with needs_closer_look = true trigger
  MODE SWITCH PROMPT → tells user to capture specific items
  in image mode for better detail
```

### Phase 4: Mode Switch Logic

The system prompts the user to switch to image mode when:

| Trigger | Example |
|---------|---------|
| **Book detected** | Spine visible but title not fully legible |
| **Small text/labels** | Serial numbers, model numbers, brand names |
| **Partially occluded** | Object behind another, only partially visible |
| **High-value guess** | "This looks like it could be expensive — capture closer" |
| **Low confidence** | VLM confidence < 0.7 on identification |
| **Barcode visible** | "I see a barcode — switch to image mode to scan it" |

The prompt appears as an HTMX-pushed notification:

```
┌─────────────────────────────────────────┐
│  📷  Switch to Image Mode               │
│                                         │
│  I found 3 books on the shelf but       │
│  can't read all the titles clearly.     │
│  Take a close-up photo of the spines.   │
│                                         │
│  [Switch to Image Mode]  [Skip]         │
└─────────────────────────────────────────┘
```

### Phase 5: Review & Confirm

```
All identified items displayed in a review grid
         │
         ▼
User can: edit names, fix descriptions, change room,
          delete false positives, merge duplicates,
          add tags, set condition, mark keep/sell/donate
         │
         ▼
Confirmed items saved to database
```

---

## Feature Breakdown

### Feature 1: Room Management
- CRUD for rooms (name, description, floor)
- Room dashboard showing item count, total estimated value
- Simple drag-and-drop floor plan per room (stretch)
  - Canvas-based room outline
  - Drag item icons to approximate positions
  - Stored as JSON coordinate map in Room model

### Feature 2: Video Walkthrough Capture
- MediaStream API for video recording in browser
- Progressive upload or post-recording upload
- Server-side frame extraction via FFmpeg
- Keyframe quality filtering (blur, duplicates, motion)
- Batch VLM analysis of keyframes
- Cross-frame deduplication
- Real-time progress via SSE

### Feature 3: Image Capture Mode
- Direct camera capture (`<input type="file" capture="camera">`)
- Also supports file upload from gallery
- Single-item focused identification
- Higher resolution analysis for fine details
- Barcode/ISBN detection triggers book metadata lookup

### Feature 4: VLM Object Identification
- Claude Vision API as primary backend
- Structured JSON output via constrained prompting
- Category classification (electronics, furniture, kitchenware, books, clothing,
  tools, decor, appliances, sports, toys, other)
- Confidence scoring per item
- Automatic `needs_closer_look` flagging

### Feature 5: Book Detection & Metadata
- VLM reads titles and authors from spines/covers
- If ISBN/barcode visible → pyzbar decodes it
- Open Library API lookup for full metadata:
  - Title, author, publisher, year, page count, genre, cover image
- Google Books API as fallback
- Manual ISBN entry option

### Feature 6: Duplicate Detection
- When a new item is identified, compare against existing items:
  - Text similarity on name + description (fuzzy matching)
  - Image embedding similarity (CLIP or similar lightweight model)
- Flag potential duplicates for user review
- Merge workflow: combine images, keep best description

### Feature 7: Value Estimation
- VLM prompted to estimate replacement value range
- Category-based median values as sanity check
- User can override with actual purchase price
- Track total value per room, per category, and overall

### Feature 8: Condition Tracking
- Condition enum: new, good, fair, poor
- VLM suggests initial condition from image analysis
- User can update over time
- History of condition changes stored

### Feature 9: Moving / Declutter Helper
- Status field on items: keep, sell, donate, trash, null
- Filtered views: "What am I selling?", "Donation pile"
- Bulk actions on item grid

### Feature 10: Multi-Image Per Item
- Additional photos: front, back, serial number, damage, receipt
- OCR on receipt images to extract purchase date and price
- Gallery view on item detail page

### Feature 11: Search & Filter
- Full-text search across names, descriptions, book titles
- Filter by: room, category, tag, condition, status, value range
- Sort by: name, value, date added, condition
- HTMX-powered instant results

### Feature 12: Export & Insurance Mode
- **CSV export**: full inventory spreadsheet
- **PDF report**: formatted with photos, organized by room
  - Insurance-ready layout with item name, description, photo, estimated value
- **Insurance summary**: total value per room, total home value
- **JSON export**: full data backup

### Feature 13: Dashboard
- Total items, total estimated value
- Items by room (bar chart or counts)
- Items by category breakdown
- Recent captures
- Items needing attention (low confidence, needs closer look)
- Quick-capture button

---

## Tech Stack

| Layer | Technology | Rationale |
|-------|-----------|-----------|
| Backend framework | FastAPI (async) | Modern, fast, great for SSE streaming |
| Templates | Jinja2 | Proven, pairs perfectly with HTMX |
| Frontend interactivity | HTMX + SSE | No JS framework, server-driven UI |
| Minimal JS | MediaStream API only | Camera/video access requires JS — nothing else does |
| Database | SQLite + aiosqlite | Zero config, single-file, portable |
| ORM | SQLAlchemy 2.0 (async) | Mature, async support, polymorphic inheritance |
| Validation | Pydantic v2 | Fast, strict, schema generation |
| Vision AI | Claude Vision API | Best multimodal reasoning for identification |
| Video processing | FFmpeg (via ffmpeg-python) | Frame extraction, keyframe analysis |
| Image processing | Pillow | Thumbnails, blur detection, resizing |
| Barcode scanning | pyzbar | ISBN/barcode decoding from images |
| Book metadata | Open Library API | Free, comprehensive, no API key needed |
| Duplicate detection | rapidfuzz + CLIP (optional) | Text fuzzy matching + image similarity |
| PDF export | weasyprint or fpdf2 | HTML-to-PDF for insurance reports |
| CSV export | stdlib csv | Simple, no dependencies |
| Blur detection | OpenCV (cv2) | Laplacian variance for frame quality |
| Perceptual hashing | imagehash | Near-duplicate frame elimination |
| Settings | pydantic-settings | Env-based config with validation |

### Dependencies (pyproject.toml)

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.34",
    "jinja2>=3.1",
    "sqlalchemy[asyncio]>=2.0",
    "aiosqlite>=0.20",
    "pydantic>=2.10",
    "pydantic-settings>=2.7",
    "anthropic>=0.45",
    "pillow>=11.0",
    "python-multipart>=0.0.18",
    "ffmpeg-python>=0.2",
    "pyzbar>=0.1",
    "imagehash>=4.3",
    "opencv-python-headless>=4.10",
    "rapidfuzz>=3.10",
    "httpx>=0.28",
    "fpdf2>=2.8",
    "python-jose>=3.3",
    "sse-starlette>=2.2",
]
```

---

## Implementation Phases

### Phase 1 — Foundation
1. Project scaffolding (directory structure, config, database setup)
2. SQLAlchemy models (Room, Item, Book, Tag, ItemImage, CaptureSession)
3. Async repository layer with generic CRUD
4. Pydantic schemas for all entities
5. Database migrations setup (alembic)

### Phase 2 — Core CRUD & UI Shell
6. Room management (router, viewmodel, templates)
7. Item management (router, viewmodel, templates)
8. Base template with mobile-first responsive layout
9. Dashboard viewmodel and template
10. Static file serving and image storage utilities

### Phase 3 — Image Capture & VLM Integration
11. Image upload endpoint and storage service
12. Claude Vision API integration (VisionService)
13. Structured prompting for object identification
14. Image capture UI (camera + file upload)
15. Capture review flow (edit, confirm, save)

### Phase 4 — Video Walkthrough Pipeline
16. Video upload endpoint
17. FFmpeg frame extraction service
18. Keyframe quality filtering (blur, dedup)
19. Batch VLM analysis with progress tracking
20. Cross-frame object deduplication
21. SSE streaming for real-time progress feedback
22. Mode switch prompt logic and UI

### Phase 5 — Book Intelligence
23. Book detection in VLM pipeline
24. pyzbar barcode/ISBN scanning integration
25. Open Library API client for metadata enrichment
26. Book-specific detail views and edit forms

### Phase 6 — Smart Features
27. Duplicate detection service (fuzzy text + optional image embeddings)
28. Value estimation via VLM prompting
29. Condition assessment from image analysis
30. Multi-image support per item (upload, categorize, gallery)

### Phase 7 — Search, Export & Polish
31. Full-text search with filters
32. CSV export
33. PDF/insurance report generation
34. Moving/declutter status workflow
35. Dashboard charts and statistics
36. Floor plan drag-and-drop (stretch)

### Phase 8 — Testing & Hardening
37. Unit tests for services and viewmodels
38. Integration tests for routers
39. Error handling and edge cases
40. Performance optimization (thumbnail caching, query optimization)

---

## API Endpoints Overview

### Rooms
| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Dashboard |
| GET | `/rooms` | List rooms |
| POST | `/rooms` | Create room |
| GET | `/rooms/{id}` | Room detail with items |
| PUT | `/rooms/{id}` | Update room |
| DELETE | `/rooms/{id}` | Delete room |

### Items
| Method | Path | Description |
|--------|------|-------------|
| GET | `/items` | All items (filterable) |
| GET | `/items/{id}` | Item detail |
| PUT | `/items/{id}` | Update item |
| DELETE | `/items/{id}` | Delete item |
| POST | `/items/{id}/images` | Add image to item |
| PUT | `/items/{id}/status` | Set keep/sell/donate/trash |

### Capture
| Method | Path | Description |
|--------|------|-------------|
| GET | `/capture` | Capture session UI |
| POST | `/capture/image` | Upload image for analysis |
| POST | `/capture/video` | Upload video for processing |
| GET | `/capture/stream/{session_id}` | SSE stream for processing progress |
| POST | `/capture/confirm` | Confirm and save identified items |

### Search & Export
| Method | Path | Description |
|--------|------|-------------|
| GET | `/search` | Search page |
| GET | `/search/results` | HTMX search results partial |
| GET | `/export/csv` | Download CSV |
| GET | `/export/pdf` | Download PDF report |
| GET | `/export/json` | Download JSON backup |

---

## VLM Prompt Design

### Video Frame Analysis Prompt

```
Analyze this image of a room in a home. Identify every distinct object you can see.

For EACH object, return a JSON object with these fields:
- name: Short descriptive name (e.g., "Samsung 55-inch TV")
- description: 2-3 sentence description including color, material, brand if visible, size
- category: One of [electronics, furniture, kitchenware, books, clothing, tools,
  decor, appliances, sports, toys, other]
- is_book: true if this is a book, magazine, or printed material
- needs_closer_look: true if you cannot fully identify this item and a closer
  photo would help (partially hidden, text too small, barcode visible but unreadable)
- closer_look_reason: If needs_closer_look is true, explain why
  (e.g., "Book spine text is too small to read reliably")
- confidence: Float 0.0-1.0 of identification confidence
- estimated_value_usd: Rough replacement value estimate (null if uncertain)
- condition: One of [new, good, fair, poor] based on visible appearance
- bounding_box: [x1, y1, x2, y2] normalized coordinates (0-1) of object in image

Return a JSON array. Be thorough — include everything from large furniture to small items
on shelves. Prefer being specific ("IKEA KALLAX shelf unit, white, 4x4") over generic
("bookshelf").
```

### Single Image Detail Prompt

```
Look at this close-up image of a household item. Provide a detailed identification.

Return JSON:
- name: Specific name including brand and model if visible
- description: Detailed 3-5 sentence description
- category: [electronics, furniture, kitchenware, books, clothing, tools, decor,
  appliances, sports, toys, other]
- is_book: true/false
- book_details: If is_book, include {title, author, isbn (if visible), publisher,
  genre, estimated_page_count}
- visible_text: Any text, serial numbers, model numbers you can read
- barcode_present: true if a barcode or QR code is visible
- estimated_value_usd: Replacement value estimate
- condition: [new, good, fair, poor] with brief justification
- confidence: Float 0.0-1.0
```

---

## Mobile UX Flow

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Dashboard   │────▶│  Select Room  │────▶│  Capture Mode   │
│             │     │  or create    │     │                 │
│ [Start Scan]│     │  new room     │     │  ◉ Video (def.) │
└─────────────┘     └──────────────┘     │  ○ Image        │
                                         │                 │
                                         │  [Start Record] │
                                         └────────┬────────┘
                                                  │
                              ┌────────────────────┤
                              ▼                    ▼
                    ┌──────────────┐     ┌──────────────────┐
                    │  Recording   │     │  Image Capture    │
                    │  video...    │     │                  │
                    │              │     │  [Take Photo]    │
                    │  [Stop]      │     │  [Upload]        │
                    └──────┬───────┘     └────────┬─────────┘
                           │                      │
                           ▼                      ▼
                    ┌──────────────┐     ┌──────────────────┐
                    │  Processing  │     │  Analyzing...     │
                    │  ████░░ 60%  │     │  ████████░░ 80%  │
                    │              │     │                  │
                    │  Found 12    │     │  Identified:     │
                    │  items so far│     │  Sony WH-1000XM5 │
                    └──────┬───────┘     └────────┬─────────┘
                           │                      │
                           ▼                      │
                    ┌──────────────┐              │
                    │ Mode Switch  │              │
                    │ Prompt       │              │
                    │              │              │
                    │ "3 books     │              │
                    │  need closer │              │
                    │  photos"     │──────────────┘
                    │              │   (switches to image mode)
                    │ [Image Mode] │
                    │ [Skip]       │
                    └──────┬───────┘
                           │
                           ▼
                    ┌──────────────────┐
                    │  Review Grid     │
                    │                  │
                    │  ┌───┐ ┌───┐    │
                    │  │ ✓ │ │ ✓ │    │
                    │  │img│ │img│    │
                    │  │TV │ │Sofa│   │
                    │  └───┘ └───┘    │
                    │  ┌───┐ ┌───┐    │
                    │  │ ✎ │ │ ✕ │    │
                    │  │img│ │img│    │
                    │  │???│ │dup│    │
                    │  └───┘ └───┘    │
                    │                  │
                    │ [Save All]       │
                    └──────────────────┘
```

---

## Design System

- **Color palette**: Dark blue (#0a1628) background, cyan (#06b6d4) accents,
  slate grays for cards
- **Typography**: Inter for headings, system sans-serif stack for body
- **Cards**: Rounded corners (12px), subtle box-shadow, hover lift transition
- **Mobile-first**: Single column, touch-friendly tap targets (min 44px),
  bottom navigation
- **Status colors**: Green (keep), Orange (sell), Blue (donate), Red (trash)
- **Condition badges**: Colored pills — green/blue/yellow/red

---

## Key Design Decisions

1. **VLM over YOLO/object detection** — A vision language model can name, describe,
   read text, estimate value, and assess condition in one pass. Object detection
   models only draw boxes and classify into fixed categories.

2. **Video-first capture** — Walking through a room with video is 10x faster than
   photographing individual items. Keyframe extraction + batch analysis makes this
   efficient on the server side.

3. **Smart mode switching** — The system should know its limits. When confidence is
   low or detail is needed, prompting the user for a targeted photo produces better
   results than guessing.

4. **SQLite** — For a personal home inventory, SQLite is the right choice. Single file,
   no server, trivially backupable (`cp inventory.db backup.db`), and fast enough
   for tens of thousands of items.

5. **HTMX over SPA** — Server-rendered HTML with HTMX gives us dynamic updates,
   SSE streaming, and partial page swaps without a JavaScript framework. The only
   JS needed is the MediaStream API for camera/video access.

6. **Polymorphic inheritance for books** — Books are items with extra fields. SQLAlchemy
   single-table or joined-table inheritance keeps queries clean and avoids a separate
   book management flow.
