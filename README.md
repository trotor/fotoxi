# Fotoxi

> **foto** (photo) + **ξ** (ksi, the Greek letter xi — the unknown, to be discovered)

Local photo management and metadata database. Indexes photos from OneDrive, Google Drive, iCloud Drive and local folders. Creates a searchable metadata database with EXIF data, perceptual hashes, and optional AI descriptions via Ollama. Detects and helps resolve duplicates.

[Suomeksi / Finnish](#suomeksi-)

## Features

- **Multi-source indexing** — OneDrive, Google Drive, iCloud Drive, local folders
- **EXIF extraction** — Date, camera, GPS, aperture, ISO, exposure, focal length
- **Perceptual hashing** — pHash/dHash for duplicate detection
- **Duplicate management** — Side-by-side comparison with smart suggestions (keeps largest)
- **AI descriptions** — Optional local Ollama vision model integration (LLaVA, Moondream, etc.)
- **Full-text search** — SQLite FTS5 across descriptions, tags, filenames
- **Cloud-optimized** — macOS Files On-Demand support, auto-download + eviction
- **Web UI** — React SPA with dark theme, infinite scroll, status badges
- **CLI** — Full command-line interface for all operations
- **Database migrations** — Alembic for schema evolution
- **Reject/restore workflow** — Mark images for deletion, review before removing

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
```

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

---

## Suomeksi 🇫🇮

# Fotoxi

> **foto** (valokuva) + **ξ** (ksi, kreikan kirjain — tuntematon, löydettävä)

Paikallinen valokuvien hallinta- ja metatietokantasovellus. Indeksoi valokuvat OneDrivestä, Google Drivestä, iCloud Drivestä ja paikallisista kansioista. Luo haettavan metatietokannan EXIF-tiedoilla, visuaalisilla sormenjäljillä ja valinnaisilla tekoälykuvauksilla Ollaman kautta. Tunnistaa ja auttaa hallitsemaan duplikaatteja.

### Ominaisuudet

- **Monikansio-indeksointi** — OneDrive, Google Drive, iCloud Drive, paikalliset kansiot
- **EXIF-metatiedot** — Päivämäärä, kamera, GPS, aukko, ISO, valotusaika, polttoväli
- **Duplikaattitunnistus** — Visuaalinen sormenjälki (pHash) + sarjakuvaustunnistus
- **Duplikaattien hallinta** — Rinnakkaisvertailu älykkäillä ehdotuksilla
- **Tekoälykuvaukset** — Valinnainen paikallinen Ollama-näkömalli (LLaVA ym.)
- **Kokotekstihaku** — SQLite FTS5 kuvauksista, tageista ja tiedostonimistä
- **Pilvioptiomointi** — macOS Files On-Demand, automaattinen lataus ja vapautus
- **Web-käyttöliittymä** — React SPA tummalla teemalla
- **Komentorivi** — Kaikki toiminnot CLI:n kautta
- **Tietokantamigraatiot** — Alembic skeemamuutoksiin

### Pikaopas

```bash
git clone https://github.com/trotor/fotoxi.git
cd fotoxi
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cd frontend && npm install && npm run build && cd ..
python fotoxi.py
# Avaa http://localhost:8000
```

### Komentorivi

```bash
python fotoxi.py                    # Käynnistä web-käyttöliittymä
python fotoxi.py add <kansio>       # Lisää lähdekansio
python fotoxi.py folders            # Listaa kansiot
python fotoxi.py index              # Aja koko indeksointi
python fotoxi.py status             # Tietokannan tila
python fotoxi.py duplicates         # Näytä duplikaattiryhmät
python fotoxi.py backup             # Luo varmuuskopio
```
