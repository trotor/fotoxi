# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Always use a Python virtual environment (venv). Activate before running any Python command:
```bash
python3 -m venv .venv               # Create (first time only)
source .venv/bin/activate            # Activate
```

## Commands

```bash
# Backend (venv must be active)
pip install -e ".[dev]"              # Install with dev deps
python fotoxi.py serve               # Start server at http://localhost:8001
python fotoxi.py serve -p 3000       # Custom port
python -m pytest -v tests/           # Run all tests
python -m pytest tests/test_api.py   # Run single test file
python -m pytest tests/test_api.py::test_name -v  # Run single test

# Frontend
cd frontend && npm install && npm run build  # Build frontend (served by backend)
cd frontend && npm run dev                   # Vite HMR dev server
cd frontend && npm run lint                  # ESLint

# Database migrations
alembic revision --autogenerate -m "description"  # Create migration
alembic upgrade head                              # Apply migrations
python fotoxi.py migrate                          # CLI migration runner

# CLI tools
python fotoxi.py add <folder>        # Add source folder
python fotoxi.py scan                # Scan for new/changed files
python fotoxi.py index               # Full pipeline: scan + metadata + AI + duplicates
python fotoxi.py ai --lang EN        # Run AI analysis
python fotoxi.py status              # Database summary
python fotoxi.py backup              # Timestamped DB backup
```

## Architecture

**Full-stack photo management app**: Python FastAPI backend + React TypeScript SPA, SQLite with FTS5 full-text search, optional Ollama AI integration.

### Backend (`backend/`)

- **Entry point**: `fotoxi.py` CLI dispatches to `backend/main.py:create_app()` async factory
- **API**: FastAPI REST at `/api` + WebSocket at `/api/ws` for live indexing progress. Routes in `backend/routes/`
- **Database**: Async SQLAlchemy 2.0 + aiosqlite. Models in `backend/db/models.py`, queries in `backend/db/queries.py`. Session factory in `backend/db/session.py` also creates the FTS5 virtual table
- **Indexer pipeline** (`backend/indexer/`): Orchestrator coordinates phases: scanning → EXIF extraction → thumbnail generation → AI analysis → duplicate grouping. Uses ThreadPoolExecutor for CPU-bound work
- **Duplicate detection** (`backend/grouping/duplicates.py`): Union-Find algorithm combining perceptual hash (pHash) similarity and burst detection (same camera, <5s apart)
- **AI analysis** (`backend/indexer/analyzer.py`): Calls Ollama vision models, uses 300px thumbnails, supports multilingual output (en/fi), stores results in language-specific DB columns
- **Cloud integration** (`backend/indexer/eviction.py`): macOS `brctl evict` to reclaim space after processing cloud files from `~/Library/CloudStorage/`
- **Config**: `backend/config.py` dataclass, persisted to `Setting` table in DB

### Frontend (`frontend/`)

- React 19 + TypeScript + Vite + Tailwind CSS 4
- State: TanStack Query for server data, Zustand for i18n only
- Pages: Search (infinite scroll grid + filters + keyboard shortcuts), Duplicates, Indexing (WebSocket live progress), Stats, Settings
- API client: `frontend/src/api.ts`
- i18n: `frontend/src/i18n/` with en/fi translations, Zustand store

### Data Flow

`python fotoxi.py serve` → creates FastAPI app → runs Alembic migrations → mounts API routes + WebSocket → serves built frontend SPA from `frontend/dist/` with index.html fallback.

Indexing runs in-process via the orchestrator, broadcasting progress over WebSocket. Thumbnails stored in `data/thumbs/`, database at `data/fotoxi.db`.

## Key Patterns

- All database access is async (`async with get_session() as session`)
- pytest uses `asyncio_mode = "auto"` — test functions can be plain `async def`
- Frontend build output goes to `frontend/dist/` and is served statically by the backend
- Image search supports FTS5 queries, date/camera/folder/GPS filters, and pagination (PAGE_SIZE=40)
- Supported formats: JPEG, PNG, HEIC, TIFF, RAW (CR2/NEF/ARW/DNG), MP4, MOV, AVI, MKV
