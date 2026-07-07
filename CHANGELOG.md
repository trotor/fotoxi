# Changelog

All notable changes to Fotoxi are documented here.

## [0.4.12] - 2026-07-07

### Fixed
- **AI language in the prompt is normalised** — the analyzer prompt used the raw setting value (e.g. "description in fi"). It now maps codes/words to a clear language name ("Finnish"/"English") via `display_language()`, so the model gets an unambiguous instruction regardless of whether the setting is stored as `fi`/`finnish`/`en`/`english`.
- **Quality filter now has a UI control** — the min-quality filter was wired end-to-end (state → API → query) but `FilterBar` never rendered a control for it. Added a "Quality ≥ …" dropdown, so it's usable instead of dead.

### Removed
- **Dead code** — the broken, unused `resolveDuplicate()` API helper (wrong payload shape), the orphaned `ImageCompare.tsx` component, and an unused `get_duplicate_groups` import in the routes module.

## [0.4.11] - 2026-07-07

### Added
- **Undo + toast notifications; in-app dialogs** (#36) — rejecting an image now shows a toast with an **Undo** action that restores its previous status. Native `alert()`/`confirm()` are replaced by a themed in-app toast/confirm dialog (with danger styling for destructive actions), used for "reject all missing" and "hide folder". New `UIProvider`/`useToast` (`frontend/src/components/Toast.tsx`).

## [0.4.10] - 2026-07-07

### Fixed
- **i18n leaks** (#32) — user-facing strings that were hardcoded (and so ignored the language toggle) now go through the translation system: Stats status labels (were always English), the Search status badges (kept/rejected/pending/error), error messages ("Error"/"Virhe haettaessa kuvia."), the Search "loading more"/"back to top" labels, the Duplicates folder/keeping/rejecting/pHash-distance labels, the Indexing "rejected"/"loading" labels, and the FolderBrowser dialog. Combined with the already-fixed `gps_inherit` phase (0.4.9), switching FI/EN now translates these consistently. (`ImageCompare.tsx` is dead/unused code and was left as-is.)

## [0.4.9] - 2026-07-07

### Changed
- **Indexing progress is clearer** (#39) — the main phase bar is now labelled with the current phase (Scan / Metadata / …) and is hidden during AI analysis, so the clearly-labelled AI progress bar no longer sits next to a second, stale-looking bar. The `gps_inherit` phase is now translated instead of showing a raw string.
- **Settings layout balanced** (#40) — the settings cards are centered and laid out in a responsive two-column grid instead of a single narrow left column.
- **Map cluster legend** (#37) — a legend explains the cluster colour buckets (1–4 / 5–19 / 20–99 / 100+) and that circle size reflects count.
- **Dark map tiles** (#38) — the map now uses a dark basemap (CARTO Dark Matter) that matches the app theme instead of bright OSM tiles.

## [0.4.8] - 2026-07-07

### Added
- **Errors & missing visibility + retry** (#30) — the Indexing page now shows an "Errors & missing" panel: errored files grouped by cause (e.g. "AI analysis returned no result", "Timeout — file too large") with per-cause and "Retry all" buttons, plus the missing-file count with an explanation of what `missing` means. Retry resets the errored images to `pending` (clearing the error) and kicks off reprocessing. New endpoints `GET /api/errors/summary` and `POST /api/errors/retry` (`backend/db/queries.py: errors_summary`, `retry_errored`).

## [0.4.7] - 2026-07-07

### Fixed
- **Full-text search now covers all AI languages** (#31) — the FTS5 index and its sync triggers were expanded from the 3 generic columns to also index the per-language columns (`ai_description_en/fi`, `ai_tags_en/fi`), so search matches AI descriptions/tags regardless of the language the analysis ran in. Existing databases self-heal on startup: `init_db` detects the old narrower FTS schema, recreates it with the full column set, and rebuilds the index from existing data (no manual migration needed).

### Notes
- To get Finnish search hits on your library, set the AI language to Finnish in Settings and re-run AI (or keep English and search in English) — the index now handles whichever language(s) are present.

## [0.4.6] - 2026-07-05

### Fixed
- **Version single source of truth** (#44) — the app version now comes from one place, `pyproject.toml`, read at runtime (`backend/version.py`) and exposed at `GET /api/version`. The frontend fetches its running version from the backend instead of a hardcoded constant, and the OpenAPI `version` is derived too. This removes the drift where the nav could show a stale version. (`version.json` remains the published-latest marker for the update check.)

## [0.4.5] - 2026-07-05

### Added
- **Installable PWA (mobile)** — Fotoxi can be installed to a phone home screen and runs standalone (app-like). Uses `vite-plugin-pwa` (Workbox): web manifest, service worker precaching the app shell, generated icons (`frontend/scripts/generate_icons.py`), and iOS meta tags (`apple-touch-icon`, standalone status bar, `theme-color`). App-shell is cached; photos/data load live from the home server (no offline photo cache by design). Safe-area insets respected in standalone mode.
- **Setup guide** `docs/mobile-pwa-tailscale.md` — install on iPhone over a private HTTPS connection via Tailscale Serve (required for the service worker). Design spec at `docs/superpowers/specs/2026-07-04-fotoxi-pwa-mobile-design.md`.

## [0.4.4] - 2026-07-04

### Changed
- **Duplicates: "Select recommended" is now a prominent action** — promoted from a tucked-away link next to the click-mode toggle to a highlighted button at the front of the primary action row. It preselects the recommended keeper for review (green ✓) without auto-confirming, so you can adjust before hitting Confirm.

## [0.4.3] - 2026-07-04

### Added
- **Bulk "Clean up copies"** (#27) — one action resolves all exact/visual duplicate copy groups at once (keeps the best per group via the same scoring the UI recommends, rejects the rest). A dry-run preview first shows how many images and groups are affected and **how much space is reclaimed** before anything is applied. New endpoint `POST /api/duplicates/bulk-resolve` (`match_types`, `exclude_burst`, `dry_run`) backed by `backend/grouping/scoring.py` and `bulk_resolve_duplicates()`.
- **Duplicate selection modes** — a "Click selects: Keeper / Rejects" toggle on the Duplicates page (persisted). In keeper mode a click marks the single image to keep (green ✓) and rejects the rest; a proper **"Select recommended"** button preselects the recommended keeper for review instead of auto-confirming.

### Changed
- **Bursts are no longer treated as duplicates to prune** (#28) — for burst groups the default action is now **"Keep all"** (never auto-rejects frames); reducing to the single best is an explicit secondary action. Bursts are excluded from bulk copy cleanup.

### Fixed
- **Version display drift** — `pyproject.toml`, `frontend` `CURRENT_VERSION` and `version.json` were out of sync (0.4.2 vs 0.4.1); realigned to 0.4.3. The systemic single-source-of-truth fix is tracked in #44.

## [0.4.2] - 2026-06-01

### Fixed
- **Cloud eviction log spam** — `brctl evict` only manages iCloud Drive (Apple CloudDocs); it was being run against every third-party cloud file (OneDrive/Google Drive/Dropbox) and failing every time, emitting one warning per file (20k+ warnings per index run). Eviction now runs `brctl` only for iCloud Drive paths and skips other providers with a single summary log line.
- **Misleading eviction count** — `_evict_cloud_files` counted every attempt as evicted; it now counts only files actually evicted via brctl.

## [0.4.1] - 2026-03-24

### Security
- **Path traversal fix** in SPA route — resolved path is now checked to stay within frontend dist
- **FTS5 query injection fix** — user search input is quoted to prevent FTS5 operator abuse
- **pip upgraded** to 26.0.1 (fixes CVE-2025-8869, CVE-2026-1703)
- **flatted** npm dependency upgraded (fixes prototype pollution GHSA-rf6f-7fwh-wjgh)

### Updated
- fastapi 0.135.1 → 0.135.2
- uvicorn 0.41.0 → 0.42.0
- anyio 4.12.1 → 4.13.0

### Fixed
- SQLite in-memory pool_size error in tests
- Updated stale test assertions (analyzer, API duplicates, search filters)
- 75/75 tests passing

## [0.4.0] - 2026-03-22

### Added
- **Custom tag system** — yellow ★ button to label and set aside special photos (e.g. sentimental)
- **Three-state ★ toggle** in search: off → "+ personal" (show tagged alongside normal) → "only personal" (show only tagged) → off
  - Tagged photos are hidden from default view (status → rejected) but stored separately from regular rejects
  - New ★ filter button in search bar shows only tagged photos
  - Tag label is configurable in Settings (default: "sentimental")
  - Yellow badge on tagged photos distinguishes them from regular rejected ones
  - Works in both grid view and preview modal
- `custom_tag` column with Alembic migration
- `PATCH /api/images/{id}/tag` endpoint
- `custom_tag` search filter parameter

## [0.3.4] - 2026-03-20

### Added
- "Show in Finder" button (📂) in preview modal — opens Finder with the file selected for drag & drop

## [0.3.3] - 2026-03-19

### Fixed
- Keep/reject no longer changes `updated_at` — sort by "Updated" now reflects only metadata/AI changes
- Added `status_changed_at` column for tracking when keep/reject happened
- Removed `onupdate=func.now()` from `updated_at` to prevent status changes from polluting sort order

## [0.3.2] - 2026-03-19

### Added
- "Updated" sort option in search — sort by last indexed/modified time (`updated_at`)

## [0.3.1] - 2026-03-19

### Added
- Timestamp on indexing log entries (`[HH:MM:SS]` prefix)
- Clickable camera name in preview modal filters by camera model

### Fixed
- AI progress bar now shows correct current file (was stuck on first file)
- Preview modal "Clear kept" button now updates UI immediately

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
