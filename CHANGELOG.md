# Changelog

All notable changes to Fotoxi are documented here.

## [0.3.0] - 2026-03-18

### Added
- **GitHub Pages site** with bilingual (EN/FI) documentation and flag-based language switcher
- **Help button** in navbar with links to docs, GitHub, keyboard shortcuts reference
- **Version check** against GitHub — notifies in Help popup when a newer version is available
- **AI concurrency setting** in Settings UI (slider 1-4) for parallel image analysis
- **Metadata refresh** — single image refresh button in preview modal + bulk video refresh API
- **Video date extraction** from MP4/MOV container atoms (mvhd creation_time) and filename parsing
- **Fotoxi logo** on GitHub Pages site and as favicon

### Fixed
- **FTS5 full-text search was empty** — added INSERT/UPDATE/DELETE triggers and rebuild on startup
- **Video timestamps** were using file modification time instead of actual recording date
- **Language toggle** on docs site — Finnish content was bleeding through due to CSS specificity

### Changed
- Infinite scroll preloads earlier (800px rootMargin) for smoother browsing
- Search auto-refreshes every 10s when AI filter is active
- Default AI concurrency remains 1; configurable up to 4

## [0.2.0] - 2026-03-15

### Added
- **Full i18n support** — English and Finnish with toggle in navbar
- **AI image analysis** — Ollama vision model integration (descriptions, tags, colors, scene type, quality score)
- **Multilingual AI descriptions** — separate EN/FI columns with Alembic migration
- **GPS proximity search** — find photos taken near a location with adjustable radius
- **Time proximity search** — find photos taken around the same time (±1min to ±7days)
- **Keyboard shortcuts** — Enter (keep), Backspace (reject), arrows (navigate), Esc (close)
- **Stats page** — timeline, camera breakdown, status distribution, clickable drill-down
- **Video support** — playback in preview, thumbnail extraction, separate video/photo counts
- **Folder browser** — expandable folder tree filter, breadcrumb navigation, exclude folders
- **Live indexing log** — real-time progress with AI results, speed metrics, remaining time
- **Duplicate UI improvements** — pHash distance display, smart recommendations, paginated API

### Fixed
- Cloud file eviction after metadata extraction
- EXIF orientation in thumbnails
- SQLite connection pool timeout under load
- Stale running flag preventing indexer restart
- Pending images stuck in wrong state

### Changed
- Duplicate API paginated (10000x faster for large collections)
- Parallel AI + metadata processing with semaphore concurrency
- Producer-consumer pipeline with 15 workers for metadata

## [0.1.0] - 2026-03-08

### Added
- Initial release
- **FastAPI backend** with async SQLAlchemy 2.0 + SQLite
- **React SPA frontend** with Tailwind CSS
- **Image scanning** — recursive folder scanning with EXIF extraction
- **Thumbnail generation** — 300px JPEG thumbnails
- **Perceptual hashing** — pHash + dHash for similarity detection
- **Duplicate detection** — union-find algorithm with pHash + burst detection
- **Full-text search** — SQLite FTS5 on file names
- **Cloud integration** — macOS iCloud/OneDrive file eviction after processing
- **Settings persistence** — stored in SQLite settings table
- **CLI tools** — scan, index, add folders, backup, status
- **WebSocket** — live indexing progress updates
