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

## NFR-10.1 justification: marked

`marked` is not on the original allowlist either, but is added for the admin-only "Docs" tab
(`src/admin/DocsTab.tsx`), which renders the project's own bundled `.md` files
(`backend/app/routers/docs.py`) so an administrator can read how the system was conceived and built
from inside the app. Chosen over hand-rolling a markdown parser because the source documents
(`REQUIREMENTS.md` in particular) contain real tables, nested lists, and code fences that a small
regex-based converter is likely to mis-render; `marked` is zero-runtime-dependency, ~40 KB, and one of
the most widely audited Markdown parsers on npm. Only ever parses this project's own committed
documentation, never user input. Exact version pinned (`18.0.9`, released 2026-08-04 — past NFR-10.3's
14-day cooldown as of this addition), `.npmrc`'s `ignore-scripts=true` and the committed
`package-lock.json` apply to it like every other dependency.

## Dev workflow

```
npm ci
npm run dev
```

`vite.config.ts` proxies `/api` and `/ws` to `http://localhost:8000` — start
the `backend` container first (`docker compose up -d backend`) so there's
something to proxy to. `npm run build` type-checks (`tsc -b`) then produces
`dist/`, which is what the backend's Docker build copies into its own image.
