# Feature 006 Frontend — Screening Workbench Design

- **Date:** 2026-07-16
- **Status:** Approved shape; supersedes the layout described in the original
  `specs/006-frontend/spec.md` demo-panel sketch. The feature spec has been
  amended to point here.
- **Role:** A working engineering tool first, with the stage demo served by a
  preset plus a canned offline fallback — not a separate demo app.

## 1. Purpose

A single-user, local-first frontend for the Feature 005 screening API. It lets
an engineer compose a screening study, run it with live progress, explore the
ranked results spatially and economically, compare runs, and export a
reproducible study memo. All physics, routing, facility, and economic logic
stays in the backend; the frontend is an API client, a renderer, and a
client-side pivot over immutable results.

## 2. Shape decision

The tool is **not** case-centric like ECLIPSE or tNavigator. Those shapes exist
because full-physics simulation is expensive and batch: one deck, one long run,
deep post-processing of a single case. This system inverts both premises — runs
are cheap (hundreds of scenarios in under a minute) and the object of interest
is the comparison across a scenario space (candidates x schedules x carbon
prices x fiscal cases), ending in a ranked shortlist with provenance.

The chosen shape is a **screening workbench inside a field-twin canvas**:

- From **FutureOn FieldTwin**: the interaction grammar — a stylized 3D scene of
  the asset as the spatial index, with docked panels for depth.
- From **tNavigator AHM / Petrel U&O**: the ensemble character — runs as
  studies, rankings, cross-plots, comparisons.
- From **SimCCS**: the domain — CO2 sources, sinks, and optimized transport on
  real terrain.
- From **the SECARB storage-cost visualization**: the reservoir encoding —
  extruded grid cells where height and color carry two independent variables
  over a desaturated basemap.

No shipping product combines all four; the design deliberately borrows the
proven grammar of each.

## 3. Application chrome — the classical WIMP contract

The interface follows the **traditional desktop application idiom** (WIMP:
windows, icons, menus, pointers) shared by Photoshop, tNavigator, OpendTect,
Petrel, ECLIPSE Office, and DWSIM. This is a deliberate, load-bearing design
decision, not styling. The idiom is a functional contract with four clauses,
and every screen of this application must honor all four:

1. **The menu bar is the complete command inventory.** Every capability of the
   application is reachable and discoverable by scanning the menus. No
   capability exists only behind a hamburger, kebab, hover-reveal, floating
   action button, or gesture. If a command exists, it has a menu entry.
2. **The toolbar is the frequency layer.** It contains no unique capabilities —
   only promoted duplicates of menu commands, rendered as small, dense,
   always-visible icon buttons with tooltips naming the command and shortcut.
3. **The status bar is ambient truth.** Cursor coordinates, current selection,
   active study fingerprint, run state, and backend health are always visible
   at the bottom edge, never modal, never a toast.
4. **Panels hold state, not navigation.** There are no "pages" and no router in
   the user's mental model. The workspace persists; panels expose aspects of
   it. Nothing is lost by switching tabs.

The visual language matches the idiom: dark, dense, quiet chrome; desaturated
monochrome context; color reserved for data (in discrete legend bins) and one
accent for interaction state. No gradients-as-decoration, no oversized empty
whitespace, no marketing typography.

### 3.1 Chrome layout

```
+---------------------------------------------------------------------+
| File   Edit   View   Study   Tools   Help                           |  menu bar
+---------------------------------------------------------------------+
| new open save | undo redo | select orbit probe measure | 2D/3D      |  toolbar
| layers  field:[saturation v]  height:[inventory v]  exagg [- 5x +]  |
|                                            | >> Screen   [] Cancel  |
+--------+-----------------------------------------+------------------+
| tree   |                                         |  inspector       |
| ledger |              3D VIEWPORT                |  (selection)     |
+--------+-----------------------------------------+------------------+
| Ranking | Economics | Production | Run console | Compose            |  tab strip
+---------------------------------------------------------------------+
| (34,17) 108.42E 6.51S el 46m | sel: W12 | study a3f81c | run 51s | * |  status bar
+---------------------------------------------------------------------+
```

### 3.2 Menu tree (complete command inventory)

- **File**
  - New Study
  - Open Study… (import study-memo JSON)
  - Save Study / Save Study As… (export study-memo JSON)
  - Recent Studies
  - Export ▸ Ranking CSV · Scene Snapshot PNG · Study Memo JSON
- **Edit**
  - Undo · Redo (scope: study-definition edits only; see 3.4)
  - Find Object… (jump-to well/source/route by id)
  - Preferences… (units, default vertical exaggeration, colormap bins)
- **View**
  - 2D / 3D viewport toggle
  - Panels ▸ show/hide Project Tree · Inspector · Dashboard strip
  - Color By ▸ gas saturation · pressure · z_CO2 · oil saturation
  - Height By ▸ CO2 inventory · flat
  - Layers ▸ routes · boosters · exclusion zones · labels
  - Vertical Exaggeration ▸ 1x · 2x · 5x · 10x · custom
  - Reset Camera · Frame Selection
- **Study**
  - Load Preset ▸ (from `/presets`, with readiness states shown as-is)
  - Validate (run preflight checks now)
  - Screen (submit the run)
  - Cancel Run
  - Re-compose from Ledger Entry
  - Compare Studies…
- **Tools**
  - Grid Probe (hover cell readout)
  - Measure Distance (terrain-following)
  - Elevation Profile Along Route
- **Help**
  - Keyboard Shortcuts
  - API Documentation (opens `/docs`)
  - About — app version, API contract version, promoted checkpoint SHA-256,
    CBC solver version. Provenance lives in the About box, where a tNav or
    OpendTect user would look for it.

Menu entries show their keyboard shortcuts right-aligned, in the traditional
manner. Implementation uses accessible menubar primitives (Radix UI or
react-aria) for full keyboard navigation and focus management; menus are
in-app components, not native menus.

### 3.3 Toolbar

Only commands with real function, all duplicated from menus: select (default),
orbit/pan, grid probe, measure, 2D/3D toggle, layer toggles, color-field and
height-field dropdowns, vertical-exaggeration stepper, Screen, Cancel. The run
progress and wall-clock render inline next to the run controls while active.

### 3.4 Undo/redo scope

Undo applies to **study-definition edits** — the Compose form. It does not
apply to camera movement or selection. Results are immutable and keyed by
`request_fingerprint`, so there is nothing destructive to undo downstream of
submission. This gives honest Ctrl+Z value without pretending the whole
application is a document editor.

### 3.5 Keyboard layer

Ctrl+Z / Ctrl+Y undo/redo · Ctrl+O / Ctrl+S open/save study · Ctrl+F find
object · Space play/pause plume timeline · Left/Right step timeline frames ·
F frame selection · 1–4 switch color field · Esc cancel active tool.

### 3.6 Status bar contents

Cursor position as grid (i,j) plus geographic coordinates plus terrain
elevation · current selection id · active study short fingerprint · run
wall-clock while running · backend health dot fed by `/health`. The preflight
checklist collapses into this always-visible ambient state.

## 4. Workspace regions

Fixed regions with collapsible and tabbed panels. **No docking framework** —
no floating, tearing, or free rearrangement. This is 90% of the FieldTwin feel
at 10% of the failure modes.

- **Project tree (left).** The loaded study's objects: Sources, Candidate
  Wells, Network (routes, boosters), Facilities — plus the **Run Ledger**
  listing this session's completed runs by short fingerprint. Read-only
  structure; selection source.
- **3D viewport (center).** See section 5. Read-only scene: a spatial index,
  never an editor.
- **Inspector (right).** Properties of the current selection: key results,
  confidence flags, cost basis, per-object warnings. The FieldTwin properties
  panel, repurposed for results instead of editable geometry.
- **Dashboard tab strip (bottom).** Sibling tabs, all functional without the
  viewport:
  - **Ranking** — the anchor table; rows are plans; selecting a row drives the
    global selection.
  - **Economics** — KPI tiles (NPV, IRR, break-even carbon and oil price, net
    CO2 stored), cost/revenue waterfall, uncertainty band, and the
    **carbon-price scrubber**.
  - **Production** — cumulative oil, gas, net CO2 stored; screening mode shows
    scenario spaghetti with the selected plan highlighted.
  - **Run console** — SSE stage timeline (surrogate batch → per-price network
    selection → selected-well facilities → two-pass economics → shortlist),
    inline warnings, dedup counter (`unique_inference_count` /
    `logical_scenario_count`), wall-clock, cancel.
  - **Compose** — the study composer (section 7.2).
  - A **facility PFD panel** (static process-flow diagram with Feature 003
    numbers bound in) renders inside the Inspector when a facility object is
    selected. DWSIM is never run live.

### 4.1 Shared selection model

One global selection (object id + optional carbon-price context). Clicking a
tree node, a scene object, or a ranking row are the same event. The inspector,
economics tab, production tab, and viewport highlight all follow it. The
carbon-price scrubber is part of selection context: changing it re-pivots the
ranking and re-colors the scene without any API call.

## 5. 3D viewport

### 5.1 Scene content and encoding

- **Terrain:** SRTM heightmap as a single monochrome low-poly mesh. No
  textures, no tile streaming, no photorealism. User-adjustable vertical
  exaggeration (default 5x; range 1–10x) because local relief is unreadable at
  1:1 next to route lengths.
- **Reservoir cells (the SECARB encoding):** the 64x64 surrogate grid rendered
  as one instanced mesh of up to 4,096 extruded prisms on a plane beneath the
  terrain (stylized cutaway). **Height encodes per-cell CO2 inventory; color
  encodes a user-switchable field** (gas saturation, pressure, z_CO2, oil
  saturation) in **discrete legend bins** — never continuous gradients. The
  plume timeline scrubber animates prism heights/colors from typed arrays
  across inject → soak → produce. The legend always states both encodings
  explicitly ("taller cells = more CO2 stored").
- **Portfolio zoom:** before drill-in, each candidate well renders as its
  extruded footprint (height = total stored, color = NPV bin or shortlist
  status). Wells dropping off the shortlist as the carbon-price scrubber moves
  visibly flatten/dim; a supply mode flipping pipeline→trucking visibly
  switches line style. The scene reacting to the price scrubber is a primary
  demo moment.
- **Transport:** pipelines as solid terrain-hugging tubes; trucking as dashed
  ground polylines; boosters as markers at their stations; exclusion zones as
  flat hatched patches. Selecting a route surfaces the pressure-along-route
  profile with the dense-phase floor line and booster rescue points (chart in
  the inspector).
- **Sources and wells** as accent-colored markers with labels (toggleable).

### 5.2 Rendering and robustness

react-three-fiber / three.js. One static scene graph; per-frame updates limited
to instanced attribute buffers (heights, colors) — smooth on integrated laptop
GPUs by construction. Orbit + zoom + pan only.

The viewport lives behind an **error boundary with an automatic 2D fallback**:
a flat map view (terrain image + SVG overlay for wells/routes/boosters) that
supports the same selection model. A GPU or driver failure degrades to a fully
working 2D tool, never a blank screen. Every dashboard tab is functional with
the viewport dead.

## 6. Stack and packaging

- **Vite + React + TypeScript SPA** in `frontend/`, built to static assets,
  mounted by the existing FastAPI app via `StaticFiles` (API routes untouched).
  One process, one port, no CORS, no Node runtime in production. Dev mode is
  the Vite dev server proxying API routes to `:8000`.
- **Types generated from `specs/005-screening-api/contracts/openapi.yaml`**
  via `openapi-typescript`; contract drift breaks the build, not the demo.
- Libraries: react-three-fiber + three (viewport), Recharts (charts), Zustand
  (workspace/selection state), TanStack Query (GET endpoints), Radix UI or
  react-aria (menubar/menus/tabs). No docking framework, no map-tile library,
  no browser storage.
- The only backend change is the static mount — packaging, not logic. The
  "no physics or economics in the frontend" rule holds absolutely.

## 7. Workflow

Preflight → Compose → Run → Explore → Compare → Export.

### 7.1 Preflight

`/health` and `/presets` feed the status-bar health dot and the Study ▸
Validate report. The Screen command is gated on readiness. Preset readiness is
shown **as reported** — a `NOT READY` or `BLOCKED` preset appears with exactly
that state and reason; the UI never papers over backend honesty.

### 7.2 Compose

A constrained study composer mirroring `InlineScreenRequest`: preset picker or
geology/operational/source/price/fiscal sections. Client-side mirror of the
422 validation rules; **trained-range enforcement flags out-of-envelope inputs
amber before submission**; live logical-scenario-count preview. A drawer shows
the literal request JSON — the payload is the deck, inspectable verbatim.

**Re-compose from study** is first-class: the composer must hydrate from any
ledger entry (imported or session-local), because import → edit one
assumption → re-run is the primary real-world loop.

### 7.3 Run

`POST /screen/stream` consumed as SSE. Because `EventSource` cannot POST, the
client uses fetch + `ReadableStream` with a small, unit-tested SSE parser. The
run console renders the event enum directly (`run_started`, `stage_started`,
`progress`, `stage_completed`, `warning`, `result`, `error`, `cancelled`,
`heartbeat`). A **heartbeat watchdog** marks the run visibly stalled if no
event of any kind arrives within 3x the server heartbeat cadence — never a
frozen spinner. Stalled is a designed state offering cancel; it does not
auto-abort the run. Cancel
wires to `DELETE /screen/runs/{run_id}`. If the stream fails at connect, the
client falls back to synchronous `/screen`.

**Warnings must be cell-addressable:** a warning tied to a (well x
carbon-price) cell attaches to that cell in the results (inspector and ranking
row badge), not merely scrolled past in the console log.

### 7.4 Explore and compare

Results are immutable, keyed by `request_fingerprint`, accumulated in the
in-memory session Run Ledger. The carbon-price scrubber pivots client-side
over `cross_price_comparison` — zero API calls while dragging. Compare mode
diffs two ledger entries: highlighted request deltas (so no one can claim two
levers moved at once) plus rank trajectories and per-well NPV deltas. The
A/B/C comparison is a ledger diff, not a bespoke screen.

### 7.5 Export — the study memo

`File ▸ Save Study` exports a **study memo JSON**: request + fingerprint +
full result + flags + app/contract versions. It is simultaneously the
persistence mechanism (no browser storage; the file is the state), the
collaboration unit (a colleague imports it into their ledger), the
reproducibility contract (re-compose → run → same fingerprint or the inputs
changed), and the Feature 007 hand-off artifact. File dialogs use the File
System Access API where available, falling back to download/upload.

## 8. Robustness and honesty rules

- HTTP errors map to specific UI: **422** → field-level errors onto the
  composer; **429** → active-run conflict card with cancel offer; **503** →
  dependency banner naming the missing piece.
- Error boundaries per region: a crashed panel never takes down the workspace;
  the viewport degrades to the 2D fallback.
- **Confidence chrome everywhere:** extended-horizon flags, out-of-trained-
  range flags, screening-grade cost-basis banners, and preset readiness states
  render wherever the affected numbers appear. Flag wording is written to be
  quotable — engineers copy these caveats into review decks verbatim.
- The demo preset ships with a **canned result JSON bundled into the static
  build**, so the core demo runs with the backend down entirely.
- No browser storage APIs. Session state lives in React state; durable state
  lives in exported study-memo files.
- No blank-screen failure modes; loading, stalled, degraded, and error states
  are all designed states.

## 9. Testing

- **Vitest + React Testing Library:** composer validation (mirror of 422
  rules), ranking/price pivot logic, selection-model reducers, SSE parser.
- **SSE parser fixtures:** recorded event streams from real backend runs,
  including warning, cancellation, and error sequences.
- **Contract safety:** generated types from the OpenAPI contract as a build
  gate.
- **Playwright smoke:** preflight → load demo preset → run (live or mocked) →
  ranking renders → selection drives inspector → export memo.
- Viewport logic (encoding functions grid→instance attributes) unit-tested as
  pure functions; visual correctness checked via the Playwright screenshot on
  the canned result.

## 10. Build order

1. Shell + chrome: menu bar, toolbar, status bar, panel regions, selection
   store. Viewport region holds the **2D fallback map** as placeholder.
2. Compose + preflight + run console against the live API (SSE parser first,
   with fixtures).
3. Ranking, economics (scrubber pivot), production tabs; inspector; ledger +
   memo export/import; compare diff.
4. 3D viewport module (terrain, extruded grid, routes) as an isolated package,
   swapped into the center region last.

If the schedule squeezes, steps 1–3 are a complete working tool with a 2D map;
step 4 is the flagship surface, not a dependency.

## 11. Out of scope

- Editing in the scene (drag-drop asset placement, geometry editing).
- Docking framework (floating/tearable panels).
- Browser storage, multi-user, auth, server-side persistence.
- Any physics, routing, facility, or economic computation in the frontend.
- Running DWSIM live (the PFD panel is static with bound numbers).
- Paper-figure generation (Feature 007 owns scientific promotion; the study
  memo is the hand-off).
