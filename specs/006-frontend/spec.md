# Feature 006: Frontend Screening Workbench

## Purpose

A single-user, local-first engineering workbench over the typed Feature 005
screening API and read-only Feature 007 paper-result API. It composes and runs
screening studies, explores ranked spatial and economic results, compares runs,
exports study memos, and interactively inspects canonical paper evidence. Physics,
routing, facility sizing, and economics stay in the backend.

The approved historical shape is documented in
[`docs/superpowers/specs/2026-07-16-frontend-workbench-design.md`](../../docs/superpowers/specs/2026-07-16-frontend-workbench-design.md).
Its dated implementation addendum governs the reservoir, split-pane, and Paper
Results extensions.

## Application shape

The interface is a screening workbench inside a field-twin canvas, using a classical
desktop WIMP contract:

- the menu bar is the complete command inventory;
- the toolbar duplicates frequent commands but adds no hidden capability;
- the status bar shows coordinates, selection, study/run state, and backend health;
- one shared selection drives the project tree, viewport, inspector, and dashboards;
- left, right, and bottom regions are constrained accessible split panes; and
- there is no browser persistence, floating window, or docking framework.

The left project tree contains study objects, the run ledger, and the APECX Paper
Results study with Figures 1-8. The center contains the 3D/2D spatial view, the right
contains the inspector, and the bottom tabs contain Ranking, Economics, Production,
Run console, Compose, and Paper Results.

## Workflow

Preflight reads `/health` and `/presets` exactly as reported. Compose mirrors the
typed screen request, surfaces training-range flags, previews scenario count, and
shows request JSON. Run uses the shared SSE/synchronous workflow with progress,
warnings, deduplication, cancellation, and error mapping. Explore and Compare use
immutable results and a client-side carbon-price pivot. Export writes a study memo;
no browser storage is used.

The Paper Results study reads immutable bundle metadata and figure/reservoir payloads.
The active `bundle_id`, freeze basis, actual scenario count, source class, and
pending/blocked status remain visible.

## Simulator-style reservoir view

The primary reservoir view is a 64 x 64 x 1 warped grid with a 900 x 600 m footprint
and constant 6 m thickness. It reconstructs 65 x 65 node elevations from
cell-centered structure and renders bounded geometry without one React component per
cell. At 1x it remains physically proportional; the independent reservoir vertical
exaggeration defaults to 8x and ranges from 1-20x.

- Default fill: log10 permeability in mD.
- Alternatives: porosity and discrete facies.
- Wells: simulator-style trajectories and completion markers.
- Coordinates: local proxy anchored to the selected well, not surveyed orientation
  or true subsea depth.

Independent layer controls cover terrain; wells; labels; routes; boosters; structural
grid and edges; permeability fill; facies, barriers, and fractures; dynamic response;
and optional legacy SECARB response columns.

Pressure is displayed as delta-P from the final warm-start frame. Oil is displayed as
`So,baseline - So,t`. Gas saturation and `z_co2` are thresholded translucent
occupancy. Only one dynamic scalar is active, with opacity and threshold controls so
permeability remains legible. A field is disabled when absent. The frontend never
relabels another scalar or loads a uniform demo plume for an unrelated result.

Paper validation cases may show synchronized MRST, surrogate, and residual panes with
one timeline, probe, camera context, and physical limits. The currently bundled
`case_0016` linked comparison exposes gas saturation; other selectors remain disabled
unless their canonical payload exists.

## Split-pane contract

- Left: 248 px default, constrained to 180-420 px.
- Right: 320 px default, constrained to 260-520 px.
- Bottom: 340 px default, constrained from 180 px to 70% of center height.

Handles use pointer capture, keyboard adjustment, double-click reset, and
collapse/restore while preserving the last session-local size. Sizes are not written
to browser storage.

## Data and API boundaries

All screening data comes from Feature 005 contracts. Canonical paper data comes from:

- `GET /paper/results`;
- `GET /paper/results/{bundle_id}`; and
- `GET /paper/results/{bundle_id}/reservoirs/{case_id}`.

Backend additions are limited to typed `detailed_reservoirs`, paper bundle/index
contracts, hash-addressed reservoir/road/spatial-artifact import routes, read-only
routes, and the guarded static build mount. No physical or economic calculation is
duplicated in TypeScript.

An editable study may assign distinct compact MRST-derived models and launch-pad
banks to contiguous well IDs W01-W20. Static field inspection follows the selected
well before screening. Detailed dynamics remain bounded to the declared top-K; memo
v4 stores those fields in a separate gzip-compressed artifact and verifies its SHA-256
when reopening the memo.

The offline study uses Figure 3's declared median validation case, `case_0016`: real
MRST-derived static geology and warm history with a frozen-checkpoint screen result.
Its local W01 position is a proxy. Missing paper or dynamic fields remain explicitly
unavailable; there is no synthetic substitution.

## Robustness and accessibility

- HTTP 422, 429, and 503 responses map to specific UI states.
- Region-level error boundaries prevent blank-screen failure.
- The 3D viewport degrades to the 2D map while all dashboards remain usable.
- Confidence, extrapolation, screening-cost, and provenance qualifications render
  beside affected values.
- Keyboard commands, split handles, menus, tabs, and dialogs remain operable without
  pointer-only interaction.
- DWSIM and MRST are never called live from the workbench.

## Implementation and validation record

- [x] Vite + React + TypeScript static application served by FastAPI.
- [x] Generated OpenAPI types, live screening/SSE workflow, cancellation, and errors.
- [x] Ranking, economic pivot, production, compare, inspector, and study-memo flow.
- [x] Real `case_0016` offline request/result rather than a uniform demo plume.
- [x] Physical reservoir geometry, property/dynamic layers, probes, wells, and legend.
- [x] Pointer/keyboard split panes with reset and collapse/restore.
- [x] APECX Paper Results study with honest ready/blocked/unavailable states.
- [x] 2D failure fallback and no browser storage.
- [x] Offline Earth boot, terrain footprints, earth/basin/field navigation, and
  camera-tracked compass.
- [x] Hash-addressed OSM import, batched context layers, per-candidate road-following
  trucking routes, and visible distance provenance.
- [x] W01-W20 reservoir catalog import plus memo-v4 top-K playback persistence.
- [ ] Load and rehearse the immutable submitted paper bundle after scientific freeze.

The current Feature 007 `working` bundle is partial and unfrozen, with scenario count
zero, mechanical `BLOCKED`, and scientific `NOT_RUN`. The workbench must preserve that
state; implemented UI is not evidence that the A/B/C paper experiment has run.
