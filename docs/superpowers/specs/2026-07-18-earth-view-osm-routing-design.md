# Earth View + OSM Road Routing — Design

**Date:** 2026-07-18
**Status:** approved (design Q&A with owner, 2026-07-18)
**Owner flow:** boot on the earth → dive into a basin → place field → import roads once → screen with road-accurate trucking
**Builds on:** `2026-07-17-blank-slate-field-workflow-design.md` (implemented)

## 1. Purpose

Two gaps reported after the blank-slate workflow landed, plus one baseline
correction:

1. There is no "earth" — the app boots to a flat hint card and the basin is an
   abstract heightmap slab with no real-world context.
2. Reopened studies cannot screen: launch pads are never relinked even though
   the artifacts still exist in `data/imports/`.
3. Trucking economics use a hardcoded 70 km distance for every candidate
   (`orchestrator.py:1109`); pipeline routing is terrain-accurate but trucking
   is not geometry-derived at all.

## 2. Decisions made with the owner (2026-07-18)

| Decision | Choice |
|---|---|
| "Earth view" meaning | Both: a globe-level zoom-out **and** real-map context (roads, coastline, places) on the basin terrain |
| Data policy | **Fully offline.** Bundled public-domain globe assets; map context and routing come from a user-imported OSM `.osm.pbf` extract. No runtime tile servers |
| Globe placement | **Boot state + top scene level**: earth → basin → field. The blank slate *is* the earth |
| Trucking without roads | **Haversine × 1.4 circuity factor** per candidate, provenance-labeled as an estimate. The fixed 70 km constant is removed |
| OSM stack | **pyosmium** streaming parse → hash-keyed cached graph. networkx/scipy/shapely already project deps; `osmium` is the only new one |
| OSM timing | Now, before the 2026-07-22 paper deadline; paper preset/Scenario-B reruns are the owner's call after landing |

## 3. Vocabulary (UI copy)

- **Road network** — one imported `.osm.pbf` extract clipped to the study
  terrain. UI never says "graph", "PBF", or "OSM extract" outside the import
  field label ("Road network (.osm.pbf)").
- **Earth** — the globe-level scene. Breadcrumb copy: "◂ Earth".
- Trucking distance provenance copy, verbatim:
  - with roads: `osm_road_network:<road_network_id>`
  - without: `greatcircle_detour_estimate` and the inspector line
    "Estimated from great-circle distance × 1.4 — import a road network for
    road-accurate routing."

## 4. Scene hierarchy (frontend)

`SceneLevel = "earth" | "basin" | "field"`; the field store boots at
`"earth"`.

- **Earth level** — new `EarthGlobe` component:
  - three.js sphere with bundled Blue Marble texture
    (`frontend/public/earth/blue_marble_2048.jpg`, NASA, public domain),
    Natural Earth 50m coastline polylines
    (`frontend/public/earth/ne_50m_coastline.json`, public domain), and a
    subtle graticule. Same-origin static fetches only.
  - Every terrain from `GET /terrain` renders as a footprint outline on the
    sphere; the active study's terrain is highlighted.
  - Double-click the active study's footprint → dive to its basin.
    Double-click any footprint with no study open → open the New Study
    dialog with that terrain preselected (no free-browse basin without a
    study). Hint card overlays only when no terrain is registered.
  - Camera: orbit-the-globe OrbitControls mode; lerp dive/return transitions
    reusing the existing CameraRig destination pattern.
- **Basin level** — unchanged, plus: "◂ Earth" breadcrumb; Esc (no dialog,
  no context menu, nothing mid-drag) returns to earth; new map-context
  layers (§6).
- **Field level** — unchanged.
- `setup()` and `hydrate()` land at basin exactly as today.

## 5. Backend: road-network import (`imports/roads.py`)

### Import and cache

- `import_road_network(path: Path, bbox: (minLon, minLat, maxLon, maxLat)) ->
  RoadNetworkRecord`
  - One pyosmium pass over the `.osm.pbf`:
    - Drivable ways: `highway` in {motorway, trunk, primary, secondary,
      tertiary, unclassified, residential, plus their `_link` variants}.
    - Clip to bbox padded by 20% per side.
    - Nodes: id → (lat, lon) for referenced nodes.
  - Graph: undirected edges per consecutive way-node pair with haversine
    length; keep the largest connected component.
  - Display layers from the same pass: road polylines bucketed
    {major: motorway/trunk/primary (+links), minor: the rest},
    `natural=coastline` ways, `place` in {city, town} nodes with `name`.
  - Cache under `data/imports/<sha16>/`: `roads_graph.npz` (node lat/lon
    arrays, edge src/dst/length/class arrays) and `roads_layers.json`
    (simplified with shapely `simplify`, point-capped).
  - Registry `data/imports/roads_registry.json`:
    `roads-<sha16>` → {sha256, source_path, bbox, node_count, edge_count}.
    Idempotent by content hash (same pattern as the terrain registry).
- `load_road_graph(record) -> RoadGraph` — networkx graph + scipy cKDTree
  over nodes; lazily built and memoized per process.

### Routes

- `POST /roads/import` body `{"path": str, "terrain_id": str}` →
  `{road_network_id, sha256, node_count, edge_count, bbox}`.
  422 unreadable PBF or zero drivable ways in the clipped extent; 404 unknown
  terrain.
- `GET /roads` → registry records.
- `GET /roads/{road_network_id}/layers` →
  `{roads: [{class: "major"|"minor", points: [[lat, lon], ...]}, ...],
    coastline: [[[lat, lon], ...], ...],
    places: [{name, lat, lon, kind}, ...]}`.
- `GET /reservoir/{model_id}?bank_id=` (relink, §8) → identical payload shape
  to `POST /reservoir/import`, re-loaded from the ImportStore; 404 when the
  artifact is missing.
- OpenAPI contract updated; `npm run gen:types` regenerated.

## 6. Screening contract and trucking rewire

- `InlineScreenRequest.road_network_id: str | null = None` (mirrors
  `terrain_id`; unknown id → existing 422 validation surface).
- Orchestrator trucking distance per (source, selected well):
  - **With road network:** snap both endpoints to nearest graph nodes
    (KDTree), networkx shortest path by length; distance = path length +
    straight connector legs from endpoints to their snap nodes; result
    carries the route polyline (lat/lon list). Per-pair memoized within a
    run.
  - **Without:** haversine × 1.4.
- `TruckingSupplyResult` gains `route: [[lat, lon], ...] | null` and
  `distance_provenance: str`. The `70.0` literal is removed from the
  orchestrator. (`infrastructure/validation.py`'s standalone facility
  validation harness keeps its explicit constant — it validates facility
  costing, not routing.)
- Existing presets/tests: presets carry no `road_network_id` → fallback path;
  numbers change only where 70 km was previously assumed, which is the point.

## 7. Frontend: study wiring and map layers

- **New Study dialog**: optional "Road network (.osm.pbf)" path field →
  `importRoads(path, terrainId)` after terrain import; shows
  "N nodes · M edges" on success. Failure blocks Create only if a path was
  entered (empty = skip).
- **Field store / memo**: `field_setup.roads: RoadsRef | null` where
  `RoadsRef = {road_network_id, sha256, source_path}`. Additive optional key —
  memo stays version 3. `hydrate` relinks: refetch layers; missing network →
  info banner, study still opens.
- **Layers**: `LayerVisibility` gains `roads`, `coastline`, `places`
  (default true). Basin renders draped polylines (existing route-draping
  helper) and `Html` labels for places. Layers fetched once per study from
  `GET /roads/{id}/layers` and held in the field store.
- **Request builder**: passes `road_network_id` when the study has roads.
- **Results**: trucking route polyline from the result replaces the straight
  dashed trucking line when present.

## 8. Bug fixes folded in (land first, independent)

1. **Compass** (`Viewport3D.tsx:911` static markup): a `cameraAzimuthDeg`
   value updated from inside the Canvas (`useFrame`, written only when the
   rounded degree changes) drives `transform: rotate(...)` on the HUD needle.
   Works at every scene level; unit-test the azimuth→rotation mapping.
2. **Launch-pad relink** (`field.store.ts` hydrate leaves
   `reservoirRuntime: null`; `useWorkbench.ts:97` then refuses screening):
   after `hydrate`, `hydrateMemoFieldSetup` calls
   `GET /reservoir/{model_id}?bank_id=`, verifies `sha256` (and
   `bank_sha256` when present) against the memo, and race-guards before
   `setState({reservoirRuntime})`. Artifact missing or hash mismatch → the
   existing relink banner; otherwise reopened studies screen normally.

## 9. Bundled assets and licensing

- `frontend/public/earth/blue_marble_2048.jpg` — NASA Blue Marble, public
  domain. ~0.3–0.5 MB.
- `frontend/public/earth/ne_50m_coastline.json` — Natural Earth 1:50m
  coastline, public domain, simplified to ≤ ~500 KB.
- `frontend/public/earth/README.md` records provenance and public-domain
  status. Downloaded once during implementation and committed; if either
  download is unavailable, the globe degrades to graticule + footprints
  (no texture/coastline) without failing.

## 10. Testing and verification

- **Backend**: pyosmium can *write* PBF — tests build a tiny synthetic
  extract fixture (a few ways forming a detour topology). Tests: import
  registers + idempotent; clip drops out-of-bbox ways; shortest-path distance
  exceeds haversine on the detour fixture; layers endpoint shape; trucking
  provenance in both modes; `/reservoir/{model_id}` 200/404; OpenAPI contract
  test; full `python -m pytest tests -q`.
- **Frontend**: field-store level transitions (boots at earth, dive/return);
  relink hydration (stubbed fetch, sha mismatch path); compass mapping;
  request builder carries `road_network_id`; `npm test -- --run`, `npx tsc
  -b`, `npm run build`.
- **Manual QA (1920×1080)**: boot → globe with footprint; dive; import
  Java PBF (one-time ~minute parse, cached); roads/coastline/places on
  basin; screen → trucking follows roads; reopen memo → screening works
  without re-import; compass tracks orbit.

## 11. Out of scope

- Online tile/imagery servers; satellite drape on the basin terrain.
- Travel-time or truck-class routing weights (length-only shortest path).
- Multi-terrain earth browsing beyond footprint display + dive.
- Regenerating paper tables/figures (owner reruns after landing).
