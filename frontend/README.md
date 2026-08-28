# Frontend (P5 — guided walkthrough UI)

React + TypeScript + Vite + Apache ECharts (REQUIREMENTS.md D21/D26). Normally
built as part of the `backend` service's multi-stage Docker image (see
`../backend/Dockerfile`) and served by FastAPI's `StaticFiles` — this
directory is not run standalone in production.

## NFR-10.1 justification: TypeScript

TypeScript (plus `@types/react`, `@types/react-dom`) is not on
`REQUIREMENTS.md`'s literal NFR-10.1 dependency allowlist
(`react`, `react-dom`, `vite`, `echarts`). It's added anyway because the app
has several interlocking JSON contracts (backend snapshot shape, per-step
data, WebSocket payloads — see `src/types.ts`) that are much easier to keep
in sync with the backend when the compiler checks them, and the added
dev-only build-time dependency carries no runtime/security surface beyond
what `vite build` already needs. `.npmrc`'s `ignore-scripts=true` and the
committed `package-lock.json` still apply to it like every other dependency.

## NFR-10.1 justification: Leaflet

Leaflet (plus dev-only `@types/leaflet`) is not on the original allowlist either, but unlike
TypeScript it *does* ship to the browser (the planner role's map view, `src/planner/MapView.tsx`).
Added because the role-based redirect requires a map, and Leaflet is the minimal-footprint way to get
one: MIT-licensed, no telemetry or network calls beyond fetching map tiles from the configured tile
server, no API key or billing account required (unlike Mapbox GL JS or the Google Maps SDK). Exact
version pinned (`1.9.4`, released 2023 — well past NFR-10.3's 14-day cooldown), `.npmrc`'s
`ignore-scripts=true` and the committed `package-lock.json` apply to it like every other dependency.

## Docs tab

`src/admin/DocsTab.tsx` embeds the local `docs/` site (see the root `docs/index.html`) via an
`<iframe>` pointed at `backend/app/routers/docs.py`'s admin-gated static file route — no markdown
rendering happens in the frontend at all; the same static HTML a developer opens directly from the
repo is what's shown in-app (D36/D37). This replaced an earlier version that fetched `.md` files and
rendered them client-side with `marked` — that dependency has since been removed
(`npm uninstall marked`) since nothing in this app parses markdown anymore.

## Dev workflow

```
npm ci
npm run dev
```

`vite.config.ts` proxies `/api` and `/ws` to `http://localhost:8000` — start
the `backend` container first (`docker compose up -d backend`) so there's
something to proxy to. `npm run build` type-checks (`tsc -b`) then produces
`dist/`, which is what the backend's Docker build copies into its own image.
