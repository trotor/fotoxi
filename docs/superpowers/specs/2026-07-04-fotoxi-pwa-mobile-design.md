# Fotoxi PWA + mobile access (Tailscale) — Design

Date: 2026-07-04
Status: Approved

## Goal

Install Fotoxi as an app on an iPhone (Safari), accessed over a private HTTPS
connection (Tailscale Serve) to the home machine that runs the backend, DB,
thumbnails and full-resolution originals. App-shell is cached (installable,
app-like); photos/data load live from the home server when it is reachable.

## Decisions (from brainstorming)

- Target device: **iPhone / Safari** (also emit correct meta so Android works,
  but iOS is the priority).
- Offline scope: **app-shell only** — the app installs and opens app-like, but
  data/thumbnails are fetched from the network. No offline thumbnail cache.
- Implementation: **`vite-plugin-pwa`** (Workbox) with `registerType: autoUpdate`.
- Connection: **Tailscale Serve** provides trusted HTTPS
  (`https://<machine>.<tailnet>.ts.net`), which is required for a service worker
  (secure-context). Private tailnet, no public exposure, no app auth needed.

## Scope

### Code (this repo)

1. **PWA via `vite-plugin-pwa`** (`frontend/vite.config.ts`)
   - Web manifest: name/short_name "Fotoxi", `display: standalone`,
     `theme_color`/`background_color` dark (`#0a0a0a`), `start_url: "/"`,
     `scope: "/"`, icons (192, 512, 512-maskable).
   - Service worker: precache the built app shell (JS/CSS/`index.html`).
     Runtime: `/api/*` and image endpoints → NetworkFirst (fresh data; brief
     offline still shows last response). No bulk thumbnail precache.
   - `registerType: autoUpdate` so new deploys apply on next load.
2. **iOS / standalone meta** (`frontend/index.html`)
   - `apple-mobile-web-app-capable`, `apple-mobile-web-app-status-bar-style`,
     `apple-touch-icon` (180), `theme-color`, `viewport-fit=cover`.
3. **Safe-area insets** (`frontend/src/index.css`) so the fixed header respects
   the notch / home indicator in standalone mode.
4. **Icons** — generate a simple Fotoxi grid mark (matching the header logo) at
   180/192/512 + maskable-512 PNG via a Pillow script committed under
   `frontend/scripts/`; outputs to `frontend/public/icons/`. Swappable later.
5. **Backend** — no code change required: `fotoxi.py serve` already supports
   `--host`/`--port`; Tailscale Serve proxies `localhost:8001`, so the backend
   can bind `127.0.0.1`. Frontend already uses relative `/api` paths, so it works
   behind the HTTPS proxy unchanged.
6. **Version bump** to 0.4.5 + CHANGELOG.

### Setup (documented, user runs once)

`docs/mobile-pwa-tailscale.md`:
- Install Tailscale on the Mac (home) and iPhone; join the same tailnet.
- `python fotoxi.py serve --host 127.0.0.1` then
  `tailscale serve --bg http://localhost:8001` → `https://<machine>.<tailnet>.ts.net`.
- iPhone Safari → open the HTTPS URL → Share → "Add to Home Screen" → installs.
- Cross-reference roadmap issues #25 (Tailscale), #21 (central server), #26
  (full-res proxy).

## Verification

- Build; confirm `dist/manifest.webmanifest`, service worker and icons are
  generated and referenced.
- Serve on `localhost` (a secure context) and verify in a browser: SW registers,
  manifest is valid, installability criteria met, app still works normally.
- Actual iPhone install is user-side; the doc gives exact steps.

## Out of scope (YAGNI)

- Offline thumbnail caching.
- App authentication (Tailscale provides the private boundary; app stays no-auth).
- Full mobile responsive overhaul (#43) — only the minimum PWA usability.
- A cloud read-only DB replica (route 2) — separate future work.
