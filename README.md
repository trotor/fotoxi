# Fotoxi

> **foto** (photo) + **ξ** (ksi, the Greek letter xi — the unknown, to be discovered)

Local photo and video management tool. Indexes media from OneDrive, Google Drive, iCloud Drive and local folders. Creates a searchable metadata database with EXIF data, perceptual hashes, and optional AI descriptions via Ollama. Detects and helps resolve duplicates.

[Suomeksi / Finnish](README.fi.md)

## What is Fotoxi good for?

**The problem:** You have thousands of photos and videos scattered across cloud services, phone backups, and local folders. Many are duplicates, some are blurry, and you can't find anything.

**Typical workflow:**

1. **Point Fotoxi at your photo folders** — OneDrive, Google Drive, local Pictures, phone backup folders. One click to add each source.
2. **Let it index** — Fotoxi scans all folders recursively, extracts EXIF metadata (date, camera, GPS, settings), generates thumbnails, and computes visual fingerprints. Cloud files are downloaded temporarily and released back to cloud-only afterwards.
3. **Browse and search** — Filter by date, camera, folder, or media type. Sort by date, name, size, or visual similarity. Infinite scroll through your entire collection.
4. **Clean up duplicates** — Fotoxi finds visually similar images and burst shots. One-click "keep largest" resolves most groups instantly. You can also filter by folder to keep originals from a preferred location.
5. **Reject unwanted files** — Mark images for deletion directly from the search grid. Review rejected items before permanent removal.
6. **Optionally: AI descriptions** — Connect a local Ollama vision model (LLaVA, Moondream) to auto-generate descriptions and tags for full-text search.

**Best for:**
- Consolidating photo libraries from multiple cloud services and devices
- Finding and removing duplicate photos from phone backup folders
- Cleaning up years of accumulated screenshots, WhatsApp images, and burst shots
- Building a searchable index of a large photo collection
- Managing media without uploading anything to third-party services

**Not designed for:**
- Photo editing or RAW processing
- Real-time photo organization (batch/offline workflow)
- Multi-user or server deployment (single-user local tool)

## Features

- **Multi-source indexing** — OneDrive, Google Drive, iCloud Drive, local folders
- **Photos and videos** — JPEG, PNG, HEIC, RAW, MP4, MOV, AVI, MKV and more
- **EXIF extraction** — Date, camera, GPS, aperture, ISO, exposure, focal length
- **Perceptual hashing** — pHash/dHash for duplicate photo detection
- **Duplicate management** — Grid comparison with one-click "keep recommended"
- **AI descriptions** — Optional local Ollama vision model (LLaVA, Moondream, etc.)
- **Full-text search** — SQLite FTS5 across descriptions, tags, filenames
- **Folder browsing** — Navigate and filter by folder tree with image counts
- **Media type filter** — Switch between all/photos/videos
- **Cloud-optimized** — macOS Files On-Demand, auto-download + eviction after processing
- **Web UI** — React SPA, dark theme, infinite scroll, hover zoom, status badges
- **CLI** — Full command-line interface for all operations
- **Reject/restore workflow** — Mark images for deletion from search, review before removing
- **Database migrations** — Alembic for safe schema evolution
- **EXIF orientation** — Thumbnails automatically rotated correctly

## Quick Start

```bash
# Clone and install
git clone https://github.com/trotor/fotoxi.git
cd fotoxi
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Build frontend
cd frontend && npm install && npm run build && cd ..

# Start
python fotoxi.py
# Open http://localhost:8000
```

## CLI

```bash
python fotoxi.py                    # Start web UI (default)
python fotoxi.py serve -p 3000      # Custom port
python fotoxi.py add <folder>       # Add source folder
python fotoxi.py folders            # List source folders
python fotoxi.py remove <folder>    # Remove source folder
python fotoxi.py scan               # Scan for new/changed files
python fotoxi.py index              # Full indexing (scan + metadata + AI + duplicates)
python fotoxi.py status             # Database summary
python fotoxi.py duplicates         # Show duplicate groups
python fotoxi.py backup             # Timestamped DB backup
python fotoxi.py migrate            # Run database migrations
python fotoxi.py rebuild-thumbs     # Rebuild thumbnails (fixes EXIF orientation)
```

## Web UI Pages

- **Search** — Infinite scroll image grid with filters (date, camera, folder, media type, status), sort options (date, name, size, similarity), folder tree navigation with breadcrumbs, image preview with keyboard shortcuts (Enter=keep, Backspace=reject, arrows=navigate)
- **Duplicates** — Groups of similar images with one-click resolve. Smart recommendations based on resolution, file size, and source path quality. pHash distance shown.
- **Indexing** — Live progress with parallel processing stats, folder scan status, activity log. "Process missing" button for metadata-only runs without re-scanning.
- **Stats** — Interactive dashboard: year/month drill-down timeline, camera breakdown, GPS stats, status summary. All clickable to filter search.
- **Settings** — Ollama model, AI language, quality scoring toggle, duplicate sensitivity, exclude patterns.

## How It Works

### Indexing Pipeline

1. **Scan** — Recursively finds images (JPEG, PNG, HEIC, TIFF, RAW, CR2, NEF, ARW, DNG)
2. **Metadata** — EXIF extraction, perceptual hash computation, thumbnail generation (300px)
3. **AI Analysis** — Optional: Ollama vision model produces descriptions, tags, quality scores
4. **Duplicate Grouping** — Groups by pHash similarity (Hamming distance < 10) and burst detection (same camera, < 5s apart). Union-Find merges overlapping matches.

### Cloud Integration (macOS)

Leverages macOS File Provider framework (Files On-Demand):
- Cloud files in `~/Library/CloudStorage/` are read as normal paths
- macOS downloads files transparently on access
- After processing, `brctl evict` releases the local copy back to cloud-only
- Works with OneDrive, Google Drive, iCloud Drive — no API keys needed

### Apple Photos Library

- **originals/** — real photos, included in indexing and duplicate detection
- **derivatives/**, **masters/**, **resources/** — Apple-generated copies, automatically excluded
- Photos Library internal duplicates (originals vs originals) are never shown in duplicate view
- Only cross-source duplicates (e.g., Photos Library vs OneDrive) are flagged

### Data Storage

- **SQLite** in `data/fotoxi.db` with FTS5 full-text search
- **Thumbnails** in `data/thumbs/` (300px JPEG)
- **Settings** persisted in SQLite (source folders, model config, preferences)
- **Alembic** migrations for schema changes

## Configuration

| Setting | Default | Description |
|---------|---------|-------------|
| `ollama_model` | `llava:7b` | Vision model for AI descriptions |
| `ai_language` | `english` | Language for AI-generated descriptions |
| `ai_quality_enabled` | `true` | Enable quality scoring (0-1) |
| `phash_threshold` | `10` | Hamming distance for duplicates (lower = stricter) |
| `exclude_patterns` | derivatives, masters, ... | Folder names to skip |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Database | SQLite + FTS5, SQLAlchemy, aiosqlite, Alembic |
| Image analysis | Ollama, exifread, imagehash, Pillow, pillow-heif |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS |
| State | TanStack Query (React Query) |

## Development

```bash
pip install -e ".[dev]"          # Install with dev deps
python -m pytest -v              # Run tests
cd frontend && npm run dev       # Frontend dev server with HMR

# Database migrations
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Requirements

- Python 3.11+
- Node.js 18+
- macOS (for cloud integration; core features work on Linux without `brctl`)
- Ollama (optional, for AI descriptions)

## License

MIT

