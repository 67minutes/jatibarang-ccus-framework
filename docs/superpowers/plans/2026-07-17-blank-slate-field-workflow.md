# Blank-Slate Field Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the Jatibarang-preloaded workbench with a blank-slate flow: import terrain + one reservoir model + launch pads, place a named field on the earth, add wells/sources by right-click, enter the field, and screen only launch-pad-covered schedules.

**Architecture:** Backend gains a hash-keyed import layer (terrain registry + windowing, MRST reservoir + launch-pad bank parsing) exposed as three small FastAPI routes; the existing `/screen` contract is reused with `terrain_id` relaxed from a pinned literal to a registry-validated string. Frontend gains one new `field.store` owning study setup (terrain ref, field placement, wells, sources, imports), a two-level scene (basin ⇄ field), and a request builder that compiles the study into the existing `InlineScreenRequest`.

**Tech Stack:** FastAPI + pydantic v2 + rasterio + h5py + numpy (backend); React + zustand + react-three-fiber/drei + vitest (frontend); pytest.

**Spec:** `docs/superpowers/specs/2026-07-17-blank-slate-field-workflow-design.md`

## Global Constraints

- UI copy: "reservoir model", "launch pads", "launch-pad bank" — the words "case", "realization", "seed" never appear in UI text (spec §3).
- The app never invents launch pads; uncovered schedules are disabled with the exact copy: "no launch pad for this schedule — import a bank or run MRST offline" (spec §9).
- Import endpoints take **local file paths in JSON bodies** (browser file inputs cannot supply paths; this is a local single-user tool — path text fields in dialogs, defaults pointing at `data/`). No multipart, no new Python deps.
- Imported artifacts live under `data/imports/<sha256-prefix-16>/`; memos reference by id + sha and never embed payloads (spec §6/§10).
- Memo compatibility: current `STUDY_MEMO_VERSION` is 2; this feature bumps to 3. Version-2 memos still open read-only with a notice (spec §10 — the spec's "memo v2" is implementation version 3).
- The well inspector line, verbatim: "Reservoir response assumes the local geology at this site matches the study's reservoir model." (spec §7)
- Work on branch `008-blank-slate-workbench`; commit after every task. Frontend verification per task: `npm test -- --run` and `npx tsc -b` from `frontend/`. Backend: `python -m pytest <test file> -q` from repo root.
- Existing behavior that must keep passing: full `python -m pytest tests -q` and the OpenAPI contract test (`tests/screening/test_api_contract.py`) after every backend task.

---

### Task 1: Shared MRST reservoir loader (backend)

Extract the `.mat` parsing that `surrogate/validation.py::load_validation_case` does into a reusable import module returning JSON-safe payloads, without changing validation behavior.

**Files:**
- Create: `src/jatibarang_ccus/imports/__init__.py` (empty)
- Create: `src/jatibarang_ccus/imports/mrst.py`
- Modify: `src/jatibarang_ccus/surrogate/validation.py` (delegate to the new loader)
- Test: `tests/imports/test_mrst_loader.py` (create `tests/imports/__init__.py` empty)

**Interfaces:**
- Consumes: `GeologyInput`, `ReservoirState`, `SeedHistory`, `OperatingSchedule`, `schedule_fingerprint` from `jatibarang_ccus.surrogate.schemas` / `.preprocessing` (existing).
- Produces: `load_mrst_reservoir(path: Path) -> MrstReservoirImport` where `MrstReservoirImport` is a dataclass with fields `geology: GeologyInput`, `seed: SeedHistory`, `schedule: OperatingSchedule`, `well_ij: tuple[int, int]`, `completion_ij: list[tuple[int, int]]`, `targets: dict[str, np.ndarray]`, `sha256: str`. Tasks 3 and 4 rely on these exact names.

- [ ] **Step 1: Branch**

```bash
git checkout -b 008-blank-slate-workbench
```

- [ ] **Step 2: Write the failing test**

```python
# tests/imports/test_mrst_loader.py
from __future__ import annotations

from pathlib import Path

import pytest

from jatibarang_ccus.imports.mrst import MrstImportError, load_mrst_reservoir

CASE = Path("data/validation_cases/case_0016.mat")


def test_loads_case_0016_with_typed_payloads() -> None:
    imported = load_mrst_reservoir(CASE)
    geology = imported.geology
    assert geology.permeability_md.shape == (64, 64)
    assert geology.length_x_m == 900.0 and geology.length_y_m == 600.0
    assert imported.schedule.cycles in (3, 4)
    assert len(imported.seed.frames) == 8
    assert imported.seed.schedule_fingerprint
    assert imported.seed.source_class == "mrst_ground_truth"
    assert 0 <= imported.well_ij[0] < 64 and 0 <= imported.well_ij[1] < 64
    assert len(imported.sha256) == 64


def test_rejects_non_mat_file(tmp_path: Path) -> None:
    bogus = tmp_path / "model.mat"
    bogus.write_bytes(b"not an hdf5 file")
    with pytest.raises(MrstImportError):
        load_mrst_reservoir(bogus)
```

- [ ] **Step 3: Run to verify it fails**

Run: `python -m pytest tests/imports/test_mrst_loader.py -q`
Expected: FAIL — `ModuleNotFoundError: jatibarang_ccus.imports`

- [ ] **Step 4: Implement the loader**

Move the body of `load_validation_case` (validation.py lines 36–105) into the new module, keeping the exact array/param handling, and add hashing + error wrapping:

```python
# src/jatibarang_ccus/imports/mrst.py
"""MRST reservoir-model import: one .mat realization -> typed payloads.

One export = one single-well sector simulation. It supplies the geology, the
native operating schedule, and that schedule's eight-frame launch pad. It
carries no georeference and no additional wells (spec §3, §7).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import h5py
import numpy as np

from ..surrogate.preprocessing import schedule_fingerprint
from ..surrogate.schemas import (
    GeologyInput,
    Grid2D,
    OperatingSchedule,
    ReservoirState,
    SeedHistory,
)

SECONDS_PER_DAY = 86400.0

ARRAY_KEYS = (
    "pressure", "gas_sat", "z_co2", "oil_sat", "perm_map", "poro_map",
    "structure_map", "fracture_proxy_map", "barrier_map", "facies_map",
    "well_mask", "completion_mask",
)


class MrstImportError(ValueError):
    """The file is not a readable MRST reservoir export."""


@dataclass(frozen=True)
class MrstReservoirImport:
    geology: GeologyInput
    seed: SeedHistory
    schedule: OperatingSchedule
    well_ij: tuple[int, int]
    completion_ij: list[tuple[int, int]]
    targets: dict[str, np.ndarray]
    sha256: str


def _grid(values: np.ndarray) -> Grid2D:
    return Grid2D.from_array(np.asarray(values, dtype=np.float32))


def load_mrst_reservoir(path: Path) -> MrstReservoirImport:
    path = Path(path)
    if not path.exists():
        raise MrstImportError(f"reservoir model file is missing: {path}")
    digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    try:
        with h5py.File(path, "r") as handle:
            params = {
                key: float(np.asarray(handle["params"][key]).reshape(-1)[0])
                for key in handle["params"].keys()
            }
            arrays = {
                key: np.asarray(handle[key], dtype=np.float32) for key in ARRAY_KEYS
            }
            dt = np.asarray(handle["dt_days"], dtype=np.float32).reshape(-1)
            stages = np.rint(np.asarray(handle["stage_labels"])).astype(np.int64).reshape(-1)
            oil_rate = np.asarray(handle["well_oil_rate"], dtype=np.float32).reshape(-1)
            gas_rate = np.asarray(handle["well_gas_rate"], dtype=np.float32).reshape(-1)
            well_ij_raw = np.rint(np.asarray(handle["well_ij"])).astype(int).reshape(-1)
            completion_raw = np.rint(np.asarray(handle["completion_ij"])).astype(int)
    except (OSError, KeyError) as exc:
        raise MrstImportError(f"not a readable MRST export: {path.name}: {exc}") from exc

    geology = GeologyInput(
        permeability_md=_grid(np.power(10.0, arrays["perm_map"])),
        porosity_fraction=_grid(arrays["poro_map"]),
        structure_m=_grid(arrays["structure_map"]),
        fracture_proxy=_grid(arrays["fracture_proxy_map"]),
        barrier=_grid(arrays["barrier_map"]),
        facies=_grid(arrays["facies_map"]),
        well_mask=_grid(arrays["well_mask"]),
        completion_mask=_grid(arrays["completion_mask"]),
        anisotropy_ratio=params["anisotropy_ratio"],
        reservoir_temperature_c=91.0,
        length_x_m=900.0,
        length_y_m=600.0,
        thickness_m=6.0,
    )
    schedule = OperatingSchedule(
        injection_rate_m3_day=params["inj_rate_surf"],
        injection_duration_days=params["t_inj_days"],
        soak_duration_days=params["t_soak_days"],
        production_duration_days=params["t_prod_days"],
        production_bhp_psi=params["prod_bhp_psi"],
        cycles=int(params["n_cycles"]),
    )
    frames = [
        ReservoirState(
            pressure_bar=_grid(arrays["pressure"][index]),
            gas_saturation=_grid(arrays["gas_sat"][index]),
            z_co2=_grid(arrays["z_co2"][index]),
        )
        for index in range(8)
    ]
    produce = (stages == 3).astype(np.float32)
    oil_delta = np.abs(oil_rate) * dt * SECONDS_PER_DAY * produce
    gas_delta = np.abs(gas_rate) * dt * SECONDS_PER_DAY * produce
    seed = SeedHistory(
        initial_state=frames[0],
        frames=frames,
        oil_delta_m3=oil_delta[:8].tolist(),
        gas_delta_m3=gas_delta[:8].tolist(),
        source_class="mrst_ground_truth",
        source_id=path.stem,
        schedule_fingerprint=schedule_fingerprint(schedule),
    )
    completion = [
        (int(completion_raw[0, k]) - 1, int(completion_raw[1, k]) - 1)
        for k in range(completion_raw.shape[1])
    ]
    return MrstReservoirImport(
        geology=geology,
        seed=seed,
        schedule=schedule,
        well_ij=(int(well_ij_raw[0]) - 1, int(well_ij_raw[1]) - 1),
        completion_ij=completion,
        targets={
            "pressure": arrays["pressure"],
            "gas_sat": arrays["gas_sat"],
            "z_co2": arrays["z_co2"],
            "oil_sat": arrays["oil_sat"],
            "oil_delta_m3": oil_delta,
            "gas_delta_m3": gas_delta,
        },
        sha256=digest,
    )
```

- [ ] **Step 5: Delegate `validation.py` to the loader**

In `src/jatibarang_ccus/surrogate/validation.py`, replace the body of `load_validation_case` with:

```python
def load_validation_case(case_id: str) -> tuple[PredictRequest, dict[str, np.ndarray]]:
    from ..imports.mrst import load_mrst_reservoir

    path = VALIDATION_DIR / f"{case_id}.mat"
    imported = load_mrst_reservoir(path)
    request = PredictRequest(
        scenario_id=case_id,
        geology=imported.geology,
        schedule=imported.schedule,
        seed=imported.seed,
    )
    return request, imported.targets
```

Delete the now-unused private parsing code from validation.py (keep `_grid` only if still referenced; otherwise remove it and its imports).

- [ ] **Step 6: Run new + existing tests**

Run: `python -m pytest tests/imports/test_mrst_loader.py tests/surrogate -q`
Expected: PASS (validation fixtures unchanged — same tensors, same fingerprints)

- [ ] **Step 7: Commit**

```bash
git add src/jatibarang_ccus/imports tests/imports src/jatibarang_ccus/surrogate/validation.py
git commit -m "feat(imports): shared MRST reservoir loader reused by validation"
```

---

### Task 2: Launch-pad bank format (backend)

A self-contained, hash-verified NPZ format for launch-pad banks, with a writer (used by tooling/tests and later G3 conversion) and a reader.

**Files:**
- Create: `src/jatibarang_ccus/imports/launchpads.py`
- Test: `tests/imports/test_launchpads.py`

**Interfaces:**
- Consumes: `SeedHistory`, `OperatingSchedule`, `schedule_fingerprint` (existing).
- Produces: `write_launchpad_bank(path, entries: dict[str, SeedHistory]) -> str` (returns sha256) and `load_launchpad_bank(path) -> dict[str, SeedHistory]` keyed by schedule fingerprint; `LaunchpadBankError`. Task 3 and Task 9 rely on these names.

- [ ] **Step 1: Write the failing round-trip test**

```python
# tests/imports/test_launchpads.py
from __future__ import annotations

from pathlib import Path

import pytest

from jatibarang_ccus.imports.launchpads import (
    LaunchpadBankError,
    load_launchpad_bank,
    write_launchpad_bank,
)
from jatibarang_ccus.imports.mrst import load_mrst_reservoir

CASE = Path("data/validation_cases/case_0016.mat")


def test_bank_round_trip(tmp_path: Path) -> None:
    imported = load_mrst_reservoir(CASE)
    bank_path = tmp_path / "model.launchpads.npz"
    digest = write_launchpad_bank(bank_path, {imported.seed.schedule_fingerprint: imported.seed})
    assert len(digest) == 64
    loaded = load_launchpad_bank(bank_path)
    assert set(loaded) == {imported.seed.schedule_fingerprint}
    pad = loaded[imported.seed.schedule_fingerprint]
    assert len(pad.frames) == 8
    assert pad.frames[0].pressure_bar.values == imported.seed.frames[0].pressure_bar.values


def test_rejects_wrong_format(tmp_path: Path) -> None:
    bogus = tmp_path / "bank.npz"
    bogus.write_bytes(b"zip? no")
    with pytest.raises(LaunchpadBankError):
        load_launchpad_bank(bogus)
```

- [ ] **Step 2: Run to verify it fails**

Run: `python -m pytest tests/imports/test_launchpads.py -q`
Expected: FAIL — module not found

- [ ] **Step 3: Implement writer/reader**

```python
# src/jatibarang_ccus/imports/launchpads.py
"""Launch-pad bank v1: schedule-fingerprinted warm-start histories in one NPZ.

Layout (all float32 unless noted):
  meta/version: [1]
  meta/fingerprints: array[str]                    (N fingerprints)
  <fp>/frames: (8, 3, 64, 64)                       pressure_bar, gas_saturation, z_co2
  <fp>/oil_delta_m3, <fp>/gas_delta_m3: (8,)
  <fp>/source_id: array[str] length 1
Never generated from thin air: banks are written from MRST-derived SeedHistory
objects only (spec §9 honesty rule).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np

from ..surrogate.schemas import Grid2D, ReservoirState, SeedHistory

VERSION = 1


class LaunchpadBankError(ValueError):
    """The file is not a readable launch-pad bank."""


def _frames_array(seed: SeedHistory) -> np.ndarray:
    out = np.empty((8, 3, 64, 64), dtype=np.float32)
    for index, frame in enumerate(seed.frames):
        out[index, 0] = np.asarray(frame.pressure_bar.as_array(), dtype=np.float32)
        out[index, 1] = np.asarray(frame.gas_saturation.as_array(), dtype=np.float32)
        out[index, 2] = np.asarray(frame.z_co2.as_array(), dtype=np.float32)
    return out


def write_launchpad_bank(path: Path, entries: dict[str, SeedHistory]) -> str:
    payload: dict[str, np.ndarray] = {
        "meta/version": np.array([VERSION]),
        "meta/fingerprints": np.array(sorted(entries), dtype=np.str_),
    }
    for fingerprint in sorted(entries):
        seed = entries[fingerprint]
        payload[f"{fingerprint}/frames"] = _frames_array(seed)
        payload[f"{fingerprint}/oil_delta_m3"] = np.asarray(seed.oil_delta_m3, dtype=np.float32)
        payload[f"{fingerprint}/gas_delta_m3"] = np.asarray(seed.gas_delta_m3, dtype=np.float32)
        payload[f"{fingerprint}/source_id"] = np.array([seed.source_id], dtype=np.str_)
    np.savez_compressed(path, **payload)
    return hashlib.sha256(Path(path).read_bytes()).hexdigest().upper()


def load_launchpad_bank(path: Path) -> dict[str, SeedHistory]:
    path = Path(path)
    try:
        with np.load(path, allow_pickle=False) as data:
            if int(data["meta/version"][0]) != VERSION:
                raise LaunchpadBankError(f"unsupported bank version in {path.name}")
            result: dict[str, SeedHistory] = {}
            for fingerprint in [str(v) for v in data["meta/fingerprints"]]:
                frames_raw = data[f"{fingerprint}/frames"]
                frames = [
                    ReservoirState(
                        pressure_bar=Grid2D.from_array(frames_raw[i, 0]),
                        gas_saturation=Grid2D.from_array(frames_raw[i, 1]),
                        z_co2=Grid2D.from_array(frames_raw[i, 2]),
                    )
                    for i in range(8)
                ]
                result[fingerprint] = SeedHistory(
                    initial_state=frames[0],
                    frames=frames,
                    oil_delta_m3=data[f"{fingerprint}/oil_delta_m3"].tolist(),
                    gas_delta_m3=data[f"{fingerprint}/gas_delta_m3"].tolist(),
                    source_class="mrst_ground_truth",
                    source_id=str(data[f"{fingerprint}/source_id"][0]),
                    schedule_fingerprint=fingerprint,
                )
            return result
    except LaunchpadBankError:
        raise
    except Exception as exc:  # zipfile/keys/shape errors
        raise LaunchpadBankError(f"not a readable launch-pad bank: {path.name}: {exc}") from exc
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/imports/test_launchpads.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/jatibarang_ccus/imports/launchpads.py tests/imports/test_launchpads.py
git commit -m "feat(imports): launch-pad bank v1 writer/reader with hash"
```

---

### Task 3: Terrain registry and import service (backend)

Registry of imported GeoTIFFs with whole-raster overview + windowed high-res crops, plus artifact storage for reservoir imports.

**Files:**
- Create: `src/jatibarang_ccus/imports/terrain.py`
- Create: `src/jatibarang_ccus/imports/store.py`
- Test: `tests/imports/test_terrain.py`, `tests/imports/test_store.py`

**Interfaces:**
- Produces (terrain): `TerrainRegistry(root: Path)` with `imports(path) -> TerrainRecord`, `list() -> list[TerrainRecord]`, `get(terrain_id) -> TerrainRecord`, `overview(terrain_id, max_px=512) -> Heightmap`, `window(terrain_id, bounds: tuple[minLon,minLat,maxLon,maxLat], max_px=768) -> Heightmap`; `Heightmap` is a pydantic model `{width, height, extent, min_elev, max_elev, elevations: list[float]}` matching the frontend `TerrainData` shape (camelCase handled in Task 5's route serialization: keys `width/height/extent{minLon,maxLon,minLat,maxLat}/minElev/maxElev/elevations`). `TerrainRecord` = `{terrain_id: str, sha256: str, source_path: str, extent: tuple, cell_size_m: float}`. `terrain_id` = `"terrain-" + sha256[:16].lower()`.
- Produces (store): `ImportStore(root: Path)` with `put(source: Path) -> StoredArtifact{artifact_id, sha256, path}` (copies into `root/<sha16>/<original name>`, idempotent by hash) and `resolve(artifact_id) -> Path`.
- Registry root default: `data/imports/terrain_registry.json` + cached overviews beside it; ImportStore default root `data/imports/`.

- [ ] **Step 1: Write failing tests**

```python
# tests/imports/test_terrain.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_bounds as transform_from_bounds

from jatibarang_ccus.imports.terrain import TerrainImportError, TerrainRegistry


@pytest.fixture()
def small_geotiff(tmp_path: Path) -> Path:
    path = tmp_path / "toy_dem.tif"
    height, width = 60, 80
    data = np.linspace(0, 500, height * width, dtype=np.float32).reshape(height, width)
    transform = transform_from_bounds(107.0, -7.0, 108.0, -6.4, width, height)
    with rasterio.open(
        path, "w", driver="GTiff", height=height, width=width, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)
    return path


def test_import_registers_and_builds_overview(tmp_path: Path, small_geotiff: Path) -> None:
    registry = TerrainRegistry(tmp_path / "registry")
    record = registry.imports(small_geotiff)
    assert record.terrain_id.startswith("terrain-")
    assert len(record.sha256) == 64
    # idempotent by content hash
    assert registry.imports(small_geotiff).terrain_id == record.terrain_id
    assert [r.terrain_id for r in registry.list()] == [record.terrain_id]

    overview = registry.overview(record.terrain_id, max_px=32)
    assert max(overview.width, overview.height) <= 32
    assert overview.min_elev >= 0 and overview.max_elev <= 500
    assert len(overview.elevations) == overview.width * overview.height


def test_window_crops_within_extent(tmp_path: Path, small_geotiff: Path) -> None:
    registry = TerrainRegistry(tmp_path / "registry")
    record = registry.imports(small_geotiff)
    window = registry.window(record.terrain_id, (107.2, -6.9, 107.6, -6.6), max_px=40)
    assert window.extent["minLon"] >= 107.0 and window.extent["maxLon"] <= 108.0
    assert len(window.elevations) == window.width * window.height


def test_import_rejects_non_raster(tmp_path: Path) -> None:
    bogus = tmp_path / "not_a_dem.tif"
    bogus.write_bytes(b"plain bytes")
    with pytest.raises(TerrainImportError):
        TerrainRegistry(tmp_path / "registry").imports(bogus)
```

```python
# tests/imports/test_store.py
from __future__ import annotations

from pathlib import Path

from jatibarang_ccus.imports.store import ImportStore


def test_put_is_idempotent_and_resolvable(tmp_path: Path) -> None:
    source = tmp_path / "model.mat"
    source.write_bytes(b"payload-bytes")
    store = ImportStore(tmp_path / "imports")
    first = store.put(source)
    second = store.put(source)
    assert first.artifact_id == second.artifact_id
    assert store.resolve(first.artifact_id).read_bytes() == b"payload-bytes"
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/imports/test_terrain.py tests/imports/test_store.py -q`
Expected: FAIL — modules not found

- [ ] **Step 3: Implement `store.py`**

```python
# src/jatibarang_ccus/imports/store.py
"""Hash-addressed local artifact store for imported study inputs (spec §6)."""

from __future__ import annotations

import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StoredArtifact:
    artifact_id: str
    sha256: str
    path: Path


class ImportStore:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def put(self, source: Path) -> StoredArtifact:
        source = Path(source)
        digest = hashlib.sha256(source.read_bytes()).hexdigest().upper()
        artifact_id = digest[:16].lower()
        target_dir = self.root / artifact_id
        target = target_dir / source.name
        if not target.exists():
            target_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return StoredArtifact(artifact_id=artifact_id, sha256=digest, path=target)

    def resolve(self, artifact_id: str) -> Path:
        target_dir = self.root / artifact_id
        files = sorted(p for p in target_dir.iterdir() if p.is_file()) if target_dir.exists() else []
        if not files:
            raise FileNotFoundError(f"imported artifact is missing: {artifact_id}")
        return files[0]
```

- [ ] **Step 4: Implement `terrain.py`**

```python
# src/jatibarang_ccus/imports/terrain.py
"""Terrain registry: whole-raster overviews and windowed crops (spec §6).

The registry JSON maps terrain_id -> {sha256, source_path, extent, cell_size_m}.
Overviews are decimated reads capped at max_px on the long side; windows are
bounded reads served for the field view. The same registered raster hash is
what routing consumes, keeping visualization and routing consistent.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import rasterio
from pydantic import BaseModel
from rasterio.windows import from_bounds as window_from_bounds


class TerrainImportError(ValueError):
    """The file is not a readable georeferenced raster."""


class Heightmap(BaseModel):
    width: int
    height: int
    extent: dict[str, float]  # minLon/maxLon/minLat/maxLat
    minElev: float
    maxElev: float
    elevations: list[float]


@dataclass(frozen=True)
class TerrainRecord:
    terrain_id: str
    sha256: str
    source_path: str
    extent: tuple[float, float, float, float]  # minLon, minLat, maxLon, maxLat
    cell_size_m: float


class TerrainRegistry:
    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.index_path = self.root / "terrain_registry.json"

    # ------------------------------------------------------------- persistence
    def _read_index(self) -> dict[str, dict]:
        if not self.index_path.exists():
            return {}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _write_index(self, index: dict[str, dict]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(index, indent=2, sort_keys=True), encoding="utf-8")

    # ------------------------------------------------------------------- API
    def imports(self, path: Path) -> TerrainRecord:
        path = Path(path)
        if not path.exists():
            raise TerrainImportError(f"terrain file is missing: {path}")
        digest = hashlib.sha256(path.read_bytes()).hexdigest().upper()
        terrain_id = f"terrain-{digest[:16].lower()}"
        index = self._read_index()
        if terrain_id not in index:
            try:
                with rasterio.open(path) as src:
                    bounds = src.bounds
                    cell_deg = abs(src.transform.a)
            except Exception as exc:
                raise TerrainImportError(f"not a readable raster: {path.name}: {exc}") from exc
            mid_lat = (bounds.bottom + bounds.top) / 2
            cell_size_m = cell_deg * 111_320 * math.cos(math.radians(mid_lat))
            index[terrain_id] = {
                "sha256": digest,
                "source_path": str(path),
                "extent": [bounds.left, bounds.bottom, bounds.right, bounds.top],
                "cell_size_m": cell_size_m,
            }
            self._write_index(index)
        return self.get(terrain_id)

    def list(self) -> list[TerrainRecord]:
        return [self.get(terrain_id) for terrain_id in sorted(self._read_index())]

    def get(self, terrain_id: str) -> TerrainRecord:
        entry = self._read_index().get(terrain_id)
        if entry is None:
            raise KeyError(f"terrain is not registered: {terrain_id}")
        return TerrainRecord(
            terrain_id=terrain_id,
            sha256=entry["sha256"],
            source_path=entry["source_path"],
            extent=tuple(entry["extent"]),
            cell_size_m=entry["cell_size_m"],
        )

    def overview(self, terrain_id: str, max_px: int = 512) -> Heightmap:
        record = self.get(terrain_id)
        min_lon, min_lat, max_lon, max_lat = record.extent
        return self._read(record, (min_lon, min_lat, max_lon, max_lat), max_px)

    def window(
        self,
        terrain_id: str,
        bounds: tuple[float, float, float, float],
        max_px: int = 768,
    ) -> Heightmap:
        record = self.get(terrain_id)
        min_lon, min_lat, max_lon, max_lat = record.extent
        clipped = (
            max(bounds[0], min_lon), max(bounds[1], min_lat),
            min(bounds[2], max_lon), min(bounds[3], max_lat),
        )
        if clipped[0] >= clipped[2] or clipped[1] >= clipped[3]:
            raise TerrainImportError("window does not intersect the terrain extent")
        return self._read(record, clipped, max_px)

    def _read(
        self,
        record: TerrainRecord,
        bounds: tuple[float, float, float, float],
        max_px: int,
    ) -> Heightmap:
        with rasterio.open(record.source_path) as src:
            win = window_from_bounds(bounds[0], bounds[1], bounds[2], bounds[3], src.transform)
            scale = max(1.0, win.width / max_px, win.height / max_px)
            out_w = max(2, int(win.width / scale))
            out_h = max(2, int(win.height / scale))
            data = src.read(1, window=win, out_shape=(out_h, out_w)).astype(float)
            nodata = src.nodata
        if nodata is not None:
            data[data == nodata] = np.nan
        data = np.clip(np.nan_to_num(data, nan=0.0), 0.0, None)
        return Heightmap(
            width=out_w,
            height=out_h,
            extent={
                "minLon": bounds[0], "maxLon": bounds[2],
                "minLat": bounds[1], "maxLat": bounds[3],
            },
            minElev=float(data.min()),
            maxElev=float(data.max()),
            elevations=[float(v) for v in data.reshape(-1)],
        )
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/imports -q`
Expected: PASS (all four import test files)

- [ ] **Step 6: Commit**

```bash
git add src/jatibarang_ccus/imports tests/imports
git commit -m "feat(imports): terrain registry with overview/window and artifact store"
```

---

### Task 4: Import API routes (backend)

Three routes wiring the import layer into the app, plus the OpenAPI contract update.

**Files:**
- Modify: `src/jatibarang_ccus/api/app.py`
- Modify: `specs/005-screening-api/contracts/openapi.yaml`
- Test: `tests/imports/test_import_api.py`

**Interfaces:**
- Produces routes (Task 6/7 frontend client consumes exactly these):
  - `POST /terrain/import` body `{"path": str}` → `{terrain_id, sha256, extent: {minLon,minLat,maxLon,maxLat}, cell_size_m, overview: Heightmap}`
  - `GET /terrain` → `[{terrain_id, sha256, source_path, extent, cell_size_m}]`
  - `GET /terrain/{terrain_id}/window?min_lon&min_lat&max_lon&max_lat&max_px` → `Heightmap`
  - `POST /reservoir/import` body `{"model_path": str, "bank_path": str | null}` → `{model_id, sha256, source_file, geology: GeologyInput.model_dump(), native_schedule: OperatingSchedule.model_dump(), native_fingerprint: str, well_ij: [i, j], completion_ij: [[i,j]...], launchpads: {bank_id: str|null, bank_sha256: str|null, covered_fingerprints: [str]}}` — `covered_fingerprints` always includes the native one. Seeds themselves stay server-side (spec §6: memos reference, requests are assembled server-known — see Task 9 note).
- `create_app` gains keyword-only factories with defaults: `terrain_registry: TerrainRegistry | None = None`, `import_store: ImportStore | None = None` (defaults constructed at `data/imports/`).

- [ ] **Step 1: Write failing API tests**

```python
# tests/imports/test_import_api.py
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_bounds as transform_from_bounds

from jatibarang_ccus.api.app import create_app
from jatibarang_ccus.imports.store import ImportStore
from jatibarang_ccus.imports.terrain import TerrainRegistry

from tests.screening.helpers import FakeRunner


class _FakeScreening:
    def list_presets(self):
        return []

    def health(self):
        return {
            "status": "ready", "surrogate_loaded": True, "solver_available": True,
            "active_runs": 0, "presets": [], "details": {},
        }


def _app(tmp_path: Path):
    return create_app(
        FakeRunner,
        screening_factory=lambda _runner: _FakeScreening(),
        terrain_registry=TerrainRegistry(tmp_path / "registry"),
        import_store=ImportStore(tmp_path / "imports"),
    )


@pytest.fixture()
def dem(tmp_path: Path) -> Path:
    path = tmp_path / "dem.tif"
    data = np.linspace(0, 300, 40 * 50, dtype=np.float32).reshape(40, 50)
    transform = transform_from_bounds(107.5, -6.9, 108.2, -6.4, 50, 40)
    with rasterio.open(
        path, "w", driver="GTiff", height=40, width=50, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)
    return path


def test_terrain_import_list_and_window(tmp_path: Path, dem: Path) -> None:
    with TestClient(_app(tmp_path)) as client:
        imported = client.post("/terrain/import", json={"path": str(dem)})
        assert imported.status_code == 200
        body = imported.json()
        assert body["terrain_id"].startswith("terrain-")
        assert body["overview"]["width"] > 0

        assert client.get("/terrain").json()[0]["terrain_id"] == body["terrain_id"]

        window = client.get(
            f"/terrain/{body['terrain_id']}/window",
            params={"min_lon": 107.6, "min_lat": -6.8, "max_lon": 107.9, "max_lat": -6.6},
        )
        assert window.status_code == 200
        assert window.json()["extent"]["minLon"] >= 107.5

        missing = client.post("/terrain/import", json={"path": str(tmp_path / "nope.tif")})
        assert missing.status_code == 422


def test_reservoir_import_returns_typed_payload(tmp_path: Path) -> None:
    model = Path("data/validation_cases/case_0016.mat")
    with TestClient(_app(tmp_path)) as client:
        response = client.post("/reservoir/import", json={"model_path": str(model)})
        assert response.status_code == 200
        body = response.json()
        assert body["geology"]["length_x_m"] == 900.0
        assert body["native_fingerprint"]
        assert body["launchpads"]["covered_fingerprints"] == [body["native_fingerprint"]]
        assert body["well_ij"][0] in range(64)

        bad = client.post("/reservoir/import", json={"model_path": str(tmp_path / "x.mat")})
        assert bad.status_code == 422
```

- [ ] **Step 2: Run to verify failure**

Run: `python -m pytest tests/imports/test_import_api.py -q`
Expected: FAIL — 404s / unexpected keyword `terrain_registry`

- [ ] **Step 3: Add routes to `app.py`**

Add imports at the top of `src/jatibarang_ccus/api/app.py`:

```python
from pydantic import BaseModel

from ..imports.launchpads import LaunchpadBankError, load_launchpad_bank
from ..imports.mrst import MrstImportError, load_mrst_reservoir
from ..imports.store import ImportStore
from ..imports.terrain import Heightmap, TerrainImportError, TerrainRegistry
```

Extend the factory signature and body:

```python
def create_app(
    runner_factory: RunnerFactory = load_surrogate,
    *,
    screening_factory: ScreeningFactory | None = None,
    terrain_registry: TerrainRegistry | None = None,
    import_store: ImportStore | None = None,
) -> FastAPI:
    registry = terrain_registry or TerrainRegistry(_REPO_ROOT / "data" / "imports")
    artifacts = import_store or ImportStore(_REPO_ROOT / "data" / "imports")
```

Add request models (module level, above `create_app`):

```python
class TerrainImportRequest(BaseModel):
    path: str


class ReservoirImportRequest(BaseModel):
    model_path: str
    bank_path: str | None = None
```

Add routes inside `create_app` (before `/health`):

```python
    @application.post(
        "/terrain/import",
        summary="Register a GeoTIFF terrain and return its basin overview",
        responses={200: {"description": "Terrain record with overview heightmap"},
                   422: {"description": "Path is missing or not a readable raster"}},
    )
    def terrain_import(payload: TerrainImportRequest) -> dict[str, Any]:
        try:
            record = registry.imports(Path(payload.path))
            overview = registry.overview(record.terrain_id)
        except TerrainImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        min_lon, min_lat, max_lon, max_lat = record.extent
        return {
            "terrain_id": record.terrain_id,
            "sha256": record.sha256,
            "extent": {"minLon": min_lon, "minLat": min_lat, "maxLon": max_lon, "maxLat": max_lat},
            "cell_size_m": record.cell_size_m,
            "overview": overview.model_dump(),
        }

    @application.get(
        "/terrain",
        summary="List registered terrains",
        responses={200: {"description": "Registered terrain records"}},
    )
    def terrain_list() -> list[dict[str, Any]]:
        return [
            {
                "terrain_id": r.terrain_id, "sha256": r.sha256, "source_path": r.source_path,
                "extent": {"minLon": r.extent[0], "minLat": r.extent[1],
                           "maxLon": r.extent[2], "maxLat": r.extent[3]},
                "cell_size_m": r.cell_size_m,
            }
            for r in registry.list()
        ]

    @application.get(
        "/terrain/{terrain_id}/window",
        response_model=Heightmap,
        summary="Read a high-resolution terrain window for the field view",
        responses={200: {"description": "Windowed heightmap"},
                   404: {"description": "Terrain is not registered"},
                   422: {"description": "Window does not intersect the terrain"}},
    )
    def terrain_window(
        terrain_id: str, min_lon: float, min_lat: float, max_lon: float, max_lat: float,
        max_px: int = 768,
    ) -> Heightmap:
        try:
            return registry.window(terrain_id, (min_lon, min_lat, max_lon, max_lat), max_px=max_px)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except TerrainImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post(
        "/reservoir/import",
        summary="Import one MRST reservoir model and optional launch-pad bank",
        responses={200: {"description": "Typed reservoir payload and coverage"},
                   422: {"description": "Model or bank file is unreadable"}},
    )
    def reservoir_import(payload: ReservoirImportRequest) -> dict[str, Any]:
        try:
            imported = load_mrst_reservoir(Path(payload.model_path))
        except MrstImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        stored = artifacts.put(Path(payload.model_path))
        bank_id = bank_sha = None
        covered = [imported.seed.schedule_fingerprint]
        if payload.bank_path:
            try:
                bank = load_launchpad_bank(Path(payload.bank_path))
            except LaunchpadBankError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            stored_bank = artifacts.put(Path(payload.bank_path))
            bank_id, bank_sha = stored_bank.artifact_id, stored_bank.sha256
            covered = sorted(set(covered) | set(bank))
        return {
            "model_id": stored.artifact_id,
            "sha256": stored.sha256,
            "source_file": Path(payload.model_path).name,
            "geology": imported.geology.model_dump(),
            "native_schedule": imported.schedule.model_dump(),
            "native_fingerprint": imported.seed.schedule_fingerprint,
            "well_ij": list(imported.well_ij),
            "completion_ij": [list(pair) for pair in imported.completion_ij],
            "launchpads": {
                "bank_id": bank_id, "bank_sha256": bank_sha,
                "covered_fingerprints": covered,
            },
        }
```

- [ ] **Step 4: Update the OpenAPI contract**

In `specs/005-screening-api/contracts/openapi.yaml`, add under `paths:` (summaries must match the route summaries exactly — the contract test compares them):

```yaml
  /terrain/import:
    post:
      summary: Register a GeoTIFF terrain and return its basin overview
      responses:
        '200': {description: Terrain record with overview heightmap}
        '422': {description: Path is missing or not a readable raster}
  /terrain:
    get:
      summary: List registered terrains
      responses:
        '200': {description: Registered terrain records}
  /terrain/{terrain_id}/window:
    get:
      summary: Read a high-resolution terrain window for the field view
      parameters:
        - {in: path, name: terrain_id, required: true, schema: {type: string}}
      responses:
        '200': {description: Windowed heightmap}
        '404': {description: Terrain is not registered}
        '422': {description: Window does not intersect the terrain}
  /reservoir/import:
    post:
      summary: Import one MRST reservoir model and optional launch-pad bank
      responses:
        '200': {description: Typed reservoir payload and coverage}
        '422': {description: Model or bank file is unreadable}
```

- [ ] **Step 5: Run import + contract + full suite**

Run: `python -m pytest tests/imports tests/screening/test_api_contract.py -q` then `python -m pytest tests -q`
Expected: PASS everywhere

- [ ] **Step 6: Regenerate frontend types and commit**

```bash
cd frontend && npm run gen:types && cd ..
git add src/jatibarang_ccus/api/app.py specs/005-screening-api/contracts/openapi.yaml \
        tests/imports/test_import_api.py frontend/src/api/types.gen.ts
git commit -m "feat(api): terrain and reservoir import routes"
```

---### Task 5: Relax `terrain_id` and screening request wiring (backend)

`InlineScreenRequest.terrain_id` is currently `Literal["jatibarang_srtm_v1"]`. Imported terrains must be usable for routing.

**Files:**
- Modify: `src/jatibarang_ccus/screening/schemas.py:151` (`terrain_id` field)
- Modify: `src/jatibarang_ccus/screening/orchestrator.py` (terrain resolution — find the code that maps `terrain_id` to the raster path; search `jatibarang_srtm_v1`)
- Test: `tests/screening/test_terrain_id_resolution.py`

**Interfaces:**
- `terrain_id: str = "jatibarang_srtm_v1"` (default preserved so every existing request/test stays valid).
- Orchestrator terrain resolution order: (1) the legacy id `"jatibarang_srtm_v1"` → the pinned assumptions raster path (unchanged behavior); (2) any id in `TerrainRegistry(data/imports)` → its `source_path` (routing then hashes that file exactly as it does the pinned one); (3) unknown id → the existing screening validation error path (422 surface).

- [ ] **Step 1: Locate current resolution.** Run `grep -rn "jatibarang_srtm_v1" src/` and read the orchestrator/routing call sites so the modification below lands where the raster path is actually chosen.

- [ ] **Step 2: Write the failing test**

```python
# tests/screening/test_terrain_id_resolution.py
from __future__ import annotations

import pytest

from jatibarang_ccus.screening.schemas import InlineScreenRequest
from jatibarang_ccus.screening.orchestrator import resolve_terrain_path


def test_schema_accepts_arbitrary_terrain_id() -> None:
    # Only the field type is under test: construction must not reject a
    # registry-style id. Use model_construct to skip unrelated validators.
    request = InlineScreenRequest.model_construct(terrain_id="terrain-abc123def4567890")
    assert request.terrain_id == "terrain-abc123def4567890"


def test_legacy_id_resolves_to_pinned_raster() -> None:
    path = resolve_terrain_path("jatibarang_srtm_v1")
    assert path.name == "DEM SRTM 30M JAWA BARAT.tif"


def test_unknown_id_raises_value_error() -> None:
    with pytest.raises(ValueError, match="terrain"):
        resolve_terrain_path("terrain-0000000000000000")
```

- [ ] **Step 3: Implement.** In `schemas.py` change the field to `terrain_id: str = "jatibarang_srtm_v1"`. In `orchestrator.py` add (and use at the raster-path call site found in Step 1):

```python
def resolve_terrain_path(terrain_id: str) -> Path:
    """Map a screening terrain_id to a raster path: legacy pinned id first,
    then the import registry. Unknown ids fail loudly (spec §6)."""
    if terrain_id == "jatibarang_srtm_v1":
        return _REPO_ROOT / ASSUMPTIONS["routing"]["terrain_raster_path"]
    from ..imports.terrain import TerrainRegistry

    try:
        return Path(TerrainRegistry(_REPO_ROOT / "data" / "imports").get(terrain_id).source_path)
    except KeyError as exc:
        raise ValueError(f"unknown terrain_id: {terrain_id}") from exc
```

Adapt the exact constant names (`_REPO_ROOT`, the assumptions accessor) to what the orchestrator already uses at that call site.

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/screening -q`
Expected: PASS (including all pre-existing screening tests)

- [ ] **Step 5: Update contract + regen types.** In `openapi.yaml`, change the `terrain_id` schema under `InlineScreenRequest` from `const: jatibarang_srtm_v1` to `{type: string, default: jatibarang_srtm_v1}` (grep the yaml for `jatibarang_srtm_v1`). Then `cd frontend && npm run gen:types`.

- [ ] **Step 6: Commit**

```bash
git add src/jatibarang_ccus/screening specs/005-screening-api/contracts/openapi.yaml \
        tests/screening/test_terrain_id_resolution.py frontend/src/api/types.gen.ts
git commit -m "feat(screening): registry-backed terrain_id resolution"
```

---

### Task 6: Field store and memo v3 (frontend)

The single new store owning study setup: terrain ref, field placement, reservoir import, wells, sources, and basin/field navigation — plus memo persistence.

**Files:**
- Create: `frontend/src/state/field.store.ts`
- Modify: `frontend/src/memo/studyMemo.ts` (memo v3 `field_setup` block)
- Modify: `frontend/src/state/study.store.ts` (`DEFAULT_STUDY_NAME = "Untitled study"`, memo stem `"untitled-study"`, drop `template` from `NewStudyOptions`)
- Test: `frontend/src/state/field.store.test.ts`, `frontend/src/memo/studyMemo.test.ts`

**Interfaces (Tasks 7–12 rely on these exact names):**

```typescript
// field.store.ts exports
export interface TerrainRef { terrain_id: string; sha256: string; source_path: string;
  extent: { minLon: number; maxLon: number; minLat: number; maxLat: number }; }
export interface FieldPlacement { name: string; center_lat: number; center_lon: number; rotation_deg: number; }
export interface ReservoirRef { model_id: string; sha256: string; source_file: string;
  native_fingerprint: string; covered_fingerprints: string[]; bank_id: string | null;
  well_ij: [number, number]; length_x_m: number; length_y_m: number; }
export interface PlacedWell { id: string; kind: "native" | "placed"; lat: number; lon: number; }
export interface PlacedSource { id: string; name: string; lat: number; lon: number;
  annual_capacity_t: number; outlet_pressure_bar: number; outlet_temperature_c: number;
  co2_purity: number; max_mass_flow_kg_s: number; }
export type SceneLevel = "basin" | "field";

interface FieldState {
  terrain: TerrainRef | null;
  reservoir: ReservoirRef | null;
  placement: FieldPlacement | null;
  wells: PlacedWell[];            // wells[0] is always the native well when reservoir set
  sources: PlacedSource[];
  level: SceneLevel;
  setup: (terrain: TerrainRef, reservoir: ReservoirRef, placement: FieldPlacement) => void;
  moveField: (center_lat: number, center_lon: number) => void;
  rotateField: (rotation_deg: number) => void;
  addWell: (lat: number, lon: number) => PlacedWell;      // id auto "W02"... (native = W01)
  moveWell: (id: string, lat: number, lon: number) => void; // native id -> no-op
  renameWell: (id: string, name: string) => void;
  removeWell: (id: string) => void;                        // native id -> no-op
  addSource: (source: Omit<PlacedSource, "id">) => PlacedSource;
  updateSource: (id: string, patch: Partial<Omit<PlacedSource, "id">>) => void;
  removeSource: (id: string) => void;
  enterField: () => void;
  exitField: () => void;
  reset: () => void;
  hydrate: (setup: FieldSetupMemo) => void;
}
export function nativeWellPosition(placement: FieldPlacement, reservoir: ReservoirRef):
  { lat: number; lon: number };
export const useFieldStore: UseBoundStore<StoreApi<FieldState>>;
```

`nativeWellPosition` math: grid-local offset of `well_ij` from grid center in metres
(`dx = (well_ij[1] + 0.5 - 32) * length_x_m / 64`, `dy = (well_ij[0] + 0.5 - 32) * length_y_m / 64`),
rotated by `rotation_deg`, converted with `dLat = dy / 111_320`,
`dLon = dx / (111_320 * cos(center_lat°))`. The store recomputes `wells[0]`'s lat/lon inside
`setup`, `moveField`, and `rotateField`.

```typescript
// studyMemo.ts additions
export const STUDY_MEMO_VERSION = 3;
export interface FieldSetupMemo {
  terrain: TerrainRef; reservoir: ReservoirRef; placement: FieldPlacement;
  wells: PlacedWell[]; sources: PlacedSource[];
}
export interface StudyMemo { /* existing fields */ field_setup?: FieldSetupMemo; }
export function isLegacyMemo(memo: StudyMemo): boolean; // memo_version < 3
```

- [ ] **Step 1: Write failing store tests**

```typescript
// frontend/src/state/field.store.test.ts
import { beforeEach, describe, expect, it } from "vitest";
import { useFieldStore, nativeWellPosition } from "./field.store";
import type { FieldPlacement, ReservoirRef, TerrainRef } from "./field.store";

const terrain: TerrainRef = {
  terrain_id: "terrain-abc", sha256: "A".repeat(64), source_path: "C:/dem.tif",
  extent: { minLon: 107, maxLon: 108, minLat: -7, maxLat: -6 },
};
const reservoir: ReservoirRef = {
  model_id: "m1", sha256: "B".repeat(64), source_file: "case_0016.mat",
  native_fingerprint: "fp-native", covered_fingerprints: ["fp-native"],
  bank_id: null, well_ij: [30, 36], length_x_m: 900, length_y_m: 600,
};
const placement: FieldPlacement = {
  name: "Test Field", center_lat: -6.5, center_lon: 107.5, rotation_deg: 0,
};

describe("field store", () => {
  beforeEach(() => useFieldStore.getState().reset());

  it("setup derives the native well from well_ij", () => {
    useFieldStore.getState().setup(terrain, reservoir, placement);
    const s = useFieldStore.getState();
    expect(s.wells).toHaveLength(1);
    expect(s.wells[0].kind).toBe("native");
    const expected = nativeWellPosition(placement, reservoir);
    expect(s.wells[0].lat).toBeCloseTo(expected.lat, 8);
    // well_ij[1]=36 is east of the 32-centre -> east of field centre
    expect(s.wells[0].lon).toBeGreaterThan(placement.center_lon);
  });

  it("moveField re-derives the native well; placed wells stay put", () => {
    const store = useFieldStore.getState();
    store.setup(terrain, reservoir, placement);
    const placed = store.addWell(-6.52, 107.52);
    useFieldStore.getState().moveField(-6.6, 107.6);
    const after = useFieldStore.getState();
    expect(after.wells[0].lat).not.toBeCloseTo(-6.5, 4);
    expect(after.wells.find((w) => w.id === placed.id)!.lat).toBe(-6.52);
  });

  it("native well cannot be moved or removed", () => {
    const store = useFieldStore.getState();
    store.setup(terrain, reservoir, placement);
    const native = store.wells[0];
    useFieldStore.getState().moveWell(native.id, 0, 0);
    useFieldStore.getState().removeWell(native.id);
    expect(useFieldStore.getState().wells[0]).toEqual(native);
  });

  it("enter/exit field toggles the scene level", () => {
    useFieldStore.getState().setup(terrain, reservoir, placement);
    useFieldStore.getState().enterField();
    expect(useFieldStore.getState().level).toBe("field");
    useFieldStore.getState().exitField();
    expect(useFieldStore.getState().level).toBe("basin");
  });
});
```

```typescript
// frontend/src/memo/studyMemo.test.ts — append tests
import { describe, expect, it } from "vitest";
import { isLegacyMemo, STUDY_MEMO_VERSION } from "./studyMemo";

describe("memo v3", () => {
  it("flags v2 memos as legacy", () => {
    expect(STUDY_MEMO_VERSION).toBe(3);
    expect(isLegacyMemo({ memo_version: 2 } as never)).toBe(true);
    expect(isLegacyMemo({ memo_version: 3 } as never)).toBe(false);
  });
});
```

- [ ] **Step 2: Run to verify failure** — `cd frontend && npm test -- --run src/state/field.store.test.ts src/memo/studyMemo.test.ts` → FAIL (module missing).

- [ ] **Step 3: Implement `field.store.ts` and memo changes** per the interfaces above (zustand `create`, same style as `study.store.ts`; ids `W01…` zero-padded two digits; `addSource` ids `S01…`). `hydrate` replaces the whole state from a `FieldSetupMemo` and recomputes nothing (memo stores the derived native position for display, per spec §10 — but `moveField` after hydrate re-derives as normal).

- [ ] **Step 4: Run tests + typecheck** — `npm test -- --run` and `npx tsc -b` → PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/state/field.store.ts frontend/src/state/field.store.test.ts \
        frontend/src/memo/studyMemo.ts frontend/src/memo/studyMemo.test.ts \
        frontend/src/state/study.store.ts
git commit -m "feat(frontend): field store and study memo v3"
```

---

### Task 7: Blank-slate boot and import client (frontend)

Remove the demo auto-load and baked terrain; add the typed client for the new routes; empty-state hint card.

**Files:**
- Modify: `frontend/src/run/useWorkbench.ts` (delete the demo-assets `useEffect`, lines 33–64, and `baseTemplateRef`; `createNewStudy` no longer uses templates — it now routes through the New Study flow of Task 8)
- Modify: `frontend/src/api/client.ts` (add import functions)
- Modify: `frontend/src/viewport/terrain.ts` (remove `loadTerrain` + its cache; keep `TerrainData`, `terrainColor`, `makeProjector`, `TERRAIN_SIZE`)
- Modify: `frontend/src/viewport/Viewport3D.tsx` (terrain comes from the field store — Task 9 completes this; in this task, render the blank-slate ground plane + hint card when `useFieldStore.getState().terrain == null`)
- Delete: `frontend/public/assets/terrain.json`, `frontend/public/assets/demo-request.json`, `frontend/public/assets/canned-demo.json`
- Modify: `frontend/src/chrome/Modals.tsx:136` — About text becomes "CCUS Screening Workbench — a Fieldman CCUS-planning module."
- Test: `frontend/src/api/importClient.test.ts`

**Interfaces:**
- `client.ts` additions (consumed by Tasks 8/9):

```typescript
export interface TerrainImportResponse { terrain_id: string; sha256: string;
  extent: { minLon: number; minLat: number; maxLon: number; maxLat: number };
  cell_size_m: number; overview: TerrainData; }
export function importTerrain(path: string): Promise<TerrainImportResponse>;
export function listTerrains(): Promise<Array<{ terrain_id: string; sha256: string;
  source_path: string; extent: TerrainImportResponse["extent"]; cell_size_m: number }>>;
export function getTerrainWindow(terrainId: string,
  bounds: { minLon: number; minLat: number; maxLon: number; maxLat: number },
  maxPx?: number): Promise<TerrainData>;
export interface ReservoirImportResponse { model_id: string; sha256: string; source_file: string;
  geology: Record<string, unknown>; native_schedule: Record<string, number>;
  native_fingerprint: string; well_ij: [number, number]; completion_ij: [number, number][];
  launchpads: { bank_id: string | null; bank_sha256: string | null; covered_fingerprints: string[] }; }
export function importReservoir(modelPath: string, bankPath?: string | null): Promise<ReservoirImportResponse>;
```

Note the server heightmap uses keys `minElev`/`maxElev` — identical to `TerrainData`, so responses cast directly.

- [ ] **Step 1: Write failing client tests** (msw-free: stub `fetch` like existing client tests do — check `frontend/src/api/sse.test.ts` for the established stubbing pattern and follow it):

```typescript
// frontend/src/api/importClient.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { importReservoir, importTerrain } from "./client";

describe("import client", () => {
  afterEach(() => vi.restoreAllMocks());

  it("posts the terrain path and returns the record", async () => {
    const body = { terrain_id: "terrain-x", sha256: "A", extent: {}, cell_size_m: 30, overview: {} };
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body))));
    const result = await importTerrain("C:/dem.tif");
    expect(result.terrain_id).toBe("terrain-x");
    const [url, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(url).toBe("/terrain/import");
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({ path: "C:/dem.tif" });
  });

  it("posts model and bank paths for reservoir import", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ model_id: "m" }))));
    await importReservoir("C:/case.mat", "C:/case.launchpads.npz");
    const [, init] = (fetch as ReturnType<typeof vi.fn>).mock.calls[0];
    expect(JSON.parse((init as RequestInit).body as string)).toEqual({
      model_path: "C:/case.mat", bank_path: "C:/case.launchpads.npz",
    });
  });
});
```

- [ ] **Step 2: Run to verify failure**, **Step 3: implement client functions** (follow `postScreen`'s fetch/error pattern in `client.ts`), **Step 4: remove demo wiring + assets + `loadTerrain`**, replacing Viewport3D's loader effect with field-store terrain (temporary in this task: `const terrain = useFieldStore((s) => s.terrain); const projector = useMemo(() => terrainOverview ? makeProjector(terrainOverview) : null, ...)` — the overview heightmap now lives in the field store; extend `TerrainRef` usage by storing the overview `TerrainData` alongside it in the store as `overviewData: TerrainData | null`, set during setup). Blank-slate empty state in `Viewport3D` when no terrain:

```tsx
if (!terrain) {
  return (
    <div className="viewport-empty">
      <div className="viewport-empty-hint">
        <strong>No study loaded</strong>
        <span>New Study — Ctrl+N · Open Study — Ctrl+O</span>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Update tests that depended on demo assets.** Run `npm test -- --run`; fix any test that asserted demo auto-load (search `canned-demo` / `demo-request` under `frontend/src`); delete those assertions or convert them to blank-slate expectations.

- [ ] **Step 6: Full frontend verification** — `npm test -- --run && npx tsc -b` → PASS.

- [ ] **Step 7: Commit**

```bash
git add -A frontend
git commit -m "feat(frontend): blank-slate boot, import client, remove baked demo assets"
```

---

### Task 8: New Study dialog rework (frontend)

**Files:**
- Modify: `frontend/src/chrome/NewStudyDialog.tsx` (full rework)
- Create: `frontend/src/chrome/wellsCsv.ts` (+ test `frontend/src/chrome/wellsCsv.test.ts`)
- Modify: `frontend/src/run/useWorkbench.ts` (`createNewStudy` action signature)

**Interfaces:**
- `parseWellsCsv(text: string): Array<{ id: string; lat: number; lon: number }>` — header `id,lat,lon`, throws `Error` with a line number on malformed rows.
- Dialog fields in order (spec §5): field/reservoir name (required), analyst, terrain (dropdown from `listTerrains()` + "Import GeoTIFF…" path input → `importTerrain`), reservoir model path (required) + optional launch-pad bank path → `importReservoir` (single call), coverage preview line ("covers N of M grid schedules" — M = 162 from the default operational grid, N = covered fingerprints that match; when no bank: "native schedule only"), initial placement (center lat/lon prefilled with terrain extent midpoint + rotation 0), optional wells CSV path/paste, start view, exaggeration.
- On Create: `useFieldStore.setup(terrain, reservoir, placement)`; CSV wells added via `addWell` then `renameWell`; `useStudyStore.create({name, analyst, ...})`; navigation to basin view (`exitField()`), workspace tab "compose".

- [ ] **Step 1: CSV parser test first**

```typescript
// frontend/src/chrome/wellsCsv.test.ts
import { describe, expect, it } from "vitest";
import { parseWellsCsv } from "./wellsCsv";

describe("parseWellsCsv", () => {
  it("parses id,lat,lon with header", () => {
    const rows = parseWellsCsv("id,lat,lon\nW02,-6.47,108.31\nW03,-6.48,108.33\n");
    expect(rows).toEqual([
      { id: "W02", lat: -6.47, lon: 108.31 },
      { id: "W03", lat: -6.48, lon: 108.33 },
    ]);
  });
  it("reports the offending line", () => {
    expect(() => parseWellsCsv("id,lat,lon\nW02,notanumber,1\n")).toThrow(/line 2/);
  });
});
```

- [ ] **Step 2: Implement parser; run test** (implementation is a ~20-line split/trim/Number.parseFloat function; empty lines skipped; header validated).
- [ ] **Step 3: Rework the dialog UI** following the existing `NewStudyDialog.tsx` markup conventions (`dialog-field` labels, selects). Import buttons show inline pending/error text (reuse the dialog's existing error span pattern). Remove the `template` select entirely.
- [ ] **Step 4: Update `createNewStudy`** in `useWorkbench.ts`: it now only resets stores (`useLedgerStore.setActive(null)`, selection clear, workspace prefs) — the dialog performs imports itself before calling it. Delete the "template still loading" banner branch.
- [ ] **Step 5: `npm test -- --run && npx tsc -b`** → PASS. Manual smoke: `npm run dev` + backend, create a study against `data/validation_cases/case_0016.mat` and the Jawa Barat GeoTIFF path.
- [ ] **Step 6: Commit** — `git add -A frontend && git commit -m "feat(frontend): import-driven New Study dialog"`

---

### Task 9: Basin scene — outline, wells, sources, context menu (frontend)

**Files:**
- Create: `frontend/src/viewport/FieldOutline.tsx`
- Create: `frontend/src/viewport/SceneContextMenu.tsx`
- Create: `frontend/src/viewport/SourceDialog.tsx`
- Modify: `frontend/src/viewport/Viewport3D.tsx` (render outline/wells/sources from field store; right-click plumbing; double-click enter)
- Test: `frontend/src/viewport/fieldInteractions.test.ts` (store-level: the interaction handlers call store actions — test the handlers as pure functions)

**Interfaces:**
- `FieldOutline` props: `{ projector: TerrainProjector; placement: FieldPlacement; reservoir: ReservoirRef; interactive: boolean }`. Renders a rotated rectangle (three `Line` from drei, matching Viewport3D's existing import) sized `length_x_m × length_y_m` via `projector.metresPerSceneUnit`, plus a name `Html` label and a rotate handle sphere at the mid-east edge. Dragging body → `moveField` (pointermove on an invisible larger hit plane while captured); dragging handle → `rotateField` (angle from center). Double-click → `enterField()`. Right-click → context menu with "Enter field".
- `SceneContextMenu`: plain absolutely-positioned `<div className="scene-context-menu">` driven by local state in Viewport3D: `{ x, y, kind: "terrain" | "outline" | "well" | "source", targetId?: string, lat, lon }`. Items: terrain → "Add CO₂ source here", plus "Add candidate well" when the click lands inside the outline polygon; well (placed) → Rename / Remove; source → Edit / Remove; outline → Enter field. Escape or click-away closes.
- `SourceDialog` props `{ initial?: PlacedSource; lat: number; lon: number; onSave(source): void; onClose(): void }` — name + annual capacity required; Advanced `<details>` with outlet pressure (default 120), temperature (27), purity (0.95), peak flow (600) — defaults copied from the Subang source constants in `data/jatibarang/case_study_assumptions.json` as generic screening defaults.
- Geometry helper exported for tests: `pointInField(lat, lon, placement, reservoir): boolean` (inverse-rotate the offset, compare against half-lengths).

- [ ] **Step 1: Failing geometry/interaction tests**

```typescript
// frontend/src/viewport/fieldInteractions.test.ts
import { describe, expect, it } from "vitest";
import { pointInField } from "./FieldOutline";
import type { FieldPlacement, ReservoirRef } from "../state/field.store";

const reservoir = { length_x_m: 900, length_y_m: 600 } as ReservoirRef;
const placement: FieldPlacement = { name: "F", center_lat: -6.5, center_lon: 108.0, rotation_deg: 0 };

describe("pointInField", () => {
  it("accepts the centre and rejects a point 1 km east", () => {
    expect(pointInField(-6.5, 108.0, placement, reservoir)).toBe(true);
    expect(pointInField(-6.5, 108.009, placement, reservoir)).toBe(false); // ~1 km
  });
  it("respects rotation", () => {
    const rotated = { ...placement, rotation_deg: 90 };
    // 400 m east fits inside the rotated (600 m-wide) footprint's half-width? 300 m -> no
    expect(pointInField(-6.5, 108.0036, rotated, reservoir)).toBe(false);
    // 400 m north now lies along the rotated long axis -> yes
    expect(pointInField(-6.4964, 108.0, rotated, reservoir)).toBe(true);
  });
});
```

- [ ] **Step 2: Implement `pointInField` + components.** Scene plumbing in Viewport3D: `onContextMenu` on the terrain mesh (`ThreeEvent<MouseEvent>` carries `event.point`; invert the projector to lat/lon with a new `projector`-adjacent helper `xzToCoordinate(projector, x, z)` added in `terrain.ts` — inverse of `toXZ`), `event.nativeEvent.preventDefault()`. Wells render as small cylinders (native: distinct ring), sources as spheres with `Html` labels — follow the existing scene-object rendering style in Viewport3D (see `collectSceneObjects` usage) but read from `useFieldStore` instead of the ledger when a study setup exists.
- [ ] **Step 3: Inspector line.** In `frontend/src/layout/Inspector.tsx`, when a well is selected and a reservoir is set, render exactly: `Reservoir response assumes the local geology at this site matches the study's reservoir model.`
- [ ] **Step 4: Tests + typecheck + manual QA** (`npm test -- --run && npx tsc -b`; dev-server: place field, drag, rotate, add well/source via right-click, rename/remove).
- [ ] **Step 5: Commit** — `git add -A frontend && git commit -m "feat(viewport): basin scene with field outline, wells, sources"`

---

### Task 10: Field scene and navigation (frontend)

**Files:**
- Modify: `frontend/src/viewport/Viewport3D.tsx` (level switch, camera transition, breadcrumb overlay, Esc exit)
- Modify: `frontend/src/viewport/ReservoirGrid.tsx` (accept anchor/rotation instead of assuming scene centre — pass `position`/`rotation` group props from the field placement)
- Test: extend `frontend/src/viewport/fieldInteractions.test.ts`

**Interfaces:**
- Level from `useFieldStore((s) => s.level)`. Basin: overview heightmap. Field: on `enterField`, fetch `getTerrainWindow(terrain_id, fieldBounds, 768)` where `fieldBounds` = placement centre ± `max(length_x_m, length_y_m) * 3` metres converted to degrees; build a second projector from the window and render the existing `ReservoirGrid` at the placement anchor with `rotation={[0, -rotation_deg * DEG2RAD, 0]}`.
- Breadcrumb overlay (HTML, not Three): `◂ Basin` button top-left of the canvas wrapper; `Escape` keydown (when no dialog/context menu open) calls `exitField()`.
- Camera transition: lerp `OrbitControls.target` and camera position over ~600 ms toward the field anchor on enter and back to origin on exit (use a `useFrame` tween with a ref flag — matching the imperative OrbitControls ref pattern already in Viewport3D).
- Store test: entering field with no terrain window keeps `level === "field"` and shows the loading state (fetch failure → banner via `useUiStore.pushBanner({ id: "terrain-window-failed", ... })` and `exitField()`).

- [ ] **Step 1: Write the failing navigation test** (store-level: `enterField` on a store with no reservoir is a no-op; with reservoir set it flips level).
- [ ] **Step 2: Implement** per interfaces.
- [ ] **Step 3: Tests + typecheck + manual QA** (enter/exit, camera moves, reservoir renders at the outline, high-res window loads).
- [ ] **Step 4: Commit** — `git commit -am "feat(viewport): field-level scene with terrain window and navigation"`

---

### Task 11: Request builder and coverage-gated compose (frontend)

**Files:**
- Create: `frontend/src/compose/studyRequest.ts` (+ test `frontend/src/compose/studyRequest.test.ts`)
- Create: `frontend/src/compose/coverage.ts` (+ test `frontend/src/compose/coverage.test.ts`)
- Modify: `frontend/src/compose/Composer.tsx` (grid coverage display; run `Glob frontend/src/compose/*` first and put the gating where the operational grid is edited)
- Modify: `frontend/src/run/useWorkbench.ts` (`screen()` uses the study request when a field setup exists)

**Interfaces:**

```typescript
// coverage.ts
export interface ScheduleCombo { injection_rate_m3_day: number; soak_duration_days: number;
  production_duration_days: number; production_bhp_psi: number; cycles: number; }
export function comboFingerprint(combo: ScheduleCombo, injectionDurationDays: number): string;
  // MUST mirror src/jatibarang_ccus/surrogate/preprocessing.py::schedule_fingerprint —
  // read that function first and reproduce its exact serialization + hash;
  // cross-check in the test against a fingerprint captured from the backend.
export function coveredCombos(grid: OperationalGrid, injectionDurationDays: number,
  covered: string[]): { total: number; covered: number; disabled: ScheduleCombo[] };
```

```typescript
// studyRequest.ts
export function buildStudyRequest(opts: {
  field: FieldSetupMemo; geology: Record<string, unknown>;
  base: Pick<InlineScreenRequest, "carbon_prices" | "fiscal_cases" | "economic_assumptions"
    | "annual_co2_budget_tonnes" | "operational_grid" | "cost_case" | "supply_scenarios"
    | "project_life_years" | "selection_fiscal_case_id" | "shortlist_top_k" | "detailed_top_k">;
}): InlineScreenRequest;
// - geologies: { [model_id]: geology payload }  (one entry)
// - candidates: wells.map(w => ({ candidate_id: w.id, latitude: w.lat, longitude: w.lon,
//     geology_id: model_id }))  — mirror ScreeningCandidate in screening/schemas.py exactly
//     (read the class; adjust key names to match before finalizing)
// - sources: sources.map(s => ({ id: s.id, name: s.name,
//     location: { latitude: s.lat, longitude: s.lon },
//     capacity_tonnes_per_year: s.annual_capacity_t, max_mass_flow_kg_s: s.max_mass_flow_kg_s,
//     outlet_pressure_bar: s.outlet_pressure_bar, outlet_temperature_c: s.outlet_temperature_c,
//     co2_purity: s.co2_purity }))
// - seeds: resolved server-side is NOT available inline — the request carries the
//     imported model's seed payload under its fingerprint. buildStudyRequest therefore
//     also accepts `seeds: Record<string, unknown>` fetched at import time; extend
//     ReservoirImportResponse (Task 4) with `native_seed: SeedHistory.model_dump()` and,
//     when a bank was supplied, `bank_seeds: {fingerprint: seed payload}` — update
//     Task 4's route + test to include `native_seed` before implementing this task.
// - terrain_id: field.terrain.terrain_id; schedules: null (grid mode), filtered to covered combos
//     via `scenario-limiting`: emit `schedules` = the covered subset when coverage < total.
```

- The default economics/prices `base` comes from a new static module `frontend/src/compose/defaults.ts` containing the four carbon-price scenarios and fiscal cases copied verbatim from `data/jatibarang/economic_basis.json` (these are generic screening defaults, editable in the composer as today).
- Composer copy for uncovered combos, verbatim (Global Constraints): "no launch pad for this schedule — import a bank or run MRST offline".
- `screen()` refuses an empty covered set: banner `id: "coverage-empty"`, message "No screened schedules: none of the grid combinations have launch pads."

- [ ] **Step 1: Failing tests for `comboFingerprint` (against a captured backend fingerprint), `coveredCombos` (162-grid with native-only coverage → covered 1), and `buildStudyRequest` (produces `mode: "inline"`, one geology, candidates carrying `geology_id`, covered `schedules` subset).** Capture the reference fingerprint: `python -c "from jatibarang_ccus.imports.mrst import load_mrst_reservoir; print(load_mrst_reservoir('data/validation_cases/case_0016.mat').seed.schedule_fingerprint)"` and paste into the test.
- [ ] **Step 2: Implement; adjust Task-4 route to include seed payloads (`native_seed`, `bank_seeds`); rerun backend import tests.**
- [ ] **Step 3: Composer integration + workbench `screen()` wiring.**
- [ ] **Step 4: Full verification: `python -m pytest tests -q`; `npm test -- --run && npx tsc -b`. End-to-end manual: create study from case_0016 → grid shows 1/162 covered → screen runs the single covered schedule and returns a result.**
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(compose): study request builder with launch-pad coverage gating"`

---

### Task 12: Influence-zone layer and memo round-trip (frontend)

**Files:**
- Create: `frontend/src/viewport/InfluenceZones.tsx`
- Modify: `frontend/src/viewport/Viewport3D.tsx` (render post-run zones from the active ledger entry)
- Modify: `frontend/src/memo/export.ts` + `frontend/src/memo/import.ts` (persist/hydrate `field_setup`)
- Modify: `frontend/src/state/workspace.store.ts` (`LayerVisibility` gains `influence: boolean`, default true; add the toggle where the other layer toggles render — follow `exclusions`)
- Test: `frontend/src/viewport/influence.test.ts`, extend memo tests

**Interfaces:**
- The screen result's interference audit: locate the fields via `grep -n "interference" frontend/src/api/types.ts` (the audit carries per-well influence radii in metres and flagged pairs). `InfluenceZones` props `{ projector: TerrainProjector; entries: Array<{ candidate_id: string; lat: number; lon: number; radius_m: number; flagged: boolean }> }` → translucent discs (`circleGeometry`, opacity 0.18, gold; flagged: warning tint + `Html` badge "interference"). A pure adapter `influenceEntries(result: ScreenResult, plan: CarbonPricePlan | null, wells: PlacedWell[]): entries[]` lives beside it and is what gets unit-tested.
- Memo: `exportStudyMemo` writes `field_setup` from `useFieldStore` when present; `pickStudyMemo`/import hydrates the field store (`hydrate`) and, for `isLegacyMemo`, pushes banner `id: "memo-legacy"`, severity "info", message "This memo predates field setups; opened read-only without a field scene."

- [ ] **Step 1: Failing adapter test** (result fixture with two wells, one flagged pair → two entries, flagged well marked).
- [ ] **Step 2: Implement adapter + component + layer toggle.**
- [ ] **Step 3: Memo round-trip test**: export entry with field setup → import → field store hydrated (deep-equal wells/sources/placement).
- [ ] **Step 4: `npm test -- --run && npx tsc -b`** → PASS.
- [ ] **Step 5: Commit** — `git add -A frontend && git commit -m "feat(viewport): influence-zone layer and memo v3 round-trip"`

---

### Task 13: Naming sweep, demo memo, final verification

**Files:**
- Modify: any remaining "Jatibarang" product copy — run `grep -rn "Jatibarang" frontend/src` and clean UI strings (keep: preset ids in `types.gen.ts`/`types.ts` unions, memo kind constant `jatibarang.ccus.study-memo` [a wire-format id, not UI copy — renaming would orphan existing memos], test fixtures).
- Create: `data/jatibarang/README_demo_memo.md` — instructions to regenerate `jatibarang.study.json` through the real flow (register the Jawa Barat raster, import `case_0016.mat`, place at −6.53/108.39 rotation 35°, CSV the 20 wells from `case_study_assumptions.json` coordinates, add the Subang source, save memo). The memo itself is produced manually through the app once the flow works and committed then.

- [ ] **Step 1: Sweep + fix strings.**
- [ ] **Step 2: Full verification** — `python -m pytest tests -q`; `cd frontend && npm test -- --run && npx tsc -b && npm run build`. Expected: all pass, build succeeds.
- [ ] **Step 3: Manual QA per spec §13** — blank boot with zero asset fetches (network tab), full create-place-enter-screen flow at 1920×1080, no console errors.
- [ ] **Step 4: Commit** — `git add -A && git commit -m "chore: blank-slate naming sweep and demo memo instructions"`

---

## Self-Review Notes

- **Spec coverage:** §4 boot → Task 7; §5 dialog → Task 8; §6 endpoints/artifacts → Tasks 1–5; §7 basin/wells/sources → Tasks 6, 9; §8 field view + influence layer → Tasks 10, 12; §9 coverage gating → Task 11; §10 memo → Tasks 6, 12; §12 demo regeneration → Task 13; §13 verification → every task + Task 13.
- **Known judgment points for the implementer:** exact `ScreeningCandidate`/`CO2Source` key names (Task 11 instructs reading `screening/schemas.py` first); the fingerprint mirror (Task 11 pins it with a captured reference value); Composer integration point (locate the grid editor first). These are bounded look-and-match steps, not open design questions.
- **Type consistency check:** `TerrainRef`/`ReservoirRef`/`PlacedWell`/`PlacedSource`/`FieldSetupMemo` names match across Tasks 6, 8, 9, 11, 12; import client names (`importTerrain`, `importReservoir`, `getTerrainWindow`, `listTerrains`) match Tasks 7–10; backend names (`load_mrst_reservoir`, `load_launchpad_bank`, `TerrainRegistry.imports/list/get/overview/window`, `ImportStore.put/resolve`, `resolve_terrain_path`) match Tasks 1–5.
