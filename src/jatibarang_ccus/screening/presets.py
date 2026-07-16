from __future__ import annotations

import hashlib
import json
from pathlib import Path
from threading import Lock
from typing import Any, Iterator

import numpy as np
from pydantic import BaseModel, Field

from jatibarang_ccus.surrogate.config import REPO_ROOT
from jatibarang_ccus.surrogate.preprocessing import schedule_fingerprint
from jatibarang_ccus.contracts import CO2Source, CarbonPriceScenario, Coordinate, EconomicAssumptions, FiscalCase
from jatibarang_ccus.surrogate.schemas import (
    GeologyInput,
    Grid2D,
    OperatingSchedule,
    PredictRequest,
    ReservoirState,
    SeedHistory,
)

from .schemas import (
    InlineScreenRequest,
    MaterializedScenario,
    PresetInfo,
    PresetScreenRequest,
    ProducedCO2Assumption,
)


EXPECTED_PRESETS = {
    "jatibarang_demo_v1": (200, 20, 10),
    "jatibarang_full_v1": (3240, 20, 162),
}
_HASH_CACHE: dict[tuple[str, int, int], str] = {}
_HASH_CACHE_LOCK = Lock()


class PresetUnavailableError(OSError):
    """A server-owned preset dependency is missing, corrupt, or inconsistent."""


class PresetManifest(BaseModel):
    schema_version: str = "1.0"
    preset_id: str
    logical_scenarios: int = Field(ge=1)
    geology_count: int = Field(ge=1)
    schedule_count: int = Field(ge=1)
    payload_file: str
    payload_sha256: str = Field(min_length=64, max_length=64)
    design_sha256: str = Field(min_length=64, max_length=64)
    source_manifest: str
    generated_at: str
    status: str = "derived_seed_bank"
    provenance: dict[str, Any] = Field(default_factory=dict)


class CompactPresetCandidate(BaseModel):
    candidate_id: str
    location: Coordinate
    produced_co2: ProducedCO2Assumption


class CompactPresetMetadata(BaseModel):
    schema_version: str = "2.0"
    preset_id: str
    candidates: list[CompactPresetCandidate]
    schedules: list[OperatingSchedule]
    sources: list[CO2Source]
    annual_co2_budget_tonnes: float
    carbon_prices: list[CarbonPriceScenario]
    fiscal_cases: list[FiscalCase]
    economic_assumptions: EconomicAssumptions
    project_life_years: int = 8
    terrain_id: str = "jatibarang_srtm_v1"
    routing_basis_id: str = "jatibarang_case_study_v1"
    pipeline_basis_id: str = "jatibarang_case_study_v1"


class CompactPresetBank:
    """Array-backed preset that materializes Pydantic seeds only one batch at a time."""

    def __init__(self, payload_path: Path) -> None:
        self.payload_path = payload_path
        self._payload = np.load(payload_path, allow_pickle=False)
        encoded = np.asarray(self._payload["metadata_json_utf8"], dtype=np.uint8).tobytes()
        self.metadata = CompactPresetMetadata.model_validate_json(encoded.decode("utf-8"))
        self.run_id: str | None = None
        self.supply_scenarios = ["optimized_pipeline", "trucking_counterfactual"]
        self.cost_case = "base"
        self.selection_fiscal_case_id = "pre_tax"
        self.shortlist_top_k = 5
        self.detailed_top_k = 5
        self.scenario_limit = 4096
        self.carbon_prices = list(self.metadata.carbon_prices)
        self.fiscal_cases = list(self.metadata.fiscal_cases)

    def configure(self, request: PresetScreenRequest) -> "CompactPresetBank":
        self.run_id = request.run_id
        self.supply_scenarios = list(request.supply_scenarios)
        self.cost_case = request.cost_case
        self.selection_fiscal_case_id = request.selection_fiscal_case_id
        self.shortlist_top_k = request.shortlist_top_k
        self.detailed_top_k = request.detailed_top_k
        self.scenario_limit = request.scenario_limit
        if request.carbon_price_scenario_ids is not None:
            requested = set(request.carbon_price_scenario_ids)
            self.carbon_prices = [
                item for item in self.metadata.carbon_prices if item.scenario_id in requested
            ]
            missing = requested - {item.scenario_id for item in self.carbon_prices}
            if missing:
                raise ValueError(f"preset does not define carbon-price scenarios: {sorted(missing)}")
        if len(self.carbon_prices) < 4:
            raise ValueError("Feature 004 requires at least four carbon-price scenarios")
        if request.fiscal_case_ids is not None:
            requested = set(request.fiscal_case_ids)
            self.fiscal_cases = [
                item for item in self.metadata.fiscal_cases if item.case_id in requested
            ]
            missing = requested - {item.case_id for item in self.fiscal_cases}
            if missing:
                raise ValueError(f"preset does not define fiscal cases: {sorted(missing)}")
        if self.selection_fiscal_case_id not in {item.case_id for item in self.fiscal_cases}:
            raise ValueError("selection_fiscal_case_id must be included in preset fiscal cases")
        if self.logical_scenario_count > self.scenario_limit:
            raise ValueError(
                f"materialized {self.logical_scenario_count} scenarios exceeds scenario limit {self.scenario_limit}"
            )
        return self

    def __getattr__(self, name: str) -> Any:
        return getattr(self.metadata, name)

    @property
    def logical_scenario_count(self) -> int:
        return len(self.metadata.candidates) * len(self.metadata.schedules)

    def _geology(self, index: int) -> GeologyInput:
        maps = self._payload["geology_maps"][index]
        scalars = self._payload["geology_scalars"][index]
        return GeologyInput(
            permeability_md=Grid2D.from_array(maps[0].reshape(64, 64)),
            porosity_fraction=Grid2D.from_array(maps[1].reshape(64, 64)),
            structure_m=Grid2D.from_array(maps[2].reshape(64, 64)),
            fracture_proxy=Grid2D.from_array(maps[3].reshape(64, 64)),
            barrier=Grid2D.from_array(maps[4].reshape(64, 64)),
            facies=Grid2D.from_array(maps[5].reshape(64, 64)),
            well_mask=Grid2D.from_array(maps[6].reshape(64, 64)),
            completion_mask=Grid2D.from_array(maps[7].reshape(64, 64)),
            anisotropy_ratio=float(scalars[0]),
            reservoir_temperature_c=float(scalars[1]),
            length_x_m=float(scalars[2]),
            length_y_m=float(scalars[3]),
            thickness_m=float(scalars[4]),
        )

    def iter_scenarios(self) -> Iterator[MaterializedScenario]:
        seed_frames = self._payload["seed_frames"]
        oil = self._payload["seed_oil_delta"]
        gas = self._payload["seed_gas_delta"]
        for candidate_index, candidate in enumerate(self.metadata.candidates):
            geology = self._geology(candidate_index)
            for schedule_index, schedule in enumerate(self.metadata.schedules):
                active = seed_frames[candidate_index, schedule_index]
                frames = [
                    ReservoirState(
                        pressure_bar=Grid2D.from_array(active[index, 0].reshape(64, 64)),
                        gas_saturation=Grid2D.from_array(active[index, 1].reshape(64, 64)),
                        z_co2=Grid2D.from_array(active[index, 2].reshape(64, 64)),
                    )
                    for index in range(8)
                ]
                fingerprint = schedule_fingerprint(schedule)
                seed = SeedHistory(
                    initial_state=frames[0],
                    frames=frames,
                    oil_delta_m3=oil[candidate_index, schedule_index].astype(float).tolist(),
                    gas_delta_m3=gas[candidate_index, schedule_index].astype(float).tolist(),
                    source_class="derived_seed",
                    source_id=f"{self.metadata.preset_id}:{candidate.candidate_id}:{fingerprint[:12]}",
                    schedule_fingerprint=fingerprint,
                )
                scenario_id = f"{candidate.candidate_id}--{fingerprint[:12]}"
                predict = PredictRequest(
                    scenario_id=scenario_id,
                    geology=geology,
                    schedule=schedule,
                    seed=seed,
                )
                yield MaterializedScenario(
                    scenario_id=scenario_id,
                    candidate_id=candidate.candidate_id,
                    location=candidate.location,
                    produced_co2=candidate.produced_co2,
                    schedule=schedule,
                    predict_request=predict,
                    input_fingerprint=_scenario_fingerprint(predict),
                )

    def close(self) -> None:
        self._payload.close()


def _sha256(path: Path) -> str:
    stat = path.stat()
    key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    with _HASH_CACHE_LOCK:
        cached = _HASH_CACHE.get(key)
    if cached is not None:
        return cached
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    value = digest.hexdigest().upper()
    with _HASH_CACHE_LOCK:
        _HASH_CACHE[key] = value
    return value


def _json_fingerprint(value: Any) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest().upper()


def _scenario_fingerprint(predict: PredictRequest) -> str:
    payload = {
        "geology": predict.geology.model_dump(mode="json"),
        "seed": predict.seed.model_dump(mode="json"),
        "schedule": predict.schedule.model_dump(mode="json"),
    }
    return _json_fingerprint(payload)


def materialize_inline_scenarios(request: InlineScreenRequest) -> list[MaterializedScenario]:
    schedules = request.schedules if request.schedules is not None else request.operational_grid.expand()
    total = len(request.candidates) * len(schedules)
    if total > request.scenario_limit:
        raise ValueError(f"materialized {total} scenarios exceeds scenario limit {request.scenario_limit}")
    if total > 4096:
        raise ValueError("materialized scenarios exceed the Feature 005 hard limit of 4096")

    output: list[MaterializedScenario] = []
    for candidate in sorted(request.candidates, key=lambda item: item.candidate_id):
        if candidate.geology_id not in request.geologies:
            raise ValueError(f"candidate {candidate.candidate_id} references unknown geology {candidate.geology_id}")
        for active_schedule in schedules:
            fingerprint = schedule_fingerprint(active_schedule)
            seed_id = candidate.seed_by_schedule_fingerprint.get(fingerprint)
            if seed_id is None:
                raise ValueError(
                    f"candidate {candidate.candidate_id} is missing compatible seed for schedule {fingerprint}"
                )
            if seed_id not in request.seeds:
                raise ValueError(f"candidate {candidate.candidate_id} references unknown seed {seed_id}")
            active_seed = request.seeds[seed_id]
            if active_seed.schedule_fingerprint.upper() != fingerprint:
                raise ValueError(f"seed {seed_id} schedule fingerprint does not match {fingerprint}")
            scenario_id = f"{candidate.candidate_id}--{fingerprint[:12]}"
            predict = PredictRequest(
                scenario_id=scenario_id,
                geology=request.geologies[candidate.geology_id],
                schedule=active_schedule,
                seed=active_seed,
            )
            output.append(
                MaterializedScenario(
                    scenario_id=scenario_id,
                    candidate_id=candidate.candidate_id,
                    location=candidate.location,
                    produced_co2=candidate.produced_co2,
                    schedule=active_schedule,
                    predict_request=predict,
                    input_fingerprint=_scenario_fingerprint(predict),
                )
            )
    return sorted(output, key=lambda item: item.scenario_id)


class PresetRegistry:
    def __init__(self, root: Path | str = REPO_ROOT / "data" / "screening_presets") -> None:
        self.root = Path(root)
        self._components: dict[str, Any] | None = None

    def component_catalog(self) -> dict[str, Any]:
        if self._components is not None:
            return self._components
        assumptions_path = REPO_ROOT / "data" / "jatibarang" / "case_study_assumptions.json"
        design_path = REPO_ROOT / "data" / "jatibarang" / "feature005_seed_design.json"
        assumptions = json.loads(assumptions_path.read_text(encoding="utf-8"))
        routing = assumptions["routing"]
        terrain_path = REPO_ROOT / routing["terrain_raster_path"]
        candidates = assumptions["candidates"]
        source = assumptions["co2_source"]
        self._components = {
            "geology": {
                "preset_id": "jatibarang_proxy_geologies_v1",
                "count": 20,
                "design_sha256": _sha256(design_path) if design_path.exists() else "",
                "ready": design_path.exists(),
            },
            "terrain": {
                "preset_id": "jatibarang_srtm_v1",
                "path": str(terrain_path),
                "expected_sha256": str(routing.get("terrain_sha256", "")).upper(),
                "ready": terrain_path.exists(),
            },
            "supply": {
                "preset_id": "subang_supply_v1",
                "source_id": source["id"],
                "sha256": _json_fingerprint(source),
                "ready": True,
            },
            "well_locations": {
                "preset_id": "jatibarang_w01_w20_v1",
                "count": len(candidates),
                "sha256": _json_fingerprint(candidates),
                "ready": len(candidates) == 20,
            },
        }
        return self._components

    def list_presets(self) -> list[PresetInfo]:
        output = []
        components = self.component_catalog()
        for preset_id, expected in EXPECTED_PRESETS.items():
            manifest_path = self.root / preset_id / "manifest.json"
            if not manifest_path.exists():
                output.append(
                    PresetInfo(
                        preset_id=preset_id,
                        logical_scenarios=expected[0],
                        geology_count=expected[1],
                        schedule_count=expected[2],
                        ready=False,
                        manifest_path=str(manifest_path),
                        reason="manifest is missing",
                        component_catalog=components,
                    )
                )
                continue
            try:
                manifest = PresetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
                payload_path = manifest_path.parent / manifest.payload_file
                dimensions = (
                    manifest.logical_scenarios,
                    manifest.geology_count,
                    manifest.schedule_count,
                )
                dimensions_match = dimensions == expected
                ready = (
                    dimensions_match
                    and payload_path.exists()
                    and _sha256(payload_path) == manifest.payload_sha256.upper()
                )
                reason = ""
                if not dimensions_match:
                    reason = f"manifest dimensions {dimensions} do not match expected {expected}"
                elif not ready:
                    reason = "payload is missing or its SHA-256 does not match"
                output.append(
                    PresetInfo(
                        preset_id=preset_id,
                        logical_scenarios=manifest.logical_scenarios,
                        geology_count=manifest.geology_count,
                        schedule_count=manifest.schedule_count,
                        ready=ready,
                        manifest_path=str(manifest_path),
                        payload_sha256=manifest.payload_sha256,
                        reason=reason,
                        component_catalog=components,
                    )
                )
            except Exception as exc:
                output.append(
                    PresetInfo(
                        preset_id=preset_id,
                        logical_scenarios=expected[0],
                        geology_count=expected[1],
                        schedule_count=expected[2],
                        ready=False,
                        manifest_path=str(manifest_path),
                        reason=f"invalid manifest: {exc}",
                        component_catalog=components,
                    )
                )
        return output

    def resolve(self, preset_id: str) -> InlineScreenRequest | CompactPresetBank:
        if preset_id not in EXPECTED_PRESETS:
            raise KeyError(f"unknown preset: {preset_id}")
        manifest_path = self.root / preset_id / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"preset {preset_id} is unavailable: manifest is missing")
        try:
            manifest = PresetManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise PresetUnavailableError(f"preset {preset_id} manifest is invalid: {exc}") from exc
        dimensions = (
            manifest.logical_scenarios,
            manifest.geology_count,
            manifest.schedule_count,
        )
        if dimensions != EXPECTED_PRESETS[preset_id]:
            raise PresetUnavailableError(
                f"preset {preset_id} manifest dimensions {dimensions} do not match "
                f"{EXPECTED_PRESETS[preset_id]}"
            )
        payload_path = manifest_path.parent / manifest.payload_file
        if not payload_path.exists():
            raise FileNotFoundError(f"preset {preset_id} is unavailable: payload is missing")
        actual = _sha256(payload_path)
        if actual != manifest.payload_sha256.upper():
            raise PresetUnavailableError(f"preset {preset_id} payload SHA-256 mismatch")
        with np.load(payload_path, allow_pickle=False) as payload:
            keys = set(payload.files)
            if "metadata_json_utf8" in keys:
                try:
                    bank = CompactPresetBank(payload_path)
                except Exception as exc:
                    raise PresetUnavailableError(
                        f"preset {preset_id} compact payload is invalid: {exc}"
                    ) from exc
                if bank.logical_scenario_count != manifest.logical_scenarios:
                    bank.close()
                    raise PresetUnavailableError(
                        "preset manifest logical scenario count does not match payload"
                    )
                return bank
            if "request_json_utf8" not in keys:
                raise PresetUnavailableError(
                    "preset payload is missing a supported request metadata record"
                )
            encoded = np.asarray(payload["request_json_utf8"], dtype=np.uint8).tobytes()
        try:
            request = InlineScreenRequest.model_validate_json(encoded.decode("utf-8"))
        except Exception as exc:
            raise PresetUnavailableError(
                f"preset {preset_id} inline payload is invalid: {exc}"
            ) from exc
        if len(materialize_inline_scenarios(request)) != manifest.logical_scenarios:
            raise PresetUnavailableError("preset manifest logical scenario count does not match payload")
        return request
