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

## Dev workflow

```
npm ci
npm run dev
```

`vite.config.ts` proxies `/api` and `/ws` to `http://localhost:8000` — start
the `backend` container first (`docker compose up -d backend`) so there's
something to proxy to. `npm run build` type-checks (`tsc -b`) then produces
`dist/`, which is what the backend's Docker build copies into its own image.
