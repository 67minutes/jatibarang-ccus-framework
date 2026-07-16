# Feature 006: Frontend (Screening Workbench)

## Purpose

A working engineering tool first, presentation centerpiece second. A
single-user, local-first workbench over the Feature 005 screening API: compose
a screening study, run it with live SSE progress, explore ranked results
spatially and economically, compare runs, and export reproducible study memos.
The stage demo is served by the demo preset plus a canned offline fallback —
not by a separate demo app.

The approved design is
[`docs/superpowers/specs/2026-07-16-frontend-workbench-design.md`](../../docs/superpowers/specs/2026-07-16-frontend-workbench-design.md).
This spec summarizes the requirements; the design doc governs on detail.

## Shape

A **screening workbench inside a field-twin canvas**, not a case-centric
simulator UI. Precedents deliberately borrowed: FieldTwin's scene-as-index
interaction grammar, tNavigator AHM / Petrel U&O ensemble-study character,
SimCCS's source–sink–transport domain, and the SECARB extruded-cell
storage-cost visualization for the reservoir encoding.

### Classical WIMP chrome (required)

The interface follows the traditional desktop application idiom shared by
Photoshop, tNavigator, OpendTect, and ECLIPSE Office — this is a functional
requirement, not styling:

- **Menu bar** (`File · Edit · View · Study · Tools · Help`) as the complete
  command inventory: every capability has a menu entry; nothing hides behind
  hamburgers or hover-reveals. Shortcuts listed right-aligned in the menus.
- **Toolbar** as the frequency layer: dense icon duplicates of menu commands
  (select, orbit, probe, measure, 2D/3D, layers, encoding dropdowns,
  exaggeration, Screen/Cancel). No unique capabilities.
- **Status bar** as ambient truth: cursor grid + geographic coordinates +
  elevation, selection, active study fingerprint, run wall-clock, `/health`
  dot.
- **Panels hold state, not navigation**: no pages; a persistent workspace with
  project tree + run ledger (left), 3D viewport (center), inspector (right),
  and a dashboard tab strip (Ranking, Economics, Production, Run console,
  Compose) at the bottom. Fixed regions with collapse/tabs; no docking
  framework.
- Undo/redo scoped to study-definition (composer) edits.
- Dark, dense, quiet chrome; desaturated context; color reserved for binned
  data plus one interaction accent (Formation Red per Intelligent Geologics
  branding).

### 3D viewport

Read-only spatial index, never an editor. Monochrome low-poly SRTM terrain
with adjustable vertical exaggeration (default 5x); the 64x64 grid as
SECARB-style extruded prisms (height = per-cell CO2 inventory, color =
switchable field in discrete legend bins) animated across inject → soak →
produce; pipelines as solid terrain-hugging tubes vs trucking as dashed lines;
boosters, sources, exclusion zones as markers/patches. Portfolio zoom shows
per-well extruded footprints that flatten/dim as the carbon-price scrubber
drops them from the shortlist. Behind an error boundary with an automatic 2D
map fallback; every panel works with the viewport dead.

## Workflow

Preflight (gates Screen on `/health` + `/presets` readiness, shown as-is
including `NOT READY`/`BLOCKED`) → Compose (constrained composer mirroring
`InlineScreenRequest`, trained-range amber flags, scenario-count preview,
literal request-JSON drawer, **re-compose from any ledger entry**) → Run (SSE
stage timeline via fetch/ReadableStream parser, heartbeat watchdog, inline
warnings, dedup counter, cancel; sync `/screen` fallback) → Explore (ranking
table anchors a global shared selection driving viewport, inspector, and
economics; carbon-price scrubber pivots client-side over
`cross_price_comparison` with zero API calls) → Compare (fingerprint-keyed
ledger diff: request deltas, rank trajectories, NPV deltas) → Export (study
memo JSON: request + fingerprint + result + flags + versions; also the
persistence and Feature 007 hand-off mechanism).

Warnings tied to a (well x carbon-price) cell must attach to that cell in the
results, not only appear in the console log.

## Demo moments (served by the workbench, preset-driven)

1. **Speed** — run console fills its stage timeline; wall-clock vs
   full-simulation annotation.
2. **The plume** — extruded-cell animation across inject → soak → produce.
3. **The pipeline** — route on real terrain with boosters; pressure profile
   holding the dense-phase floor.
4. **The slider** — carbon-price scrubber reshuffles ranking, updates NPV, and
   visibly re-shapes the scene in real time.
5. **The comparison** — A/B/C as a ledger diff with time and NPV deltas.

## DWSIM in the UI

Do **not** run DWSIM live. A static PFD panel in the inspector binds Feature
003 numbers (compression power, separator capacity, facility CAPEX/OPEX) for
the selected plan.

## Behavior rules

- All data comes from the Feature 005 API. No physics or economics in the
  frontend. The only backend change is a `StaticFiles` mount (packaging).
- No browser storage APIs; session state in React state, durable state in
  exported study-memo files.
- HTTP errors map to specific UI (422 → composer fields, 429 → active-run
  conflict card, 503 → dependency banner). Error boundaries per region; no
  blank-screen failure modes.
- Confidence chrome everywhere: extended-horizon, out-of-trained-range,
  screening-grade cost-basis flags rendered wherever affected numbers appear,
  worded to be quotable.
- A canned Jatibarang demo result is bundled into the static build so the core
  demo runs without a live backend.

## Dependencies

- Vite + React + TypeScript SPA in `frontend/`, built static, served by the
  existing FastAPI app (one process, no CORS, no Node in production).
- Types generated from `specs/005-screening-api/contracts/openapi.yaml`
  (`openapi-typescript`) as a build gate.
- react-three-fiber/three (viewport), Recharts (charts), Zustand + TanStack
  Query (state/data), Radix UI or react-aria (menubar/menus/tabs).

## Done Criteria

- [x] Full flow works against the live Feature 005 API on an inline demo study
      (Playwright smoke). The MRST preset payloads remain BLOCKED (Feature 007),
      so the demo uses inline mode, as designed.
- [x] WIMP chrome complete: menu bar as full command inventory, toolbar,
      status bar, keyboard layer (undo/redo, open/save, find, timeline keys).
- [x] Extruded-grid reservoir plume renders from real surrogate fields and
      animates across the timeline (bundled demo plume; unit-tested encoding).
- [x] Pipeline vs trucking rendered distinctly on real 3D terrain; boosters and
      the dense-phase pressure profile render for a viable network. (The demo's
      HnP volumes are honestly `no_viable_network`, so it shows the trucking
      supply; a pipeline network draws when one is economic.)
- [x] Carbon-price scrubber re-pivots ranking, NPV, and scene with **zero** API
      calls while dragging (Playwright-verified).
- [x] Run console reflects real SSE progress (real stage names), stall watchdog,
      inline warnings, dedup counter, and working cancel.
- [x] Ledger diff (A/B/C) shows request deltas, rank trajectories, NPV deltas.
- [x] Study memo export/import round-trips; re-compose hydrates the composer.
- [x] Out-of-range inputs and low-confidence results visibly flagged; preset
      readiness shown as reported (`NOT READY`/`BLOCKED` surfaced honestly).
- [x] Viewport failure degrades automatically to the 2D map with all panels
      functional; no browser storage; no blank-screen failure modes
      (Playwright offline + error-mapping tests).

## Implementation notes

- The backend selects wells only via an economically viable pipeline. At
  Huff-and-Puff CO₂ volumes no pipeline is economic, so the honest screening
  result is `no_viable_network` with an empty shortlist. The workbench surfaces
  this transparently and falls back to a pre-logistics well ranking, per-well
  predictions, and trucking as the indicated supply. This is the documented
  default-proxy outcome, not a defect.
- The only backend change is a guarded `StaticFiles` mount serving
  `frontend/dist`; no API or screening logic was modified.
- See [`frontend/README.md`](../../frontend/README.md) and the design doc for
  the full architecture, and `frontend/public/assets/README.md` for the demo
  fixtures.
