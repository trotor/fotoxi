# Fotoxi Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan. Steps use checkbox syntax for tracking.

**Goal:** Build a local photo management app that indexes photos with AI descriptions, EXIF data, and duplicate detection.

**Architecture:** Single-process Python FastAPI backend + React SPA frontend. SQLite + FTS5 database. Ollama for vision AI. Background thread indexing.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy, aiosqlite, imagehash, exifread, Pillow, httpx, React 18, Vite, TypeScript, Tailwind CSS, React Query, zustand

**Spec:** docs/superpowers/specs/2026-03-14-fotoxi-design.md

---

## Chunk 1: Project Setup and Database

### Task 1: Python project scaffolding

**Files:**
- Create: backend/__init__.py
- Create: backend/config.py
- Create: pyproject.toml
- Create: fotoxi.py

- [ ] Step 1: Create pyproject.toml with all dependencies (fastapi, uvicorn, sqlalchemy, aiosqlite, exifread, imagehash, Pillow, httpx, python-multipart; dev: pytest, pytest-asyncio, pytest-httpx, piexif)
- [ ] Step 2: Create backend/config.py with Config dataclass (db_path, thumbs_dir, source_dirs, ollama settings, thresholds, server settings)
- [ ] Step 3: Create backend/__init__.py (empty)
- [ ] Step 4: Create fotoxi.py that starts uvicorn with the FastAPI app
- [ ] Step 5: Create venv and install: python -m venv .venv and pip install -e ".[dev]"
- [ ] Step 6: Commit

### Task 2: Database models

**Files:**
- Create: backend/db/__init__.py
- Create: backend/db/models.py
- Create: tests/__init__.py
- Create: tests/test_models.py

- [ ] Step 1: Write tests for Image CRUD, DuplicateGroup creation, Setting storage
- [ ] Step 2: Run tests - expect FAIL
- [ ] Step 3: Implement SQLAlchemy models: Image (all fields from spec), DuplicateGroup, DuplicateGroupMember, Setting. Include indexes on phash, dhash, exif_date, status.
- [ ] Step 4: Run tests - expect PASS
- [ ] Step 5: Commit

### Task 3: Database session and FTS5

**Files:**
- Create: backend/db/session.py
- Create: tests/test_fts.py

- [ ] Step 1: Write test for FTS5 search (insert image, sync to FTS, search by keyword)
- [ ] Step 2: Implement session.py with create_engine_and_init() that creates tables and FTS5 virtual table
- [ ] Step 3: Run tests - expect PASS
- [ ] Step 4: Commit

---

## Chunk 2: Indexer Pipeline

### Task 4: File scanner

**Files:**
- Create: backend/indexer/__init__.py
- Create: backend/indexer/scanner.py
- Create: tests/test_scanner.py

- [ ] Step 1: Write test (scan temp dir with jpg/png/heic/txt files, verify only images found)
- [ ] Step 2: Implement scan_directory() that rglobs for IMAGE_EXTENSIONS
- [ ] Step 3: Run tests, commit

### Task 5: EXIF reader

**Files:**
- Create: backend/indexer/exif.py
- Create: tests/test_exif.py

- [ ] Step 1: Write test using PIL to create test JPEG with EXIF, verify extraction
- [ ] Step 2: Implement extract_exif() using Pillow for dimensions and exifread for metadata (date, camera, GPS, lens info)
- [ ] Step 3: Run tests, commit

### Task 6: Perceptual hasher

**Files:**
- Create: backend/indexer/hasher.py
- Create: tests/test_hasher.py

- [ ] Step 1: Write tests for hash computation, similar images low distance, hamming_distance function
- [ ] Step 2: Implement compute_hashes() using imagehash (phash + dhash), hamming_distance() via XOR bit count
- [ ] Step 3: Run tests, commit

### Task 7: Thumbnail generator

**Files:**
- Create: backend/indexer/thumbnailer.py
- Create: tests/test_thumbnailer.py

- [ ] Step 1: Write test (create 4000x3000 image, generate thumb, verify max 300px)
- [ ] Step 2: Implement generate_thumbnail() using Pillow thumbnail (300px longest side, JPEG q85)
- [ ] Step 3: Run tests, commit

### Task 8: Ollama analyzer

**Files:**
- Create: backend/indexer/analyzer.py
- Create: tests/test_analyzer.py

- [ ] Step 1: Write tests with mocked httpx (success returns JSON with description/tags/quality, failure returns None)
- [ ] Step 2: Implement analyze_image() - base64 encode image, POST to Ollama /api/chat, parse JSON response, retry 3x on failure
- [ ] Step 3: Run tests, commit

### Task 9: Cloud eviction

**Files:**
- Create: backend/indexer/eviction.py
- Create: tests/test_eviction.py

- [ ] Step 1: Write tests for is_cloud_path() and evict_file() with mocked subprocess
- [ ] Step 2: Implement using asyncio.create_subprocess_exec for brctl evict, no-op for local files
- [ ] Step 3: Run tests, commit

### Task 10: Duplicate grouping

**Files:**
- Create: backend/grouping/__init__.py
- Create: backend/grouping/duplicates.py
- Create: tests/test_duplicates.py

- [ ] Step 1: Write tests for phash duplicates, burst detection, combined groups, no duplicates
- [ ] Step 2: Implement find_duplicate_groups() with Union-Find, phash comparison (Hamming < threshold), burst detection (time + camera)
- [ ] Step 3: Run tests, commit

### Task 11: Indexer orchestrator

**Files:**
- Create: backend/indexer/orchestrator.py
- Create: tests/test_orchestrator.py

- [ ] Step 1: Write tests for scan phase (creates pending images) and metadata phase (populates hashes/EXIF)
- [ ] Step 2: Implement IndexerOrchestrator with scan(), process_metadata() (ThreadPoolExecutor), process_ai() (async + semaphore), run_full(), request_stop(), and progress callback
- [ ] Step 3: Run tests, commit

---

## Chunk 3: API and WebSocket

### Task 12: Database queries module

**Files:**
- Create: backend/db/queries.py
- Create: tests/test_queries.py

- [ ] Step 1: Write tests for text search, date filter, camera filter, pagination
- [ ] Step 2: Implement search_images() with FTS5 + filters, get_duplicate_groups(), resolve_duplicate_group()
- [ ] Step 3: Run tests, commit

### Task 13: FastAPI routes and WebSocket

**Files:**
- Create: backend/main.py
- Create: backend/api/__init__.py
- Create: backend/api/routes.py
- Create: backend/api/websocket.py
- Create: tests/test_api.py

- [ ] Step 1: Write tests for GET /api/images (empty), GET /api/indexer/status, GET /api/settings, GET /api/duplicates
- [ ] Step 2: Implement main.py with create_app() factory (init DB, create orchestrator, mount routes, serve frontend dist if exists)
- [ ] Step 3: Implement routes.py with all endpoints from spec
- [ ] Step 4: Implement websocket.py for progress streaming
- [ ] Step 5: Update fotoxi.py to use async create_app
- [ ] Step 6: Run tests, commit

---

## Chunk 4: React Frontend

### Task 14: Frontend scaffolding

- [ ] Step 1: npm create vite frontend (react-ts template)
- [ ] Step 2: Install deps: tailwindcss, @tailwindcss/vite, @tanstack/react-query, zustand, react-router-dom
- [ ] Step 3: Configure Tailwind Vite plugin and proxy to backend
- [ ] Step 4: Set up App.tsx with routing (Search, Duplicates, Indexing, Settings) and dark nav bar
- [ ] Step 5: Create api.ts with all TypeScript interfaces and fetch functions
- [ ] Step 6: Commit

### Task 15: Search page

- [ ] Step 1: Implement FilterBar component (date, camera, quality filters)
- [ ] Step 2: Implement Search page (text search, image grid with thumbnails, hover overlay with AI description, detail modal, pagination)
- [ ] Step 3: Commit

### Task 16: Duplicates page

- [ ] Step 1: Implement ImageCompare component (side-by-side with EXIF, AI recommendation, keep/reject buttons)
- [ ] Step 2: Implement Duplicates page (group navigation, thumbnail strip, resolve and advance)
- [ ] Step 3: Commit

### Task 17: Indexing page

- [ ] Step 1: Implement ProgressBar component
- [ ] Step 2: Implement Indexing page (status display, progress bar, stats grid, WebSocket live updates, source folder management)
- [ ] Step 3: Commit

### Task 18: Settings page

- [ ] Step 1: Implement Settings page (Ollama model input, language select, quality toggle, phash threshold slider, save button)
- [ ] Step 2: Commit

### Task 19: Build and integrate

- [ ] Step 1: Remove Vite boilerplate (App.css, assets, default content)
- [ ] Step 2: Build frontend: npm run build
- [ ] Step 3: Verify fotoxi.py serves built frontend
- [ ] Step 4: Final commit
