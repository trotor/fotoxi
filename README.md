# Fotoxi

Local photo management and metadata database. Indexes photos from OneDrive, Google Drive, iCloud Drive and local folders. Creates searchable metadata with EXIF data, perceptual hashes, and optional AI descriptions via Ollama. Detects and helps resolve duplicates.

## Features

- **Multi-source indexing** - OneDrive, Google Drive, iCloud Drive, local folders
- **EXIF extraction** - Date, camera, GPS, aperture, ISO, exposure, focal length
- **Perceptual hashing** - pHash/dHash for duplicate detection
- **Duplicate management** - Side-by-side comparison with smart suggestions
- **AI descriptions** - Optional Ollama vision model integration (LLaVA, etc.)
- **Full-text search** - SQLite FTS5 across descriptions, tags, filenames
- **Cloud-optimized** - macOS Files On-Demand support with automatic eviction
- **Web UI** - React SPA with dark theme
- **CLI** - Full command-line interface for all operations
- **Database migrations** - Alembic for schema evolution

## Quick Start

```bash
# Clone and install
git clone https://github.com/trotor/fotoxi.git
cd fotoxi
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# Install frontend dependencies and build
cd frontend
npm install
npm run build
cd ..

# Start the server
python fotoxi.py
# Open http://localhost:8000
```

## CLI Usage

```bash
python fotoxi.py serve              # Start web UI (default, port 8000)
python fotoxi.py serve -p 3000      # Custom port
python fotoxi.py add ~/Pictures     # Add source folder
python fotoxi.py add ~/Library/CloudStorage/OneDrive-Personal
python fotoxi.py folders            # List source folders
python fotoxi.py remove <folder>    # Remove source folder
python fotoxi.py scan               # Scan for new/changed files
python fotoxi.py index              # Full indexing pipeline
python fotoxi.py status             # Database status summary
python fotoxi.py duplicates         # Show duplicate groups
python fotoxi.py backup             # Create timestamped DB backup
python fotoxi.py migrate            # Run database migrations
```

## How It Works

### Indexing Pipeline

1. **Scan** - Recursively finds image files (JPEG, PNG, HEIC, TIFF, RAW, etc.)
2. **Metadata** - Extracts EXIF data, computes perceptual hashes, generates thumbnails
3. **AI Analysis** - Optional: sends images to local Ollama vision model for descriptions and tags
4. **Duplicate Grouping** - Groups similar images by pHash similarity and burst detection (same camera, close timestamps)

### Cloud Integration (macOS)

Uses macOS Files On-Demand (File Provider framework):
- Cloud files appear as normal paths in `~/Library/CloudStorage/`
- Reading a file triggers automatic download
- After processing, `brctl evict` releases the local copy
- No API keys or OAuth needed

### Duplicate Detection

- **Perceptual hash** - Hamming distance < 10 on 64-bit pHash
- **Burst detection** - Same camera model within 5 seconds
- **Union-Find** grouping merges overlapping matches
- Smart suggestions: keeps largest resolution image
- Apple Photos Library internal duplicates are automatically excluded

### Data Storage

- **SQLite database** in `data/fotoxi.db` (with FTS5 for full-text search)
- **Thumbnails** in `data/thumbs/` (300px JPEG, ~20-50KB each)
- **Settings** persisted in database (source folders, model config, etc.)
- **Alembic migrations** for schema changes

## Configuration

Settings are configured via the web UI (Settings page) or CLI. Key settings:

| Setting | Default | Description |
|---------|---------|-------------|
| `ollama_model` | `llava:7b` | Ollama vision model for AI descriptions |
| `ai_language` | `english` | Language for AI descriptions |
| `ai_quality_enabled` | `true` | Enable AI quality scoring |
| `phash_threshold` | `10` | Hamming distance for duplicate detection (lower = stricter) |
| `exclude_patterns` | derivatives, masters, resources, ... | Folder names to skip during scan |

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+, FastAPI, uvicorn |
| Database | SQLite + FTS5, SQLAlchemy, aiosqlite, Alembic |
| Image analysis | Ollama (configurable model), exifread, imagehash, Pillow |
| Frontend | React 18, Vite, TypeScript, Tailwind CSS |
| State management | TanStack Query, zustand |

## Development

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
python -m pytest -v

# Frontend dev server (with hot reload)
cd frontend
npm run dev

# Create a new migration after model changes
alembic revision --autogenerate -m "description"
alembic upgrade head
```

## Requirements

- Python 3.11+
- Node.js 18+ (for frontend build)
- macOS (for cloud file integration via `brctl evict`)
- Ollama (optional, for AI descriptions)

## License

MIT
