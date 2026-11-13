# Earth View + OSM Road Routing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Boot the workbench onto an offline globe (earth → basin → field), give the basin real-map context from an imported OSM extract, route trucking over the real road network (haversine × 1.4 fallback), fix the static compass, and auto-relink launch pads when a study memo is reopened.

**Architecture:** Backend gains `imports/roads.py` (pyosmium streaming parse → hash-keyed cached networkx graph + display layers) exposed as three routes, plus a `GET /reservoir/{model_id}` relink route; the orchestrator's fixed 70 km trucking distance becomes per-candidate legs. Frontend gains an `"earth"` scene level with a bundled-asset globe, map-context layers on the basin, a camera-tracked compass, and automatic reservoir-runtime relink on memo open.

**Tech Stack:** FastAPI + pydantic v2 + pyosmium (new) + networkx/scipy/shapely (existing); React + zustand + react-three-fiber/drei + vitest; pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-earth-view-osm-routing-design.md`

**Execution status (2026-07-19):** implemented and verified in the current worktree.
The historical task checkboxes below preserve the original Claude-authored plan; the
completion record at the end is the execution source of truth.

## Global Constraints

- Fully offline: no runtime tile servers; globe assets are bundled same-origin static files; map context and routing come only from user-imported files (spec §2).
- Path-taking import routes MUST call `_require_local_client(request)` (exists in `api/app.py`) — the loopback guard is a security invariant; do not remove or bypass it.
- Trucking provenance strings, verbatim: `osm_road_network:<road_network_id>` with roads; `greatcircle_detour_estimate` without (spec §3).
- UI copy: "Road network (.osm.pbf)" for the import field; breadcrumb "◂ Earth"; the no-roads inspector line verbatim: "Estimated from great-circle distance × 1.4 — import a road network for road-accurate routing." Never say "graph", "PBF", or "OSM extract" elsewhere in UI copy.
- `STUDY_MEMO_VERSION` stays **3** — the new `field_setup.roads` key is optional/additive.
- The only new Python dependency is `osmium>=3.7` (PyPI name `osmium`). networkx, scipy, shapely are already dependencies.
- Work on branch `008-blank-slate-workbench`; commit after every task.
- After every backend task: `python -m pytest tests -q` and the contract test must pass. After every frontend task: `npm test -- --run` and `npx tsc -b` from `frontend/`.
- Existing preset screening requests carry no `road_network_id` → they take the haversine fallback path. Trucking numbers in existing integration tests change deliberately (the 70 km constant is removed); update asserted values only after manually confirming the new value is the correct haversine × 1.4 result.

---

### Task 1: Compass tracks the camera (frontend)

The HUD compass at `frontend/src/viewport/Viewport3D.tsx:911` is static markup. Wire it to the OrbitControls azimuth.

**Files:**
- Create: `frontend/src/state/camera.store.ts`
- Test: `frontend/src/state/camera.store.test.ts`
- Modify: `frontend/src/viewport/Viewport3D.tsx` (CameraRig `useFrame` at ~line 1338; `ViewportNavigationHud` at ~line 895)

**Interfaces:**
- Produces: `useCameraStore` (zustand) with `{ azimuthDeg: number; setAzimuthDeg(v: number): void }` and pure `compassRotationDeg(azimuthalAngleRad: number): number`. Task 9's earth branch does NOT use this store (compass renders only in basin/field).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/state/camera.store.test.ts
import { describe, expect, it } from "vitest";
import { compassRotationDeg, useCameraStore } from "./camera.store";

describe("camera store", () => {
  it("maps azimuthal radians to compass rotation degrees", () => {
    expect(compassRotationDeg(0)).toBe(0);
    expect(compassRotationDeg(Math.PI / 2)).toBeCloseTo(90);
    expect(compassRotationDeg(-Math.PI)).toBeCloseTo(-180);
  });
  it("stores the latest azimuth", () => {
    useCameraStore.getState().setAzimuthDeg(45);
    expect(useCameraStore.getState().azimuthDeg).toBe(45);
  });
});
```

- [ ] **Step 2: Run to verify failure** — `cd frontend && npm test -- --run src/state/camera.store.test.ts` → FAIL (module missing).

- [ ] **Step 3: Implement the store**

```typescript
// frontend/src/state/camera.store.ts
import { create } from "zustand";

/**
 * Camera azimuth shared from inside the Canvas to the HTML HUD. North in the
 * scene is -Z (terrain.ts toXZ maps increasing latitude to -Z), so an
 * OrbitControls azimuthal angle of 0 means north is up on screen.
 */
interface CameraState {
  azimuthDeg: number;
  setAzimuthDeg: (value: number) => void;
}

export const useCameraStore = create<CameraState>((set) => ({
  azimuthDeg: 0,
  setAzimuthDeg: (azimuthDeg) => set({ azimuthDeg }),
}));

/** Screen rotation of the compass rose for a camera azimuthal angle (radians). */
export function compassRotationDeg(azimuthalAngleRad: number): number {
  return (azimuthalAngleRad * 180) / Math.PI;
}
```

- [ ] **Step 4: Publish azimuth from CameraRig.** In `Viewport3D.tsx`'s `CameraRig`, add a `lastAzimuth` ref and restructure the existing `useFrame` so the azimuth is read every frame (the current body early-returns when there is no camera destination):

```tsx
const lastAzimuth = useRef(0);

useFrame((_, delta) => {
  if (controls.current) {
    const azimuth = Math.round(
      compassRotationDeg(controls.current.getAzimuthalAngle()),
    );
    if (azimuth !== lastAzimuth.current) {
      lastAzimuth.current = azimuth;
      useCameraStore.getState().setAzimuthDeg(azimuth);
    }
  }
  const next = destination.current;
  if (!next || !controls.current) return;
  // ... existing tween body unchanged ...
});
```

Import `compassRotationDeg` and `useCameraStore` from `../state/camera.store`.

- [ ] **Step 5: Rotate the HUD rose.** In `ViewportNavigationHud`:

```tsx
const azimuthDeg = useCameraStore((state) => state.azimuthDeg);
// replace the static compass div:
<div
  className="viewport-compass"
  style={{ transform: `rotate(${azimuthDeg}deg)` }}
>
  <span>N</span>
  <i />
</div>
```

- [ ] **Step 6: Tests + typecheck** — `npm test -- --run && npx tsc -b` → PASS.
- [ ] **Step 7: Manual sign check** — `npm run dev` + backend, create/open a study, orbit left and right: the N marker must swing toward where north actually is (the terrain's top edge when latitude increases away from camera). If it swings the wrong way, negate: `rotate(${-azimuthDeg}deg)` and update the store docstring.
- [ ] **Step 8: Commit** — `git add frontend/src/state/camera.store.ts frontend/src/state/camera.store.test.ts frontend/src/viewport/Viewport3D.tsx && git commit -m "fix(viewport): compass tracks camera azimuth"`

---

### Task 2: Reservoir relink endpoint (backend)

**Files:**
- Modify: `src/jatibarang_ccus/api/app.py` (refactor `reservoir_import` at ~line 364; add `GET /reservoir/{model_id}`)
- Modify: `specs/005-screening-api/contracts/openapi.yaml`
- Test: `tests/imports/test_import_api.py` (append)

**Interfaces:**
- Produces: `GET /reservoir/{model_id}?bank_id=` returning exactly the same JSON shape as `POST /reservoir/import` (keys: `model_id, sha256, source_file, geology, native_schedule, native_fingerprint, well_ij, completion_ij, launchpads{bank_id, bank_sha256, covered_fingerprints}, native_seed, bank_seeds`). 404 when the artifact id is unknown; 422 when the stored file no longer parses. Task 3 consumes this route. No loopback guard: it takes no client paths — it only resolves ids inside the app's own store.

- [ ] **Step 1: Write the failing test** (append to `tests/imports/test_import_api.py`):

```python
def test_reservoir_get_reloads_from_the_artifact_store(tmp_path: Path) -> None:
    model = Path("data/validation_cases/case_0016.mat")
    bank_entry = load_mrst_reservoir(Path("data/validation_cases/case_0115.mat")).seed
    bank_path = tmp_path / "model.launchpads.npz"
    write_launchpad_bank(bank_path, {bank_entry.schedule_fingerprint: bank_entry})

    with TestClient(_app(tmp_path)) as client:
        imported = client.post(
            "/reservoir/import",
            json={"model_path": str(model), "bank_path": str(bank_path)},
        ).json()

        again = client.get(
            f"/reservoir/{imported['model_id']}",
            params={"bank_id": imported["launchpads"]["bank_id"]},
        )
        assert again.status_code == 200
        body = again.json()
        assert body["sha256"] == imported["sha256"]
        assert body["native_fingerprint"] == imported["native_fingerprint"]
        assert body["launchpads"] == imported["launchpads"]
        assert set(body["bank_seeds"]) == set(imported["bank_seeds"])
        assert body["native_seed"]

        assert client.get("/reservoir/00000000deadbeef").status_code == 404
        missing_bank = client.get(
            f"/reservoir/{imported['model_id']}",
            params={"bank_id": "00000000deadbeef"},
        )
        assert missing_bank.status_code == 404
```

- [ ] **Step 2: Run to verify failure** — `python -m pytest tests/imports/test_import_api.py -q` → FAIL (405/404 on GET).

- [ ] **Step 3: Refactor + implement.** Read the current `reservoir_import` body first. Extract everything after the artifact `put` calls into a helper that both routes share (module-level or inside `create_app` beside the routes):

```python
def _reservoir_payload(
    model_path: Path,
    model_id: str,
    model_sha: str,
    bank_path: Path | None,
    bank_id: str | None,
    bank_sha: str | None,
) -> dict[str, Any]:
    imported = load_mrst_reservoir(model_path)
    covered = [imported.seed.schedule_fingerprint]
    bank_seeds: dict[str, Any] = {}
    if bank_path is not None:
        bank = load_launchpad_bank(bank_path)
        covered = sorted(set(covered) | set(bank))
        bank_seeds = {fp: seed.model_dump() for fp, seed in bank.items()}
    return {
        "model_id": model_id,
        "sha256": model_sha,
        "source_file": model_path.name,
        "geology": imported.geology.model_dump(),
        "native_schedule": imported.schedule.model_dump(),
        "native_fingerprint": imported.seed.schedule_fingerprint,
        "well_ij": list(imported.well_ij),
        "completion_ij": [list(pair) for pair in imported.completion_ij],
        "launchpads": {
            "bank_id": bank_id, "bank_sha256": bank_sha,
            "covered_fingerprints": covered,
        },
        "native_seed": imported.seed.model_dump(),
        "bank_seeds": bank_seeds,
    }
```

Match the exact current response construction when extracting — if the current route's keys differ from the above, the current route wins; the helper must produce byte-identical responses for `POST /reservoir/import`. Then the new route:

```python
    @application.get(
        "/reservoir/{model_id}",
        summary="Re-load an imported reservoir model from the artifact store",
        responses={200: {"description": "Typed reservoir payload and coverage"},
                   404: {"description": "Imported artifact is missing"},
                   422: {"description": "Stored artifact is unreadable"}},
    )
    def reservoir_get(model_id: str, bank_id: str | None = None) -> dict[str, Any]:
        try:
            model_path = artifacts.resolve(model_id)
            bank_path = artifacts.resolve(bank_id) if bank_id else None
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        model_sha = hashlib.sha256(model_path.read_bytes()).hexdigest().upper()
        bank_sha = (
            hashlib.sha256(bank_path.read_bytes()).hexdigest().upper()
            if bank_path else None
        )
        try:
            return _reservoir_payload(
                model_path, model_id, model_sha, bank_path, bank_id, bank_sha,
            )
        except (MrstImportError, LaunchpadBankError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
```

Add `import hashlib` to app.py's imports if absent.

- [ ] **Step 4: Contract.** In `specs/005-screening-api/contracts/openapi.yaml` add after `/reservoir/import`:

```yaml
  /reservoir/{model_id}:
    get:
      summary: Re-load an imported reservoir model from the artifact store
      parameters:
        - {in: path, name: model_id, required: true, schema: {type: string}}
      responses:
        '200': {description: Typed reservoir payload and coverage}
        '404': {description: Imported artifact is missing}
        '422': {description: Stored artifact is unreadable}
```

- [ ] **Step 5: Verify** — `python -m pytest tests/imports tests/screening/test_api_contract.py -q` then `python -m pytest tests -q` → PASS.
- [ ] **Step 6: Regen types + commit** — `cd frontend && npm run gen:types && cd ..`, then `git add src/jatibarang_ccus/api/app.py specs/005-screening-api/contracts/openapi.yaml tests/imports/test_import_api.py frontend/src/api/types.gen.ts && git commit -m "feat(api): reservoir relink route reloading from the artifact store"`

---

### Task 3: Auto-relink launch pads on memo open (frontend)

**Files:**
- Modify: `frontend/src/api/client.ts` (add `getReservoir`)
- Modify: `frontend/src/memo/import.ts` (`hydrateMemoFieldSetup`)
- Modify: `frontend/src/run/useWorkbench.ts` (~lines 360–370: the unconditional `memo-reservoir-relink` banner)
- Test: `frontend/src/memo/studyMemo.test.ts` (append), `frontend/src/api/importClient.test.ts` (append)

**Interfaces:**
- Consumes: Task 2's `GET /reservoir/{model_id}?bank_id=`.
- Produces: `getReservoir(modelId: string, bankId?: string | null): Promise<ReservoirImportResponse>` in `client.ts`. After a successful open, `useFieldStore.getState().reservoirRuntime` is populated and `prepareScreeningRequest` (`useWorkbench.ts:97`) succeeds without changes.

- [ ] **Step 1: Failing client test** (append to `importClient.test.ts`, follow its existing fetch-stub pattern):

```typescript
it("fetches a reservoir relink by model and bank id", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ model_id: "m1" }))));
  const result = await getReservoir("m1", "b1");
  expect(result.model_id).toBe("m1");
  const [url] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
  expect(url).toBe("/reservoir/m1?bank_id=b1");
});
```

- [ ] **Step 2: Failing hydration tests** (append to `studyMemo.test.ts`; mirror its existing stubbed-fetch memo fixtures — read the file's `memo(...)` helper first):
  - opening a v3 memo whose relink fetch succeeds with matching `sha256` (and matching `bank_sha256` when the memo has one) sets `reservoirRuntime` to the fetched payload;
  - a relink response with a mismatched `sha256` leaves `reservoirRuntime` null;
  - a rejected relink fetch leaves `reservoirRuntime` null and the memo still opens (no throw).

- [ ] **Step 3: Implement `getReservoir`** in `client.ts` following the `importReservoir` request helper pattern:

```typescript
export function getReservoir(
  modelId: string,
  bankId?: string | null,
): Promise<ReservoirImportResponse> {
  const query = bankId ? `?bank_id=${encodeURIComponent(bankId)}` : "";
  return requestJson(`/reservoir/${encodeURIComponent(modelId)}${query}`);
}
```

(`requestJson` = whatever internal helper `importReservoir` uses; match it exactly.)

- [ ] **Step 4: Relink in `hydrateMemoFieldSetup`** (`memo/import.ts`), after `field.hydrate(...)`, alongside the existing overview refetch:

```typescript
try {
  const runtime = await getReservoir(
    memo.field_setup.reservoir.model_id,
    memo.field_setup.reservoir.bank_id,
  );
  const active = useFieldStore.getState().reservoir;
  const stillOpen = active?.model_id === memo.field_setup.reservoir.model_id;
  const verified =
    runtime.sha256 === memo.field_setup.reservoir.sha256 &&
    (!memo.field_setup.reservoir.bank_sha256 ||
      runtime.launchpads.bank_sha256 === memo.field_setup.reservoir.bank_sha256);
  if (stillOpen && verified) {
    useFieldStore.setState({ reservoirRuntime: runtime });
    ui.dismissBanner("memo-reservoir-relink");
  }
} catch {
  // Artifact missing from data/imports: the memo still opens read-only and
  // the useWorkbench banner explains how to restore it.
}
```

- [ ] **Step 5: Make the useWorkbench banner conditional.** Read `useWorkbench.ts` around lines 355–370: it currently pushes `memo-reservoir-relink` on every field-setup open. Change the condition to push only when `useFieldStore.getState().reservoirRuntime == null` after hydration completes, and update the banner message to: "The imported reservoir files for this study could not be found in data/imports. Re-import the model via New Study to screen again." (The hydration is async — move the banner decision after the awaited `hydrateMemoFieldSetup` call.)

- [ ] **Step 6: Verify** — `npm test -- --run && npx tsc -b` → PASS. Manual QA: create study → save memo → reload the app (or File ▸ Open) → open the memo → the compose panel screens without any "read-only" banner.
- [ ] **Step 7: Commit** — `git add -A frontend && git commit -m "fix(memo): auto-relink reservoir runtime from the artifact store on open"`

---

### Task 4: Roads import module (backend)

pyosmium parse → clipped drivable graph + display layers, hash-keyed cache, registry — mirroring `imports/terrain.py`.

**Files:**
- Modify: `pyproject.toml` (add `"osmium>=3.7",` to `dependencies`)
- Create: `src/jatibarang_ccus/imports/roads.py`
- Test: `tests/imports/test_roads.py`

**Interfaces:**
- Produces (Tasks 5 and 6 rely on these exact names):
  - `class RoadsImportError(ValueError)`
  - `@dataclass RoadNetworkRecord: road_network_id: str; sha256: str; source_path: str; bbox: tuple[float, float, float, float]; node_count: int; edge_count: int` (bbox = minLon, minLat, maxLon, maxLat — the padded clip actually used)
  - `class RoadsRegistry(root: Path)` with `imports(path: Path, extent: tuple[minLon, minLat, maxLon, maxLat]) -> RoadNetworkRecord`, `list() -> list[RoadNetworkRecord]`, `get(road_network_id) -> RoadNetworkRecord` (KeyError when unknown), `layers(road_network_id) -> dict`, `graph(road_network_id) -> RoadGraph` (lazy, memoized per instance)
  - `@dataclass RoadGraph: road_network_id: str; latlon: np.ndarray; graph: nx.Graph; kdtree: cKDTree; lon_scale: float` with methods `snap(lat, lon) -> tuple[int, float]` (node index, straight connector km) and `shortest_path_km(a: int, b: int) -> tuple[float, list[tuple[float, float]]]` (km, lat/lon polyline)
  - `haversine_km(lat1, lon1, lat2, lon2) -> float`
  - Registry index file: `<root>/roads_registry.json`; caches `<root>/<sha16>/roads_graph.npz` and `<root>/<sha16>/roads_layers.json`; `road_network_id = "roads-" + sha256[:16].lower()`.

- [ ] **Step 1: Add the dependency** — edit `pyproject.toml` dependencies (alphabetical: after `numpy`), then `python -m pip install osmium` and verify `python -c "import osmium; print(osmium.__version__)"`.

- [ ] **Step 2: Write the failing tests**

```python
# tests/imports/test_roads.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import osmium
import pytest

from jatibarang_ccus.imports.roads import (
    RoadsImportError,
    RoadsRegistry,
    haversine_km,
)

EXTENT = (107.0, -6.6, 107.2, -6.3)  # minLon, minLat, maxLon, maxLat


def write_pbf(path: Path) -> None:
    """Synthetic extract: a two-segment detour road between A and B, one road
    outside the extent, one coastline way, one town, one ignored waterway."""
    writer = osmium.SimpleWriter(str(path))
    nodes = {
        1: (107.02, -6.50),  # A
        2: (107.10, -6.35),  # detour apex
        3: (107.18, -6.50),  # B
        4: (109.00, -6.50),  # outside extent
        5: (109.10, -6.50),
        6: (107.10, -6.45),  # town
        7: (107.00, -6.30),  # coastline
        8: (107.20, -6.30),
        9: (107.05, -6.55),  # waterway
        10: (107.15, -6.55),
    }
    for node_id, (lon, lat) in nodes.items():
        tags = {}
        if node_id == 6:
            tags = {"place": "town", "name": "Testville"}
        writer.add_node(
            osmium.osm.mutable.Node(id=node_id, location=(lon, lat), tags=tags)
        )
    writer.add_way(osmium.osm.mutable.Way(id=1, nodes=[1, 2, 3], tags={"highway": "primary"}))
    writer.add_way(osmium.osm.mutable.Way(id=2, nodes=[4, 5], tags={"highway": "primary"}))
    writer.add_way(osmium.osm.mutable.Way(id=3, nodes=[7, 8], tags={"natural": "coastline"}))
    writer.add_way(osmium.osm.mutable.Way(id=4, nodes=[9, 10], tags={"waterway": "river"}))
    writer.close()


@pytest.fixture()
def pbf(tmp_path: Path) -> Path:
    path = tmp_path / "toy.osm.pbf"
    write_pbf(path)
    return path


def test_import_registers_clips_and_is_idempotent(tmp_path: Path, pbf: Path) -> None:
    registry = RoadsRegistry(tmp_path / "imports")
    record = registry.imports(pbf, EXTENT)
    assert record.road_network_id.startswith("roads-")
    assert record.node_count == 3          # ways outside the extent dropped
    assert record.edge_count == 2
    assert registry.imports(pbf, EXTENT).road_network_id == record.road_network_id
    assert [r.road_network_id for r in registry.list()] == [record.road_network_id]


def test_shortest_path_beats_haversine_on_the_detour(tmp_path: Path, pbf: Path) -> None:
    registry = RoadsRegistry(tmp_path / "imports")
    record = registry.imports(pbf, EXTENT)
    graph = registry.graph(record.road_network_id)
    a_idx, a_conn = graph.snap(-6.50, 107.02)
    b_idx, b_conn = graph.snap(-6.50, 107.18)
    assert a_conn < 0.1 and b_conn < 0.1   # snapped exactly onto road nodes
    path_km, route = graph.shortest_path_km(a_idx, b_idx)
    direct_km = haversine_km(-6.50, 107.02, -6.50, 107.18)
    assert path_km > direct_km * 1.5       # the detour is much longer
    assert len(route) == 3                 # A -> apex -> B polyline


def test_layers_carry_roads_coastline_and_places(tmp_path: Path, pbf: Path) -> None:
    registry = RoadsRegistry(tmp_path / "imports")
    record = registry.imports(pbf, EXTENT)
    layers = registry.layers(record.road_network_id)
    assert layers["roads"] and layers["roads"][0]["class"] == "major"
    assert layers["coastline"]
    assert layers["places"] == [
        {"name": "Testville", "lat": -6.45, "lon": 107.10, "kind": "town"}
    ]


def test_rejects_non_pbf(tmp_path: Path) -> None:
    bogus = tmp_path / "roads.osm.pbf"
    bogus.write_bytes(b"not a pbf")
    with pytest.raises(RoadsImportError):
        RoadsRegistry(tmp_path / "imports").imports(bogus, EXTENT)
```

Note on layer coordinates: places store float lat/lon as parsed — compare with `pytest.approx` if exact equality fails on OSM's 1e-7 coordinate grid.

- [ ] **Step 3: Run to verify failure** — `python -m pytest tests/imports/test_roads.py -q` → FAIL (module missing).

- [ ] **Step 4: Implement `roads.py`**

```python
# src/jatibarang_ccus/imports/roads.py
"""OSM road-network import: one .osm.pbf -> clipped drivable graph + layers.

One import serves two consumers with one hash: trucking routing (graph) and
the basin's real-map context (display layers). Registry and cache layout
mirror imports/terrain.py (spec 2026-07-18 §5).
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import networkx as nx
import numpy as np
import osmium
from scipy.spatial import cKDTree

DRIVABLE = {
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "unclassified", "residential",
    "motorway_link", "trunk_link", "primary_link", "secondary_link",
}
MAJOR = {"motorway", "trunk", "primary", "motorway_link", "trunk_link", "primary_link"}
PAD_FRACTION = 0.2
MAX_LAYER_POINTS_PER_LINE = 400
EARTH_RADIUS_KM = 6371.0088


class RoadsImportError(ValueError):
    """The file is not a readable OSM extract with drivable ways in the extent."""


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rad = math.pi / 180.0
    dlat = (lat2 - lat1) * rad
    dlon = (lon2 - lon1) * rad
    h = (
        math.sin(dlat / 2) ** 2
        + math.cos(lat1 * rad) * math.cos(lat2 * rad) * math.sin(dlon / 2) ** 2
    )
    return EARTH_RADIUS_KM * 2 * math.atan2(math.sqrt(h), math.sqrt(1 - h))


@dataclass(frozen=True)
class RoadNetworkRecord:
    road_network_id: str
    sha256: str
    source_path: str
    bbox: tuple[float, float, float, float]
    node_count: int
    edge_count: int


@dataclass
class RoadGraph:
    road_network_id: str
    latlon: np.ndarray  # (N, 2) lat, lon
    graph: nx.Graph
    kdtree: cKDTree
    lon_scale: float

    def snap(self, lat: float, lon: float) -> tuple[int, float]:
        _, index = self.kdtree.query([lat, lon * self.lon_scale])
        node_lat, node_lon = self.latlon[int(index)]
        return int(index), haversine_km(lat, lon, float(node_lat), float(node_lon))

    def shortest_path_km(self, a: int, b: int) -> tuple[float, list[tuple[float, float]]]:
        nodes = nx.shortest_path(self.graph, a, b, weight="length_m")
        length_m = sum(
            self.graph.edges[u, v]["length_m"] for u, v in zip(nodes, nodes[1:])
        )
        route = [(float(self.latlon[n][0]), float(self.latlon[n][1])) for n in nodes]
        return length_m / 1000.0, route


class _Collector(osmium.SimpleHandler):
    def __init__(self, bbox: tuple[float, float, float, float]) -> None:
        super().__init__()
        self.bbox = bbox
        self.node_coords: dict[int, tuple[float, float]] = {}  # ref -> (lat, lon)
        self.edges: list[tuple[int, int, float, str]] = []
        self.road_lines: list[tuple[str, list[tuple[float, float]]]] = []
        self.coastline: list[list[tuple[float, float]]] = []
        self.places: list[dict] = []

    def _inside(self, lat: float, lon: float) -> bool:
        min_lon, min_lat, max_lon, max_lat = self.bbox
        return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat

    def node(self, n: "osmium.osm.Node") -> None:
        kind = n.tags.get("place")
        if kind in {"city", "town"} and "name" in n.tags and n.location.valid():
            lat, lon = n.location.lat, n.location.lon
            if self._inside(lat, lon):
                self.places.append(
                    {"name": n.tags["name"], "lat": lat, "lon": lon, "kind": kind}
                )

    def way(self, w: "osmium.osm.Way") -> None:
        highway = w.tags.get("highway")
        is_road = highway in DRIVABLE
        is_coast = w.tags.get("natural") == "coastline"
        if not is_road and not is_coast:
            return
        points: list[tuple[int, float, float]] = []
        for nd in w.nodes:
            if not nd.location.valid():
                continue
            lat, lon = nd.location.lat, nd.location.lon
            if self._inside(lat, lon):
                points.append((nd.ref, lat, lon))
        if len(points) < 2:
            return
        if is_coast:
            self.coastline.append([(lat, lon) for _, lat, lon in points])
            return
        bucket = "major" if highway in MAJOR else "minor"
        self.road_lines.append((bucket, [(lat, lon) for _, lat, lon in points]))
        for (ref_a, lat_a, lon_a), (ref_b, lat_b, lon_b) in zip(points, points[1:]):
            self.node_coords[ref_a] = (lat_a, lon_a)
            self.node_coords[ref_b] = (lat_b, lon_b)
            self.edges.append(
                (ref_a, ref_b, haversine_km(lat_a, lon_a, lat_b, lon_b) * 1000.0, highway)
            )


def _simplify(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if len(points) <= MAX_LAYER_POINTS_PER_LINE:
        return points
    step = math.ceil(len(points) / MAX_LAYER_POINTS_PER_LINE)
    kept = points[::step]
    if kept[-1] != points[-1]:
        kept.append(points[-1])
    return kept


class RoadsRegistry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.index_path = self.root / "roads_registry.json"
        self._graphs: dict[str, RoadGraph] = {}

    def _read_index(self) -> dict[str, dict]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, index: dict[str, dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(
            json.dumps(index, indent=2, sort_keys=True), encoding="utf-8"
        )

    def imports(
        self, path: Path, extent: tuple[float, float, float, float]
    ) -> RoadNetworkRecord:
        path = Path(path)
        if not path.exists():
            raise RoadsImportError(f"road network file is missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        road_network_id = f"roads-{digest[:16].lower()}"
        index = self._read_index()
        pad_lon = (extent[2] - extent[0]) * PAD_FRACTION
        pad_lat = (extent[3] - extent[1]) * PAD_FRACTION
        bbox = (
            extent[0] - pad_lon, extent[1] - pad_lat,
            extent[2] + pad_lon, extent[3] + pad_lat,
        )
        entry = index.get(road_network_id)
        if entry is None or tuple(entry["bbox"]) != bbox:
            collector = _Collector(bbox)
            try:
                collector.apply_file(str(path), locations=True)
            except (RuntimeError, OSError) as exc:
                raise RoadsImportError(f"not a readable OSM extract: {path.name}: {exc}") from exc
            if not collector.edges:
                raise RoadsImportError(
                    f"no drivable roads found inside the terrain extent: {path.name}"
                )
            graph = nx.Graph()
            for ref_a, ref_b, length_m, highway in collector.edges:
                graph.add_edge(ref_a, ref_b, length_m=length_m, highway=highway)
            largest = max(nx.connected_components(graph), key=len)
            graph = graph.subgraph(largest).copy()
            refs = sorted(graph.nodes)
            ref_to_index = {ref: i for i, ref in enumerate(refs)}
            latlon = np.array(
                [collector.node_coords[ref] for ref in refs], dtype=np.float64
            )
            edge_src = np.array(
                [ref_to_index[a] for a, b in graph.edges], dtype=np.int64
            )
            edge_dst = np.array(
                [ref_to_index[b] for a, b in graph.edges], dtype=np.int64
            )
            edge_len = np.array(
                [graph.edges[a, b]["length_m"] for a, b in graph.edges],
                dtype=np.float64,
            )
            cache_dir = self.root / digest[:16].lower()
            cache_dir.mkdir(parents=True, exist_ok=True)
            np.savez_compressed(
                cache_dir / "roads_graph.npz",
                latlon=latlon, edge_src=edge_src, edge_dst=edge_dst, edge_len=edge_len,
            )
            layers = {
                "roads": [
                    {"class": bucket, "points": _simplify(line)}
                    for bucket, line in collector.road_lines
                ],
                "coastline": [_simplify(line) for line in collector.coastline],
                "places": collector.places,
            }
            (cache_dir / "roads_layers.json").write_text(
                json.dumps(layers), encoding="utf-8"
            )
            index[road_network_id] = {
                "sha256": digest,
                "source_path": str(path),
                "bbox": list(bbox),
                "node_count": int(latlon.shape[0]),
                "edge_count": int(edge_src.shape[0]),
            }
            self._write_index(index)
            self._graphs.pop(road_network_id, None)
        return self.get(road_network_id)

    def list(self) -> list[RoadNetworkRecord]:
        return [self.get(road_network_id) for road_network_id in sorted(self._read_index())]

    def get(self, road_network_id: str) -> RoadNetworkRecord:
        entry = self._read_index().get(road_network_id)
        if entry is None:
            raise KeyError(f"road network is not registered: {road_network_id}")
        return RoadNetworkRecord(
            road_network_id=road_network_id,
            sha256=entry["sha256"],
            source_path=entry["source_path"],
            bbox=tuple(entry["bbox"]),
            node_count=entry["node_count"],
            edge_count=entry["edge_count"],
        )

    def _cache_dir(self, road_network_id: str) -> Path:
        return self.root / road_network_id.removeprefix("roads-")

    def layers(self, road_network_id: str) -> dict:
        self.get(road_network_id)
        return json.loads(
            (self._cache_dir(road_network_id) / "roads_layers.json").read_text(
                encoding="utf-8"
            )
        )

    def graph(self, road_network_id: str) -> RoadGraph:
        cached = self._graphs.get(road_network_id)
        if cached is not None:
            return cached
        self.get(road_network_id)
        data = np.load(self._cache_dir(road_network_id) / "roads_graph.npz")
        latlon = data["latlon"]
        graph = nx.Graph()
        for src, dst, length in zip(data["edge_src"], data["edge_dst"], data["edge_len"]):
            graph.add_edge(int(src), int(dst), length_m=float(length))
        mid_lat = float(latlon[:, 0].mean())
        lon_scale = math.cos(math.radians(mid_lat))
        kdtree = cKDTree(
            np.column_stack([latlon[:, 0], latlon[:, 1] * lon_scale])
        )
        built = RoadGraph(
            road_network_id=road_network_id,
            latlon=latlon, graph=graph, kdtree=kdtree, lon_scale=lon_scale,
        )
        self._graphs[road_network_id] = built
        return built
```

pyosmium API note: `osmium.SimpleWriter` / `osmium.osm.mutable.Node(location=(lon, lat))` write test fixtures; `apply_file(path, locations=True)` makes `w.nodes[i].location` valid. If `SimpleWriter` in the installed version requires keyword-only args or `Tag` lists instead of dicts, adapt the test helper — the module API above is the fixed part.

- [ ] **Step 5: Run tests** — `python -m pytest tests/imports/test_roads.py -q` → PASS. Then full: `python -m pytest tests -q` → PASS.
- [ ] **Step 6: Commit** — `git add pyproject.toml src/jatibarang_ccus/imports/roads.py tests/imports/test_roads.py && git commit -m "feat(imports): OSM road-network import with cached graph and map layers"`

---

### Task 5: Roads API routes (backend)

**Files:**
- Modify: `src/jatibarang_ccus/api/app.py`
- Modify: `specs/005-screening-api/contracts/openapi.yaml`
- Test: `tests/imports/test_import_api.py` (append)

**Interfaces:**
- Consumes: Task 4's `RoadsRegistry`, `RoadsImportError`.
- Produces (Task 7's client consumes exactly these):
  - `POST /roads/import` body `{"path": str, "terrain_id": str}` → `{road_network_id, sha256, node_count, edge_count, bbox: [minLon, minLat, maxLon, maxLat]}`; 404 unknown terrain; 422 unreadable/empty; **loopback-guarded**.
  - `GET /roads` → `[{road_network_id, sha256, source_path, bbox, node_count, edge_count}]`
  - `GET /roads/{road_network_id}/layers` → the Task 4 layers dict; 404 unknown.
- `create_app` gains keyword-only `roads_registry: RoadsRegistry | None = None` (default `RoadsRegistry(_REPO_ROOT / "data" / "imports")`).

- [ ] **Step 1: Failing tests** (append to `test_import_api.py`; reuse the Task 4 `write_pbf` helper by importing it: `from tests.imports.test_roads import write_pbf, EXTENT` — and pass `roads_registry=RoadsRegistry(tmp_path / "imports")` in `_app`, mirroring the other registries):

```python
def test_roads_import_list_and_layers(tmp_path: Path, dem: Path) -> None:
    pbf = tmp_path / "toy.osm.pbf"
    write_pbf(pbf)
    with TestClient(_app(tmp_path)) as client:
        terrain = client.post("/terrain/import", json={"path": str(dem)}).json()
        imported = client.post(
            "/roads/import",
            json={"path": str(pbf), "terrain_id": terrain["terrain_id"]},
        )
        assert imported.status_code == 200
        body = imported.json()
        assert body["road_network_id"].startswith("roads-")
        assert body["edge_count"] > 0

        assert client.get("/roads").json()[0]["road_network_id"] == body["road_network_id"]

        layers = client.get(f"/roads/{body['road_network_id']}/layers")
        assert layers.status_code == 200
        assert "roads" in layers.json()

        assert client.get("/roads/roads-unknown0000000/layers").status_code == 404
        unknown_terrain = client.post(
            "/roads/import", json={"path": str(pbf), "terrain_id": "terrain-nope"}
        )
        assert unknown_terrain.status_code == 404
        bad = client.post(
            "/roads/import",
            json={"path": str(tmp_path / "missing.pbf"), "terrain_id": terrain["terrain_id"]},
        )
        assert bad.status_code == 422
```

Also extend `test_path_taking_import_routes_refuse_non_loopback_clients` with a `POST /roads/import` call asserting 403. Note: the toy DEM extent (107.5–108.2 lon) does not overlap the toy PBF (107.0–107.2) — move the PBF's coordinates or build the DEM fixture at the PBF's extent so the clip keeps roads; simplest is a second small DEM fixture at `transform_from_bounds(107.0, -6.6, 107.2, -6.3, 50, 40)` used by this test.

- [ ] **Step 2: Verify failure**, **Step 3: implement routes** in `create_app` (before `/health`), following the terrain routes' shape:

```python
    @application.post(
        "/roads/import",
        summary="Import an OSM extract as the study road network",
        responses={200: {"description": "Road network record"},
                   404: {"description": "Terrain is not registered"},
                   422: {"description": "File is not a readable OSM extract with roads in the extent"}},
    )
    def roads_import(payload: RoadsImportRequest, request: Request) -> dict[str, Any]:
        _require_local_client(request)
        try:
            terrain = registry.get(payload.terrain_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            record = roads.imports(Path(payload.path), terrain.extent)
        except RoadsImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "road_network_id": record.road_network_id,
            "sha256": record.sha256,
            "node_count": record.node_count,
            "edge_count": record.edge_count,
            "bbox": list(record.bbox),
        }

    @application.get(
        "/roads",
        summary="List registered road networks",
        responses={200: {"description": "Registered road-network records"}},
    )
    def roads_list() -> list[dict[str, Any]]:
        return [
            {
                "road_network_id": r.road_network_id, "sha256": r.sha256,
                "source_path": r.source_path, "bbox": list(r.bbox),
                "node_count": r.node_count, "edge_count": r.edge_count,
            }
            for r in roads.list()
        ]

    @application.get(
        "/roads/{road_network_id}/layers",
        summary="Read simplified map-context layers for the basin view",
        responses={200: {"description": "Roads, coastline, and place layers"},
                   404: {"description": "Road network is not registered"}},
    )
    def roads_layers(road_network_id: str) -> dict[str, Any]:
        try:
            return roads.layers(road_network_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
```

With module-level `class RoadsImportRequest(BaseModel): path: str; terrain_id: str`, factory param `roads_registry: RoadsRegistry | None = None`, and `roads = roads_registry or RoadsRegistry(_REPO_ROOT / "data" / "imports")`. Imports: `from ..imports.roads import RoadsImportError, RoadsRegistry`.

- [ ] **Step 4: Contract** — add to `openapi.yaml` after `/reservoir/{model_id}` (summaries must match the decorators verbatim):

```yaml
  /roads/import:
    post:
      summary: Import an OSM extract as the study road network
      responses:
        '200': {description: Road network record}
        '404': {description: Terrain is not registered}
        '422': {description: File is not a readable OSM extract with roads in the extent}
  /roads:
    get:
      summary: List registered road networks
      responses:
        '200': {description: Registered road-network records}
  /roads/{road_network_id}/layers:
    get:
      summary: Read simplified map-context layers for the basin view
      parameters:
        - {in: path, name: road_network_id, required: true, schema: {type: string}}
      responses:
        '200': {description: Roads, coastline, and place layers}
        '404': {description: Road network is not registered}
```

- [ ] **Step 5: Verify** — `python -m pytest tests/imports tests/screening/test_api_contract.py -q`, then `python -m pytest tests -q` → PASS.
- [ ] **Step 6: Regen types + commit** — `cd frontend && npm run gen:types && cd ..`, `git add -A src/jatibarang_ccus/api specs tests/imports frontend/src/api/types.gen.ts && git commit -m "feat(api): road-network import, listing, and layer routes"`

---

### Task 6: Trucking rewire — legs, provenance, road_network_id (backend)

**Files:**
- Modify: `src/jatibarang_ccus/contracts.py` (`TruckingLeg` new; `TruckingSupplyResult` ~line 260; `SupplyComparisonRequest` ~line 293)
- Modify: `src/jatibarang_ccus/imports/roads.py` (add `compute_trucking_legs`)
- Modify: `src/jatibarang_ccus/infrastructure/supply.py` (`_trucking_result` ~line 13)
- Modify: `src/jatibarang_ccus/screening/schemas.py` (`InlineScreenRequest` ~line 151)
- Modify: `src/jatibarang_ccus/screening/orchestrator.py` (trucking call site ~line 1106; road-graph resolution near `resolve_terrain_path`)
- Modify: `specs/005-screening-api/contracts/openapi.yaml` (`InlineScreenRequest` schema properties)
- Test: `tests/screening/test_trucking_legs.py` (create)

**Interfaces:**
- Produces:
  - `contracts.TruckingLeg{candidate_id: str, distance_km: float (gt=0), annual_mass_tonnes: float (gt=0), route: list[tuple[float, float]] | None}`
  - `TruckingSupplyResult` gains `distance_provenance: str = "declared_distance"`, `legs: list[TruckingLeg] | None = None`; `SupplyComparisonRequest` gains the same two fields as passthrough inputs (`trucking_legs` named `trucking_legs`, provenance named `distance_provenance`).
  - `roads.compute_trucking_legs(sources: list[CO2Source], demands: list[PipelineWellDemand], graph: RoadGraph | None) -> tuple[float, str, list[TruckingLeg]]` returning (mass-weighted km, provenance, legs). `GREATCIRCLE_DETOUR_FACTOR = 1.4`.
  - `InlineScreenRequest.road_network_id: str | None = None`.
- Task 8 consumes `legs[].route` from the screen result (`plans[].trucking.supply.legs` — verify the exact key path with `grep -n "TruckingCounterfactual" src/jatibarang_ccus/screening/schemas.py`).

- [ ] **Step 1: Failing tests**

```python
# tests/screening/test_trucking_legs.py
from __future__ import annotations

from pathlib import Path

import pytest

from jatibarang_ccus.contracts import CO2Source, Coordinate, PipelineWellDemand
from jatibarang_ccus.imports.roads import (
    GREATCIRCLE_DETOUR_FACTOR,
    RoadsRegistry,
    compute_trucking_legs,
    haversine_km,
)
from tests.imports.test_roads import EXTENT, write_pbf


def _source(lat: float, lon: float) -> CO2Source:
    return CO2Source(
        id="S01", name="Source", location=Coordinate(latitude=lat, longitude=lon),
        capacity_tonnes_per_year=500_000.0, max_mass_flow_kg_s=600.0,
        outlet_pressure_bar=120.0, outlet_temperature_c=27.0, co2_purity=0.98,
    )


def _demand(candidate_id: str, lat: float, lon: float, mass: float) -> PipelineWellDemand:
    return PipelineWellDemand(
        candidate_id=candidate_id, location=Coordinate(latitude=lat, longitude=lon),
        annual_demand_tonnes=mass, peak_mass_flow_kg_s=25.0,
        pre_logistics_value_usd=1.0,
    )


def test_fallback_uses_massweighted_greatcircle_detour() -> None:
    source = _source(-6.50, 107.02)
    near = _demand("W01", -6.50, 107.06, 100_000.0)
    far = _demand("W02", -6.50, 107.18, 300_000.0)
    weighted, provenance, legs = compute_trucking_legs([source], [near, far], None)
    assert provenance == "greatcircle_detour_estimate"
    d_near = haversine_km(-6.50, 107.02, -6.50, 107.06) * GREATCIRCLE_DETOUR_FACTOR
    d_far = haversine_km(-6.50, 107.02, -6.50, 107.18) * GREATCIRCLE_DETOUR_FACTOR
    assert legs[0].distance_km == pytest.approx(d_near)
    assert legs[1].distance_km == pytest.approx(d_far)
    assert weighted == pytest.approx((d_near * 100_000 + d_far * 300_000) / 400_000)
    assert legs[0].route is None


def test_road_mode_routes_over_the_network(tmp_path: Path) -> None:
    pbf = tmp_path / "toy.osm.pbf"
    write_pbf(pbf)
    registry = RoadsRegistry(tmp_path / "imports")
    record = registry.imports(pbf, EXTENT)
    graph = registry.graph(record.road_network_id)
    source = _source(-6.50, 107.02)
    demand = _demand("W01", -6.50, 107.18, 200_000.0)
    weighted, provenance, legs = compute_trucking_legs([source], [demand], graph)
    assert provenance == f"osm_road_network:{record.road_network_id}"
    direct = haversine_km(-6.50, 107.02, -6.50, 107.18)
    assert legs[0].distance_km > direct * 1.5
    assert legs[0].route and len(legs[0].route) >= 3
    assert weighted == pytest.approx(legs[0].distance_km)
```

- [ ] **Step 2: Verify failure** — `python -m pytest tests/screening/test_trucking_legs.py -q` → FAIL (imports missing).

- [ ] **Step 3: Contracts.** In `contracts.py`, above `TruckingSupplyResult`:

```python
class TruckingLeg(BaseModel):
    candidate_id: str
    distance_km: float = Field(gt=0)
    annual_mass_tonnes: float = Field(gt=0)
    route: list[tuple[float, float]] | None = None
```

Add to `TruckingSupplyResult`: `distance_provenance: str = "declared_distance"` and `legs: list[TruckingLeg] | None = None`. Add to `SupplyComparisonRequest`: `trucking_legs: list[TruckingLeg] | None = None` and `distance_provenance: str = "declared_distance"`.

- [ ] **Step 4: `compute_trucking_legs`** in `roads.py` (imports `CO2Source`, `PipelineWellDemand`, `TruckingLeg` from `..contracts`):

```python
GREATCIRCLE_DETOUR_FACTOR = 1.4
MIN_LEG_KM = 0.1


def compute_trucking_legs(
    sources: list["CO2Source"],
    demands: list["PipelineWellDemand"],
    graph: RoadGraph | None,
) -> tuple[float, str, list["TruckingLeg"]]:
    """Per-candidate trucking legs from each well's nearest source.

    With a road graph: snap both endpoints, shortest path by length, plus the
    straight connector km from each endpoint to its snap node. Without one:
    great-circle x detour factor (spec 2026-07-18 §6)."""
    legs: list[TruckingLeg] = []
    provenance = (
        f"osm_road_network:{graph.road_network_id}"
        if graph is not None
        else "greatcircle_detour_estimate"
    )
    for demand in demands:
        d_lat = demand.location.latitude
        d_lon = demand.location.longitude
        source = min(
            sources,
            key=lambda s: haversine_km(
                s.location.latitude, s.location.longitude, d_lat, d_lon
            ),
        )
        s_lat, s_lon = source.location.latitude, source.location.longitude
        route: list[tuple[float, float]] | None = None
        if graph is None:
            distance = haversine_km(s_lat, s_lon, d_lat, d_lon) * GREATCIRCLE_DETOUR_FACTOR
        else:
            s_idx, s_conn = graph.snap(s_lat, s_lon)
            d_idx, d_conn = graph.snap(d_lat, d_lon)
            path_km, path = graph.shortest_path_km(s_idx, d_idx)
            distance = path_km + s_conn + d_conn
            route = [(s_lat, s_lon), *path, (d_lat, d_lon)]
        legs.append(
            TruckingLeg(
                candidate_id=demand.candidate_id,
                distance_km=max(distance, MIN_LEG_KM),
                annual_mass_tonnes=demand.annual_demand_tonnes,
                route=route,
            )
        )
    total_mass = sum(leg.annual_mass_tonnes for leg in legs)
    weighted = (
        sum(leg.distance_km * leg.annual_mass_tonnes for leg in legs) / total_mass
        if total_mass
        else MIN_LEG_KM
    )
    return weighted, provenance, legs
```

- [ ] **Step 5: `supply.py`.** In `_trucking_result`, add to the `TruckingSupplyResult(...)` construction: `distance_provenance=request.distance_provenance, legs=request.trucking_legs,`.

- [ ] **Step 6: Request schema + orchestrator.** In `screening/schemas.py` add `road_network_id: str | None = None` after `terrain_id`. In `orchestrator.py`:
  1. Beside `resolve_terrain_path`, add:

```python
def resolve_road_graph(road_network_id: str | None):
    """Registry-backed road graph for trucking; None means the great-circle
    fallback. Unknown ids fail loudly like unknown terrain ids."""
    if not road_network_id:
        return None
    from ..imports.roads import RoadsRegistry

    try:
        return RoadsRegistry(_REPO_ROOT / "data" / "imports").graph(road_network_id)
    except KeyError as exc:
        raise ValueError(f"unknown road_network_id: {road_network_id}") from exc
```

(Adapt `_REPO_ROOT` to the constant `resolve_terrain_path` already uses.)
  2. Where the run resolves the terrain (find with `grep -n "resolve_terrain_path" src/jatibarang_ccus/screening/orchestrator.py`), also resolve once per run: `road_graph = resolve_road_graph(getattr(request, "road_network_id", None))`, and thread it to the trucking call site.
  3. Replace the call site (~line 1106):

```python
                selected_demands = [item for item in demands if item.candidate_id in selected]
                weighted_km, distance_provenance, trucking_legs = compute_trucking_legs(
                    design_request.sources, selected_demands, road_graph
                )
                trucking_supply = self.services.trucking_evaluator(
                    SupplyComparisonRequest(
                        pipeline_request=selected_request,
                        trucking_distance_km=weighted_km,
                        trucking_legs=trucking_legs,
                        distance_provenance=distance_provenance,
                    ),
                    annual_mass_tonnes=annual_mass,
                )
```

Import `compute_trucking_legs` from `..imports.roads`. The existing `annual_mass` / `selected_request` lines stay.

- [ ] **Step 7: Contract file.** In `openapi.yaml`, add to the `InlineScreenRequest` schema `properties`: `road_network_id: {type: [string, 'null'], default: null}`.

- [ ] **Step 8: Full verification.** `python -m pytest tests/screening/test_trucking_legs.py -q` → PASS. Then `python -m pytest tests -q`. Any pre-existing screening/infrastructure test that asserted trucking numbers derived from the 70 km constant now fails — for each, compute the expected haversine × 1.4 value from that test's source/well coordinates by hand, confirm the new output matches it, then update the assertion. `tests/infrastructure` facility-validation tests that pass `trucking_distance_km=70.0` explicitly are untouched (they construct the request directly).
- [ ] **Step 9: Regen types + commit** — `cd frontend && npm run gen:types && cd ..`, `git add -A src tests specs frontend/src/api/types.gen.ts && git commit -m "feat(screening): road-network trucking legs replace the fixed 70 km distance"`

---

### Task 7: Roads study wiring (frontend)

**Files:**
- Modify: `frontend/src/api/client.ts` (`importRoads`, `listRoadNetworks`, `getRoadLayers`)
- Modify: `frontend/src/state/field.store.ts` (`RoadsRef`, `roads`, `roadLayers`, `setRoads`; hydrate)
- Modify: `frontend/src/memo/studyMemo.ts` (`FieldSetupMemo.roads?: RoadsRef | null`)
- Modify: `frontend/src/memo/import.ts` (relink road layers on open)
- Modify: `frontend/src/run/useWorkbench.ts` (`currentFieldSetup` includes `roads`)
- Modify: `frontend/src/compose/studyRequest.ts` (`road_network_id` in built request)
- Modify: `frontend/src/chrome/NewStudyDialog.tsx` (optional "Road network (.osm.pbf)" field)
- Test: `frontend/src/api/importClient.test.ts`, `frontend/src/state/field.store.test.ts`, `frontend/src/compose/studyRequest.test.ts` (append to each)

**Interfaces:**
- Consumes: Task 5 routes.
- Produces (Task 8 consumes `roadLayers` from the field store):

```typescript
// client.ts
export interface RoadsImportResponse { road_network_id: string; sha256: string;
  node_count: number; edge_count: number; bbox: [number, number, number, number]; }
export function importRoads(path: string, terrainId: string): Promise<RoadsImportResponse>;
export interface RoadLayers {
  roads: Array<{ class: "major" | "minor"; points: [number, number][] }>;
  coastline: [number, number][][];
  places: Array<{ name: string; lat: number; lon: number; kind: string }>;
}
export function getRoadLayers(roadNetworkId: string): Promise<RoadLayers>;
// field.store.ts
export interface RoadsRef { road_network_id: string; sha256: string; source_path: string; }
// state additions: roads: RoadsRef | null; roadLayers: RoadLayers | null;
// action: setRoads(roads: RoadsRef | null, layers: RoadLayers | null): void;
```

- [ ] **Step 1: Failing tests.**
  - `importClient.test.ts`: `importRoads("C:/java.osm.pbf", "terrain-x")` POSTs `/roads/import` with body `{path, terrain_id}`; `getRoadLayers("roads-a")` GETs `/roads/roads-a/layers`.
  - `field.store.test.ts`: `setRoads(ref, layers)` stores both; `reset()` clears both; `hydrate` with a memo whose `roads` is set restores the ref with `roadLayers: null`; `hydrate` with a memo lacking `roads` leaves it null.
  - `studyRequest.test.ts`: built request carries `road_network_id: "roads-a"` when `field.roads` is set and `road_network_id: null` otherwise.

- [ ] **Step 2: Verify failures**, **Step 3: implement**:
  - `client.ts` functions per the interfaces (match `importReservoir`'s helper pattern).
  - `field.store.ts`: add the two state fields to `EMPTY_STATE` (`roads: null, roadLayers: null`), `setRoads: (roads, layers) => set({ roads, roadLayers: layers })`, and in `hydrate`: `roads: setup.roads ? { ...setup.roads } : null, roadLayers: null,`.
  - `studyMemo.ts`: `FieldSetupMemo` gains `roads?: RoadsRef | null;` (import the type from the field store). `useWorkbench.ts` `currentFieldSetup()` adds `roads: state.roads ? { ...state.roads } : null,`.
  - `studyRequest.ts` `buildStudyRequest`: include `road_network_id: opts.field.roads?.road_network_id ?? null` in the returned request.
  - `memo/import.ts`: when `memo.field_setup.roads` exists, after `field.hydrate(...)`: `getRoadLayers(memo.field_setup.roads.road_network_id)` → race-guard (`useFieldStore.getState().roads?.road_network_id` still matches) → `useFieldStore.setState({ roadLayers: layers })`; on failure push banner `{ id: "roads-relink", severity: "info", message: "The road network for this study could not be found; trucking falls back to the great-circle estimate until it is re-imported." }`.
  - `NewStudyDialog.tsx`: after the launch-pad bank field, an optional path input labeled exactly "Road network (.osm.pbf)" with an Import button following the dialog's existing terrain-import pending/error pattern; on success show "`{node_count}` nodes · `{edge_count}` edges"; on Create call `useFieldStore.getState().setRoads(ref, layers)` (fetch layers right after import) before the existing `setup(...)` — note `setup()` resets state, so call `setRoads` **after** `setup(...)` instead; verify order by reading the dialog's Create handler.

- [ ] **Step 4: Verify** — `npm test -- --run && npx tsc -b` → PASS.
- [ ] **Step 5: Commit** — `git add -A frontend && git commit -m "feat(frontend): road-network import wired through study, memo, and request"`

---

### Task 8: Basin map layers + road-following trucking display (frontend)

**Files:**
- Modify: `frontend/src/state/workspace.store.ts` (`LayerVisibility` + defaults)
- Create: `frontend/src/viewport/MapContextLayers.tsx`
- Modify: `frontend/src/viewport/Viewport3D.tsx` (render `MapContextLayers` in the basin branch; `LAYER_OPTIONS` at ~line 921)
- Modify: `frontend/src/viewport/scene.ts` (trucking legs override the straight path, ~lines 113–130)
- Test: `frontend/src/viewport/scene.test.ts` or the existing scene-adjacent test file (locate with `Glob frontend/src/viewport/*.test.ts`), append

**Interfaces:**
- Consumes: `useFieldStore` `roadLayers` (Task 7); screen-result trucking legs (Task 6; confirm the key path in `frontend/src/api/types.ts` with `grep -n "trucking" frontend/src/api/types.ts` — expected `plan.trucking.supply.legs`).
- Produces: `MapContextLayers` props `{ projector: TerrainProjector; exaggeration: number; layers: LayerVisibility }` (reads `roadLayers` from the store itself).

- [ ] **Step 1: Failing scene test** — a plan fixture whose `trucking.supply.legs` carries `{candidate_id: "W02", route: [[-6.5, 107.0], [-6.4, 107.1], [-6.5, 107.2]]}` produces a trucking `SceneRoute` with a 3-point path; a plan without legs keeps the 2-point straight path.

- [ ] **Step 2: Implement scene override.** In `scene.ts`'s trucking branch (the `networkAccepted === false` arm at ~line 113), before the loop: `const legs = plan.trucking?.supply?.legs ?? null;` and inside:

```typescript
const leg = legs?.find((item) => item.candidate_id === wellId) ?? null;
routes.push({
  id: `truck:${wellId}`,
  mode: "trucking",
  path: leg?.route
    ? leg.route.map(([latitude, longitude]) => ({ latitude, longitude }))
    : [source.location, to],
});
```

(Adjust the property path to whatever `types.gen.ts` produced in Task 6.)

- [ ] **Step 3: Layer toggles.** `LayerVisibility` gains `roads: boolean; coastline: boolean; places: boolean;` defaulting `true`; add to `LAYER_OPTIONS` in Viewport3D: `["roads", "Roads"], ["coastline", "Coastline"], ["places", "Place labels"]`.

- [ ] **Step 4: Implement `MapContextLayers`.** Draped polylines exactly like `SceneObjects` routes (subdivide via the existing `samplePath`-style approach and `projector.heightOf(projector.elevationAt(c), exaggeration)` + small lift):
  - roads: major `color "#9aa0a8", lineWidth 1.6`; minor `color "#5a616b", lineWidth 1.0`, lift 0.02;
  - coastline: `color "#4e86a0", lineWidth 1.4`, lift 0.02;
  - places: `Html` labels (`className "scene-label"`) at lift 0.28, rendered only when `layers.places && layers.labels` is irrelevant — gate on `layers.places` alone.
  - Cap rendering effort: skip minor roads when a line has < 2 points; memoize the converted vectors with `useMemo` keyed on `[roadLayers, projector, exaggeration]`.
  Render from Viewport3D's `SceneContent` for the **basin** level only, behind `layers.roads || layers.coastline || layers.places`, reading `roadLayers` from `useFieldStore`.

- [ ] **Step 5: Verify** — `npm test -- --run && npx tsc -b` → PASS. Manual QA: import the Java PBF, see roads/coastline/places on the basin; run a screen; the trucking dashes follow roads.
- [ ] **Step 6: Commit** — `git add -A frontend && git commit -m "feat(viewport): basin map-context layers and road-following trucking routes"`

---

### Task 9: Globe assets + earth scene level (frontend)

**Files:**
- Create: `tools/earth/simplify_coastline.py`, `frontend/public/earth/README.md`, `frontend/public/earth/ne_50m_coastline.json`, `frontend/public/earth/blue_marble_2048.jpg` (downloaded)
- Create: `frontend/src/viewport/EarthGlobe.tsx`
- Modify: `frontend/src/state/field.store.ts` (`SceneLevel` + `enterBasin`/`exitBasin`; boot level `"earth"`)
- Modify: `frontend/src/state/ui.store.ts` (`newStudyTerrainId: string | null` + setter)
- Modify: `frontend/src/chrome/NewStudyDialog.tsx` (preselect terrain from `newStudyTerrainId`)
- Modify: `frontend/src/viewport/Viewport3D.tsx` (earth branch, breadcrumb, Esc)
- Test: `frontend/src/viewport/earthGlobe.test.ts`, `frontend/src/state/field.store.test.ts` (append)

**Interfaces:**
- Produces: `latLonToVec3(lat: number, lon: number, radius: number): [number, number, number]` exported from `EarthGlobe.tsx`; `EarthGlobe` props `{ terrains: RegisteredTerrain[]; activeTerrainId: string | null; onDive: (terrainId: string) => void }`. Field store: `SceneLevel = "earth" | "basin" | "field"`; `enterBasin(): void` (no-op without terrain), `exitBasin(): void`; `EMPTY_STATE.level = "earth"`.

- [ ] **Step 1: Fetch + commit assets.**

```bash
mkdir -p frontend/public/earth
curl -L -o "$TMPDIR/ne_coast.geojson" https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_50m_coastline.geojson
python tools/earth/simplify_coastline.py "$TMPDIR/ne_coast.geojson" frontend/public/earth/ne_50m_coastline.json
curl -L -o frontend/public/earth/blue_marble_2048.jpg https://eoimages.gsfc.nasa.gov/images/imagerecords/57000/57752/land_shallow_topo_2048.jpg
```

`tools/earth/simplify_coastline.py` (write first):

```python
"""Simplify the Natural Earth coastline GeoJSON to a compact line bundle."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from shapely.geometry import shape


def main(source: str, target: str) -> None:
    data = json.loads(Path(source).read_text(encoding="utf-8"))
    lines: list[list[list[float]]] = []
    for feature in data["features"]:
        geometry = shape(feature["geometry"]).simplify(0.1)
        parts = getattr(geometry, "geoms", [geometry])
        for part in parts:
            coords = [[round(x, 3), round(y, 3)] for x, y in part.coords]
            if len(coords) >= 2:
                lines.append(coords)
    Path(target).write_text(json.dumps({"lines": lines}), encoding="utf-8")
    print(f"{len(lines)} lines, {sum(len(l) for l in lines)} points")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
```

Output format: `{"lines": [[[lon, lat], ...], ...]}`, target ≤ ~500 KB (raise the simplify tolerance if larger). Write `frontend/public/earth/README.md` recording: Natural Earth (public domain) and NASA Visible Earth `land_shallow_topo_2048` (public domain), download dates, and the simplify tolerance. If a download fails, commit the README with a note and continue — the globe must handle both assets being absent (Step 4).

- [ ] **Step 2: Failing tests.**
  - `earthGlobe.test.ts`: `latLonToVec3(90, 0, 10)` ≈ `[0, 10, 0]` (north pole up); `latLonToVec3(0, 0, 10)` has `y ≈ 0` and length 10; `latLonToVec3(0, 90, 10)` differs from `latLonToVec3(0, 0, 10)` by a 90° rotation about Y (dot product ≈ 0).
  - `field.store.test.ts` additions: fresh store boots at `"earth"`; `enterBasin()` without terrain is a no-op; after `setup(...)` level is `"basin"`; `exitBasin()` → `"earth"`; `enterBasin()` with terrain → `"basin"`; `reset()` returns to `"earth"`.

- [ ] **Step 3: Store changes.** `SceneLevel = "earth" | "basin" | "field"`; `EMPTY_STATE.level: "earth" as const`; actions:

```typescript
enterBasin: () => {
  if (get().terrain) set({ level: "basin" });
},
exitBasin: () => set({ level: "earth" }),
```

`setup`/`hydrate` already set `level: "basin"` — keep. `ui.store.ts`: add `newStudyTerrainId: string | null` (default null) + `setNewStudyTerrainId(id: string | null)`; `NewStudyDialog` reads it once on open to preselect the terrain dropdown and clears it on close (find the dialog's open effect at `NewStudyDialog.tsx:202` where `listTerrains()` already loads the dropdown).

- [ ] **Step 4: `EarthGlobe.tsx`.**

```tsx
const GLOBE_RADIUS = 10;

export function latLonToVec3(lat: number, lon: number, radius: number): [number, number, number] {
  const phi = (90 - lat) * DEG2RAD;
  const theta = (lon + 180) * DEG2RAD;
  return [
    -radius * Math.sin(phi) * Math.cos(theta),
    radius * Math.cos(phi),
    radius * Math.sin(phi) * Math.sin(theta),
  ];
}
```

(This matches three.js SphereGeometry equirectangular UV orientation, so the Blue Marble texture lines up with coastlines/footprints.) Component behavior:
  - Sphere: `<mesh><sphereGeometry args={[GLOBE_RADIUS, 64, 48]} /><meshStandardMaterial map={texture ?? undefined} color={texture ? "#ffffff" : "#123a52"} roughness={0.9} /></mesh>`; texture loaded with `new THREE.TextureLoader().load("/earth/blue_marble_2048.jpg", onLoad, undefined, () => setTexture(null))` in a `useEffect` (set `texture.colorSpace = THREE.SRGBColorSpace` on load).
  - Coastline: fetch `/earth/ne_50m_coastline.json` once (`useEffect`, ignore failure), draw each line as drei `Line` at radius `GLOBE_RADIUS * 1.002`, `color "#9fd0e0"`, `lineWidth 0.6`.
  - Graticule: meridians every 30° and parallels every 15° as faint lines (`color "#2c4a58"`, `lineWidth 0.4`, radius `* 1.001`).
  - Footprints: per terrain, subdivide the extent rectangle (12 points per edge), map through `latLonToVec3(..., GLOBE_RADIUS * 1.004)`, closed `Line` — active: `color "#e8c268", lineWidth 2.4` plus an `Html` label with the terrain id's short form; inactive: `color "#7d8894", lineWidth 1.4`. `onDoubleClick` (on an invisible sphere-quad mesh over the footprint or the Line itself) → `onDive(terrain_id)`.

- [ ] **Step 5: Viewport3D earth branch.** Replace the current `if (!terrain)` empty-state return: compute `const level = useFieldStore((s) => s.level);` and when `level === "earth"` render a dedicated Canvas (own lighting: ambient 0.5 + one directional; `OrbitControls` with `target={[0,0,0]} minDistance={13} maxDistance={40}`, camera `position: [0, 8, 26]`), containing `<EarthGlobe terrains={terrains} activeTerrainId={terrain?.terrain_id ?? null} onDive={handleDive} />`:
  - `terrains` from `listTerrains()` fetched in a `useEffect` on mount and whenever `terrain` changes (failure → empty list).
  - `handleDive(id)`: if `terrain?.terrain_id === id` → `useFieldStore.getState().enterBasin()`; else if no study terrain → `useUiStore.getState().setNewStudyTerrainId(id)` then open the New Study modal (locate the modal-open command with `grep -n "new-study" frontend/src/chrome/commands.ts frontend/src/state/ui.store.ts` and reuse it); else no-op.
  - Overlay hint card (existing `viewport-empty-hint` styles, absolutely positioned) when `terrains.length === 0 && !terrain`: same copy as today ("No study loaded / New Study — Ctrl+N · Open Study — Ctrl+O").
  - Mode tag: `3D · earth`.
  - Basin branch gains a "◂ Earth" breadcrumb button (same `field-breadcrumb` class, shown when `level === "basin"`, `onClick={() => useFieldStore.getState().exitBasin()}`) — keep the existing "Field ▸" button beside it; and extend the `exitOnEscape` handler: when `level === "basin"` and no modal/context menu/source editor and the selection store is empty (`useSelectionStore.getState().selection.kind === "none"` — read `selection.store.ts` for the actual empty value), Esc calls `exitBasin()`.
  - The `if (!projector)` "Terrain overview unavailable" branch stays, but only for `level !== "earth"`.

- [ ] **Step 6: Verify** — `npm test -- --run && npx tsc -b && npm run build` → PASS. Manual QA at 1920×1080: boot → globe with texture, coastlines, graticule; register a terrain → footprint appears; double-click → New Study preselected; create study → basin; "◂ Earth"/Esc → globe with highlighted footprint; double-click it → basin again; no network requests other than same-origin.
- [ ] **Step 7: Commit** — `git add -A frontend tools/earth && git commit -m "feat(viewport): offline earth globe boot level with terrain footprints"`

---

### Task 10: Final verification and docs

**Files:**
- Create: `data/imports/README.md`
- Modify: `frontend/src/layout/Inspector.tsx` (trucking provenance line)

**Steps:**

- [ ] **Step 1: Inspector line.** Where the Inspector shows trucking/supply details for a selected route or plan (locate with `grep -n "trucking" frontend/src/layout/Inspector.tsx`), when the active result's trucking `distance_provenance === "greatcircle_detour_estimate"`, render exactly: "Estimated from great-circle distance × 1.4 — import a road network for road-accurate routing." When it starts with `osm_road_network:`, render "Routed over the imported road network."
- [ ] **Step 2: `data/imports/README.md`** — document the hash-addressed layout (`<sha16>/<original file>`, `terrain_registry.json`, `roads_registry.json`, graph/layer caches), that the directory is machine-local state ignored by git, and that memos reference artifacts here by id + sha.
- [ ] **Step 3: Full verification.**
  - `python -m pytest tests -q` → PASS
  - `cd frontend && npm test -- --run && npx tsc -b && npm run build` → PASS
- [ ] **Step 4: Manual QA sweep per spec §10** — boot globe; dive; import Java PBF (expect ~a minute, then instant on re-import); map layers; screen with roads → trucking follows roads, provenance `osm_road_network:*`; screen without roads → estimate provenance + inspector line; reopen a saved memo → screening works with no re-import; compass tracks orbit in basin and field.
- [ ] **Step 5: Commit** — `git add -A && git commit -m "docs: import store notes and trucking provenance display"`

---

## Execution completion record (2026-07-19)

- Tasks 1-3: camera-backed compass, reservoir reload route, memo-v4 W01-W20 relink,
  SHA checks, and restored spatial playback are complete.
- Tasks 4-6: official Java PBF imported; cache schema 4 compact CSR replaces the
  memory-prohibitive NetworkX materialization; route API, exact per-candidate legs,
  estimates, and provenance are complete. The fixed production 70 km constant is
  absent.
- Tasks 7-9: road field wiring, context layers, routed trucking previews, offline
  Earth assets, footprints, and earth/basin/field navigation are complete.
- Task 10: import-store documentation, browser QA, 187 backend tests, 176 frontend
  tests, TypeScript, production build, and Feature 007 bundle build/verification pass.
- Real QA evidence: memo v4 with 20 distinct model IDs and 20 distinct banks; ten
  archived plume/reservoir pairs; 20 road-preview legs with 1,658-2,909 points in the
  saved result; W01/W02 playback; and a five-entry MRST export with
  `development_selection_claimed=false`.
- The full 200/3,240 paper banks and scientific A/B/C results remain explicitly
  `NOT_RUN`/blocked. The completed 20-run bank is workflow evidence only.
- No task-by-task commits were created because the repository already contained
  unrelated user changes and no commit was requested.

## Self-Review Notes

- **Spec coverage:** §4 scene hierarchy → Task 9; §5 roads import/registry/routes → Tasks 4–5; §6 screening contract + trucking → Task 6; §7 study wiring + layers → Tasks 7–8; §8 bug fixes → Tasks 1–3; §9 assets/licensing → Task 9 Step 1; §10 testing → per-task + Task 10; §11 out-of-scope respected (no tiles, no travel-time weights).
- **Deliberate judgment points:** exact pyosmium writer kwargs (Task 4 note), the result-side key path for trucking legs (Task 8 Step 2 instructs verifying against `types.gen.ts`), the New Study modal-open command (Task 9 Step 5), Inspector integration point (Task 10 Step 1). Each is a bounded look-and-match instruction with a named grep.
- **Type consistency check:** `RoadsRef`/`RoadLayers`/`setRoads`/`roadLayers` names match across Tasks 7–8; `RoadsRegistry.imports/list/get/layers/graph`, `RoadGraph.snap/shortest_path_km`, `compute_trucking_legs`, `TruckingLeg`, `road_network_id` match across Tasks 4–8; `enterBasin`/`exitBasin`/`SceneLevel "earth"` match Tasks 9 and the store tests; `getReservoir` matches Tasks 2–3.
