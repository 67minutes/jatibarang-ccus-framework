# Jatibarang CCUS Screening Workbench (Feature 006)

A single-user, local-first frontend for the Feature 005 screening API. It is a
classical **WIMP desktop workbench** (menu bar / toolbar / status bar / docked
panels — the Photoshop / tNavigator / OpendTect idiom) wrapped around a
field-twin 3D viewport. Compose a screening study, run it with live SSE
progress, explore the ranked results spatially and economically, compare runs,
and export reproducible study memos. All physics and economics stay in the
backend; this is an API client, renderer, and client-side pivot.

Design: [`docs/superpowers/specs/2026-07-16-frontend-workbench-design.md`](../docs/superpowers/specs/2026-07-16-frontend-workbench-design.md).
Spec: [`specs/006-frontend/spec.md`](../specs/006-frontend/spec.md).

## Stack

Vite + React + TypeScript, built to static assets and served by the existing
FastAPI app (one process, one port, no CORS). react-three-fiber/three
(viewport), Recharts (charts), Zustand + TanStack Query (state/data), Radix UI
(menus/tabs). Types are generated from the OpenAPI contract as a build gate.

## Develop

```bash
cd frontend
npm install
npm run gen:types          # generate API types from the OpenAPI contract
npm run dev                # Vite dev server, proxies API to :8000
```

Run the backend separately for live data:

```bash
uvicorn jatibarang_ccus.api.app:app --app-dir src --port 8000
```

## Build (served by FastAPI)

```bash
npm run build              # -> frontend/dist, auto-mounted by the FastAPI app
```

Then start the backend and open `http://127.0.0.1:8000/` — the SPA and API share
one origin. If `frontend/dist` is absent the API runs unchanged (the mount is a
guarded no-op).

## Test

```bash
npm run test               # Vitest units (SSE parser, price pivot, validation,
                           #   compare, scene, grid encoding)
npm run e2e                # Playwright smoke/offline/error tests (needs a
                           #   backend on :8000 serving a build)
```

## Regenerating demo assets

See [`public/assets/README.md`](public/assets/README.md). The scripts are
`scripts/gen_demo_request.py` (demo request) and `scripts/bake-terrain.mjs`
(terrain heightmap).

## Notable design points

- **Classical WIMP contract:** the menu bar is the complete command inventory;
  the toolbar is a strict subset; the status bar is ambient truth; panels hold
  state, not navigation. Menu/toolbar/keyboard all dispatch one command registry.
- **Shared selection model:** clicking the tree, the scene, or a ranking row is
  one event that drives the inspector, economics, and production panels.
- **Client-side carbon-price pivot:** the scrubber re-derives ranking/NPV/scene
  from the immutable result with zero API calls.
- **Honest by construction:** confidence flags (extended-horizon,
  out-of-trained-range, screening-grade cost basis) render wherever the affected
  numbers appear; preset readiness and the `no_viable_network` HnP outcome are
  shown as-is.
- **Robust viewport:** the 3D scene sits behind an error boundary that falls back
  to the 2D map; every dashboard panel works with the viewport dead.
