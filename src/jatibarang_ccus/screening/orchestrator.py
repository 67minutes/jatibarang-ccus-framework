from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from threading import Event
import tempfile
from time import perf_counter
from typing import Any, Callable, Iterable, Iterator, Mapping, MutableMapping
from uuid import uuid4

import numpy as np

from jatibarang_ccus.contracts import (
    EconomicBatchRequest,
    EconomicBatchResult,
    EconomicProvenance,
    FacilityEconomicInput,
    FacilityPortfolioRequest,
    FacilityProvenance,
    FlatDeliveredSupplyCost,
    PipelineDesignRequest,
    PipelineWellDemand,
    PortfolioEconomicInput,
    RouteLibraryRequest,
    SupplyComparisonRequest,
)
from jatibarang_ccus.infrastructure.economic_adapters import (
    DEFAULT_ECONOMIC_BASIS,
    annualize_prediction,
    apply_facility_surface_loss,
    basis_provenance,
    combine_portfolios,
    facility_for_well,
    load_economic_basis,
    pipeline_raw_supply,
    trucking_raw_supply,
    uncertainty_from_prediction,
)
from jatibarang_ccus.infrastructure.economics import evaluate_economic_batch
from jatibarang_ccus.infrastructure.facility import (
    DEFAULT_COST_BASIS,
    DEFAULT_DESIGN_BASIS,
    evaluate_facility_portfolio,
)
from jatibarang_ccus.infrastructure.pipeline import assert_solver_available, solve_pipeline_design
from jatibarang_ccus.infrastructure.routing import build_route_library
from jatibarang_ccus.infrastructure.supply import evaluate_trucking_supply
from jatibarang_ccus.imports.roads import compute_trucking_legs
from jatibarang_ccus.phase1.case_study import load_assumptions
from jatibarang_ccus.surrogate.config import REPO_ROOT
from jatibarang_ccus.surrogate.postprocessing import build_prediction_result
from jatibarang_ccus.surrogate.preprocessing import compile_request
from jatibarang_ccus.surrogate.schemas import Grid2D, PredictionResult, SpatialFrame

from .adapters import (
    discounted_supply_cost,
    facility_well_from_prediction,
    interference_report,
    pipeline_demand_from_prediction,
    prediction_source_class,
)
from .presets import CompactPresetBank, PresetRegistry, _sha256, materialize_inline_scenarios
from .progress import RunRegistry
from .schemas import (
    CarbonPricePlan,
    CachePopulationMetrics,
    CachePopulationResult,
    CrossPriceComparison,
    CrossPriceTransition,
    HealthResponse,
    InlineScreenRequest,
    InterferenceReport,
    MaterializedScenario,
    PresetInfo,
    PresetScreenRequest,
    ProgressEvent,
    ReservoirBaselineState,
    ReservoirFieldMetadata,
    ReservoirGridGeometry,
    ReservoirStaticFields,
    ReservoirVisualization,
    RunTimings,
    ScreenFlag,
    ScreenRequest,
    ScreenResult,
    SelectionDiscrepancyAudit,
    TruckingCounterfactual,
    TruckingRoutePreview,
    ValidationShortlistItem,
    WellStrategyResult,
)


SURROGATE_CHUNK_SIZE = 64
ECONOMIC_CHUNK_SIZE = 256
LEGACY_TERRAIN_ID = "jatibarang_srtm_v1"


def resolve_terrain_path(
    terrain_id: str,
    *,
    routing_assumptions: dict[str, Any] | None = None,
    registry: Any | None = None,
) -> Path:
    """Resolve the legacy terrain or a hash-registered imported terrain.

    Imported ids fail loudly rather than falling back to the paper/demo raster.
    The optional arguments keep this pure enough for isolated registry tests.
    """

    if terrain_id == LEGACY_TERRAIN_ID:
        routing = routing_assumptions or load_assumptions()["routing"]
        configured = Path(routing["terrain_raster_path"])
        return configured if configured.is_absolute() else REPO_ROOT / configured

    if registry is None:
        from ..imports.terrain import TerrainRegistry

        registry = TerrainRegistry(REPO_ROOT / "data" / "imports")
    try:
        return Path(registry.get(terrain_id).source_path)
    except KeyError as exc:
        raise ValueError(f"unknown terrain_id: {terrain_id}") from exc


def resolve_road_graph(road_network_id: str | None) -> Any | None:
    """Resolve an imported road graph; None selects the offline estimate."""

    if not road_network_id:
        return None
    from ..imports.roads import RoadsRegistry

    try:
        return RoadsRegistry(REPO_ROOT / "data" / "imports").graph(
            road_network_id
        )
    except (KeyError, FileNotFoundError) as exc:
        raise ValueError(f"unknown road_network_id: {road_network_id}") from exc


def routing_assumptions_for_terrain(
    terrain_id: str,
    base: dict[str, Any],
    *,
    registry: Any | None = None,
) -> dict[str, Any]:
    """Clone routing assumptions and bind them to the requested terrain hash."""

    assumptions = json.loads(json.dumps(base))
    path = resolve_terrain_path(
        terrain_id,
        routing_assumptions=assumptions,
        registry=registry,
    )
    if terrain_id != LEGACY_TERRAIN_ID:
        assumptions["terrain_raster_path"] = str(path)
        assumptions["terrain_sha256"] = _sha256(path)
    return assumptions


class ScreeningCancelled(RuntimeError):
    """Internal cooperative cancellation sentinel."""


@dataclass(frozen=True)
class ScreeningServices:
    route_builder: Callable = build_route_library
    pipeline_solver: Callable = solve_pipeline_design
    facility_evaluator: Callable = evaluate_facility_portfolio
    economic_evaluator: Callable = evaluate_economic_batch
    trucking_evaluator: Callable = evaluate_trucking_supply
    solver_checker: Callable = assert_solver_available


@dataclass(frozen=True)
class _ScenarioRecord:
    scenario_id: str
    candidate_id: str
    geology_id: str
    location: Any
    produced_co2: Any
    schedule: Any
    input_fingerprint: str
    seed_source_class: str
    seed_source_id: str


def _chunks(values: list[Any], size: int) -> Iterable[list[Any]]:
    for index in range(0, len(values), size):
        yield values[index : index + size]


def _iter_chunks(values: Iterable[Any], size: int) -> Iterator[list[Any]]:
    chunk = []
    for value in values:
        chunk.append(value)
        if len(chunk) == size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def _canonical_fingerprint(value: Any) -> str:
    if hasattr(value, "model_dump"):
        value = value.model_dump(mode="json")
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def _empty_interference() -> InterferenceReport:
    return InterferenceReport(well_ids=[], matrix=[], flagged_pairs=[])


class _DetailedFieldStore:
    """Spill retained spatial outputs to disk so full presets stay below the RSS gate."""

    def __init__(self, *, enabled: bool) -> None:
        self.enabled = enabled
        self._temporary = tempfile.TemporaryDirectory(prefix="jatibarang-feature005-") if enabled else None

    def save(self, fingerprint: str, compiled: Any, prediction: Any, materialized: MaterializedScenario) -> None:
        if not self.enabled or self._temporary is None:
            return
        geology = materialized.predict_request.geology
        np.savez(
            Path(self._temporary.name) / f"{fingerprint}.npz",
            seed_pressure=np.asarray(compiled.seed_pressure_bar, dtype=np.float32),
            seed_gas=np.asarray(compiled.seed_gas_saturation, dtype=np.float32),
            seed_z=np.asarray(compiled.seed_z_co2, dtype=np.float32),
            forecast_pressure=np.asarray(prediction.pred_pressure_bar, dtype=np.float32),
            forecast_gas=np.asarray(prediction.pred_normalized[:, 1], dtype=np.float32),
            forecast_z=np.asarray(prediction.pred_normalized[:, 2], dtype=np.float32),
            forecast_oil=np.asarray(prediction.pred_normalized[:, 3], dtype=np.float32),
            permeability_md=geology.permeability_md.as_array(),
            porosity_fraction=geology.porosity_fraction.as_array(),
            structure_m=geology.structure_m.as_array(),
            fracture_proxy=geology.fracture_proxy.as_array(),
            barrier=geology.barrier.as_array(),
            facies=geology.facies.as_array(),
            well_mask=geology.well_mask.as_array(),
            completion_mask=geology.completion_mask.as_array(),
            # Dynamic display deltas are referenced to the final warm-start
            # frame (t=7), exactly where the free surrogate rollout begins.
            # The request initial state is still carried by the prediction
            # contract, but it is not the relevant comparison datum here.
            baseline_pressure_bar=np.asarray(compiled.seed_pressure_bar[-1], dtype=np.float32),
            baseline_gas_saturation=np.asarray(
                compiled.seed_gas_saturation[-1], dtype=np.float32
            ),
            baseline_z_co2=np.asarray(compiled.seed_z_co2[-1], dtype=np.float32),
            geometry=np.asarray(
                [geology.length_x_m, geology.length_y_m, geology.thickness_m],
                dtype=np.float64,
            ),
        )

    def attach(self, fingerprint: str, compact: Any, *, scenario_id: str) -> Any:
        if not self.enabled or self._temporary is None:
            return compact.model_copy(update={"scenario_id": scenario_id})
        path = Path(self._temporary.name) / f"{fingerprint}.npz"
        with np.load(path, allow_pickle=False) as arrays:
            fields = [
                SpatialFrame(
                    step_index=index,
                    pressure_bar=Grid2D.from_array(arrays["seed_pressure"][index]),
                    gas_saturation=Grid2D.from_array(arrays["seed_gas"][index]),
                    z_co2=Grid2D.from_array(arrays["seed_z"][index]),
                    oil_saturation=None,
                    origin="seed",
                )
                for index in range(8)
            ]
            fields.extend(
                SpatialFrame(
                    step_index=8 + index,
                    pressure_bar=Grid2D.from_array(arrays["forecast_pressure"][index]),
                    gas_saturation=Grid2D.from_array(arrays["forecast_gas"][index]),
                    z_co2=Grid2D.from_array(arrays["forecast_z"][index]),
                    oil_saturation=Grid2D.from_array(arrays["forecast_oil"][index]),
                    origin="surrogate",
                )
                for index in range(len(arrays["forecast_pressure"]))
            )
        return compact.model_copy(update={"scenario_id": scenario_id, "fields": fields})

    def reservoir(
        self,
        fingerprint: str,
        *,
        scenario_id: str,
        geology_id: str,
        seed_source_class: str,
        seed_source_id: str,
    ) -> ReservoirVisualization:
        if not self.enabled or self._temporary is None:
            raise RuntimeError("detailed reservoir fields were not retained")
        path = Path(self._temporary.name) / f"{fingerprint}.npz"
        with np.load(path, allow_pickle=False) as arrays:
            static_arrays = {
                name: np.asarray(arrays[name], dtype=np.float32)
                for name in (
                    "permeability_md",
                    "porosity_fraction",
                    "structure_m",
                    "fracture_proxy",
                    "barrier",
                    "facies",
                    "well_mask",
                    "completion_mask",
                )
            }
            baseline_arrays = {
                "pressure_bar": np.asarray(arrays["baseline_pressure_bar"], dtype=np.float32),
                "gas_saturation": np.asarray(
                    arrays["baseline_gas_saturation"], dtype=np.float32
                ),
                "z_co2": np.asarray(arrays["baseline_z_co2"], dtype=np.float32),
            }
            display_arrays = {
                "pressure_bar": np.concatenate(
                    (arrays["seed_pressure"], arrays["forecast_pressure"]), axis=0
                ).astype(np.float32)
                - baseline_arrays["pressure_bar"][None, :, :],
                "gas_saturation": np.concatenate(
                    (arrays["seed_gas"], arrays["forecast_gas"]), axis=0
                ).astype(np.float32),
                "z_co2": np.concatenate(
                    (arrays["seed_z"], arrays["forecast_z"]), axis=0
                ).astype(np.float32),
            }
            length_x_m, length_y_m, thickness_m = arrays["geometry"].astype(float).tolist()

        static_source = (
            "mrst_derived_geology"
            if seed_source_class == "mrst_ground_truth"
            else "surrogate_input_proxy"
        )
        metadata_specs = {
            "permeability_md": ("Permeability", "mD", "log10", static_source),
            "porosity_fraction": ("Porosity", "fraction", "linear", static_source),
            "structure_m": ("Relative structure", "m", "linear", static_source),
            "fracture_proxy": ("Fracture proxy", "fraction", "linear", static_source),
            "barrier": ("Barrier", "fraction", "binary", static_source),
            "facies": ("Facies", "code", "categorical", static_source),
            "well_mask": ("Well mask", "fraction", "binary", static_source),
            "completion_mask": ("Completion mask", "fraction", "binary", static_source),
            "pressure_bar": ("Pressure change from final warm start", "bar", "linear", "seed_and_surrogate_prediction"),
            "gas_saturation": ("Gas saturation", "fraction", "linear", "seed_and_surrogate_prediction"),
            "z_co2": ("CO2 composition", "fraction", "linear", "seed_and_surrogate_prediction"),
        }
        all_arrays = {**static_arrays, **display_arrays}
        field_metadata = {
            name: ReservoirFieldMetadata(
                label=label,
                unit=unit,
                minimum=float(np.min(all_arrays[name])),
                maximum=float(np.max(all_arrays[name])),
                scale=scale,
                source_class=source_class,
            )
            for name, (label, unit, scale, source_class) in metadata_specs.items()
        }
        return ReservoirVisualization(
            scenario_id=scenario_id,
            geology_id=geology_id,
            grid=ReservoirGridGeometry(
                length_x_m=length_x_m,
                length_y_m=length_y_m,
                thickness_m=thickness_m,
            ),
            static_fields=ReservoirStaticFields(
                **{
                    name: Grid2D.from_array(values)
                    for name, values in static_arrays.items()
                }
            ),
            baseline_state=ReservoirBaselineState(
                pressure_bar=Grid2D.from_array(baseline_arrays["pressure_bar"]),
                gas_saturation=Grid2D.from_array(baseline_arrays["gas_saturation"]),
                z_co2=Grid2D.from_array(baseline_arrays["z_co2"]),
            ),
            field_metadata=field_metadata,
            provenance={
                "coordinate_reference": "local_proxy_grid",
                "geometry_source_class": static_source,
                "baseline_source_class": seed_source_class,
                "baseline_source_id": seed_source_id,
                "baseline_frame_index": 7,
                "baseline_semantics": "final_warm_start_frame",
                "vertical_layers": 1,
                "surveyed_orientation": False,
            },
        )

    def cleanup(self) -> None:
        if self._temporary is not None:
            self._temporary.cleanup()


def _selection_comparison(plans: list[CarbonPricePlan]) -> CrossPriceComparison:
    selection = {plan.carbon_price_scenario_id: plan.selected_wells for plan in plans}
    transitions = []
    for previous, current in zip(plans, plans[1:]):
        previous_ids = set(previous.selected_wells)
        current_ids = set(current.selected_wells)
        transitions.append(
            CrossPriceTransition(
                from_scenario_id=previous.carbon_price_scenario_id,
                to_scenario_id=current.carbon_price_scenario_id,
                entrants=sorted(current_ids - previous_ids),
                exits=sorted(previous_ids - current_ids),
            )
        )
    return CrossPriceComparison(
        selection_by_carbon_price=selection,
        transitions=transitions,
        pivot_observed=any(item.entrants or item.exits for item in transitions),
    )


class ScreeningOrchestrator:
    def __init__(
        self,
        runner: Any,
        *,
        assumptions: dict[str, Any] | None = None,
        economic_basis: dict[str, Any] | None = None,
        preset_registry: PresetRegistry | None = None,
        services: ScreeningServices | None = None,
        run_registry: RunRegistry | None = None,
    ) -> None:
        self.runner = runner
        self.assumptions = assumptions or load_assumptions()
        self.economic_basis = economic_basis or load_economic_basis()
        self.presets = preset_registry or PresetRegistry()
        self.services = services or ScreeningServices()
        self.runs = run_registry or RunRegistry(max_active=1)

    def list_presets(self) -> list[PresetInfo]:
        return self.presets.list_presets()

    def health(self) -> HealthResponse:
        solver_available = True
        solver_reason = ""
        solver = str(self.assumptions.get("pipeline", {}).get("solver", "cbc"))
        try:
            self.services.solver_checker(solver)
        except Exception as exc:
            solver_available = False
            solver_reason = str(exc)
        terrain_path = REPO_ROOT / self.assumptions["routing"]["terrain_raster_path"]
        expected_terrain_sha = str(self.assumptions["routing"].get("terrain_sha256", "")).upper()
        actual_terrain_sha = _sha256(terrain_path) if terrain_path.exists() else ""
        terrain_ready = terrain_path.exists() and (
            not expected_terrain_sha or actual_terrain_sha == expected_terrain_sha
        )
        basis_paths = [
            Path(DEFAULT_DESIGN_BASIS),
            Path(DEFAULT_COST_BASIS),
            Path(DEFAULT_ECONOMIC_BASIS),
        ]
        surrogate_loaded = hasattr(self.runner, "checkpoint")
        preset_info = self.list_presets()
        core_ready = (
            surrogate_loaded
            and solver_available
            and terrain_ready
            and all(path.exists() for path in basis_paths)
        )
        return HealthResponse(
            status="ready" if core_ready else "degraded",
            surrogate_loaded=surrogate_loaded,
            solver_available=solver_available,
            active_runs=self.runs.active_count,
            presets=preset_info,
            details={
                "solver": solver,
                "solver_reason": solver_reason,
                "terrain_path": str(terrain_path),
                "terrain_ready": terrain_ready,
                "terrain_sha256": actual_terrain_sha,
                "expected_terrain_sha256": expected_terrain_sha,
                "facility_design_basis": str(basis_paths[0]),
                "facility_cost_basis": str(basis_paths[1]),
                "economic_basis": str(basis_paths[2]),
                "basis_sha256": {
                    str(path): _sha256(path) if path.exists() else "" for path in basis_paths
                },
                "bases_ready": all(path.exists() for path in basis_paths),
                "economic_basis_version": self.economic_basis.get("version", ""),
                "checkpoint": self.runner.info_dict() if hasattr(self.runner, "info_dict") else {},
            },
        )

    def cancel(self, run_id: str) -> bool:
        return self.runs.cancel(run_id)

    def _resolve_request(self, request: ScreenRequest) -> InlineScreenRequest | CompactPresetBank:
        readiness = self.health()
        if readiness.status != "ready":
            raise EnvironmentError(
                "screening runtime dependencies are unavailable: "
                + json.dumps(readiness.details, sort_keys=True, default=str)
            )
        if isinstance(request, InlineScreenRequest):
            resolved = request
        else:
            resolved = self.presets.resolve(request.preset_id)
            if isinstance(resolved, CompactPresetBank):
                resolved.configure(request)
                self.services.solver_checker(
                    str(self.assumptions["pipeline"].get("solver", "cbc"))
                )
                return resolved
            updates = request.model_dump(
                exclude={"mode", "preset_id", "carbon_price_scenario_ids", "fiscal_case_ids"}
            )
            carbon_prices = resolved.carbon_prices
            fiscal_cases = resolved.fiscal_cases
            if request.carbon_price_scenario_ids is not None:
                requested = set(request.carbon_price_scenario_ids)
                carbon_prices = [item for item in carbon_prices if item.scenario_id in requested]
                missing = requested - {item.scenario_id for item in carbon_prices}
                if missing:
                    raise ValueError(f"preset does not define carbon-price scenarios: {sorted(missing)}")
            if request.fiscal_case_ids is not None:
                requested = set(request.fiscal_case_ids)
                fiscal_cases = [item for item in fiscal_cases if item.case_id in requested]
                missing = requested - {item.case_id for item in fiscal_cases}
                if missing:
                    raise ValueError(f"preset does not define fiscal cases: {sorted(missing)}")
            resolved = InlineScreenRequest.model_validate(
                {
                    **resolved.model_dump(mode="json"),
                    **updates,
                    "carbon_prices": [item.model_dump(mode="json") for item in carbon_prices],
                    "fiscal_cases": [item.model_dump(mode="json") for item in fiscal_cases],
                }
            )
        self.services.solver_checker(str(self.assumptions["pipeline"].get("solver", "cbc")))
        materialize_inline_scenarios(resolved)
        return resolved

    def stream(self, request: ScreenRequest) -> Iterator[ProgressEvent]:
        run_id = request.run_id or uuid4().hex
        token = self.runs.register(run_id)
        try:
            resolved = self._resolve_request(request)
        except Exception:
            self.runs.finish(run_id)
            raise

        def guarded() -> Iterator[ProgressEvent]:
            sequence = 0
            try:
                for event in self._execute(run_id, request, resolved, token):
                    sequence = event.sequence + 1
                    yield event
            except ScreeningCancelled:
                yield ProgressEvent(
                    run_id=run_id,
                    sequence=sequence,
                    event="cancelled",
                    stage="cancelled",
                    message="cooperative cancellation completed",
                )
            except Exception as exc:
                yield ProgressEvent(
                    run_id=run_id,
                    sequence=sequence,
                    event="error",
                    stage="failed",
                    message=str(exc),
                    payload={"exception_type": type(exc).__name__},
                )
            finally:
                if isinstance(resolved, CompactPresetBank):
                    resolved.close()
                self.runs.finish(run_id)

        return guarded()

    def run(self, request: ScreenRequest) -> ScreenResult:
        terminal: ProgressEvent | None = None
        for event in self.stream(request):
            if event.event in {"result", "error", "cancelled"}:
                terminal = event
        if terminal is None:
            raise RuntimeError("screening event pipeline ended without a terminal event")
        if terminal.event == "result":
            return ScreenResult.model_validate(terminal.payload["result"])
        if terminal.event == "cancelled":
            raise RuntimeError("screening run was cancelled")
        raise RuntimeError(terminal.message)

    def run_with_prediction_cache(
        self,
        request: InlineScreenRequest,
        prediction_cache: Mapping[str, PredictionResult],
    ) -> ScreenResult:
        """Re-run logistics, facilities, and economics without surrogate calls.

        Cache keys are the location-independent geology/seed/schedule input
        fingerprints produced by ``materialize_inline_scenarios``.  This is the
        Feature 007 Arm C boundary: assignment re-labels physical wells while
        the 3,240 rollout values remain immutable.
        """

        if request.detailed_top_k != 0:
            raise ValueError(
                "cached downstream re-solves require detailed_top_k=0; spatial fields are not in the compact rollout cache"
            )
        resolved = self._resolve_request(request)
        if not isinstance(resolved, InlineScreenRequest):
            raise TypeError("cached downstream re-solves require an inline request")
        run_id = request.run_id or uuid4().hex
        terminal: ProgressEvent | None = None
        for event in self._execute(
            run_id,
            request,
            resolved,
            Event(),
            prediction_cache=prediction_cache,
        ):
            if event.event in {"result", "error", "cancelled"}:
                terminal = event
        if terminal is None or terminal.event != "result":
            raise RuntimeError(
                terminal.message if terminal is not None else "cached screening ended without a result"
            )
        return ScreenResult.model_validate(terminal.payload["result"])

    def run_and_populate_prediction_cache(
        self,
        request: PresetScreenRequest,
        prediction_cache: MutableMapping[str, PredictionResult],
    ) -> CachePopulationResult:
        """Run a preset while durably storing only missing compact predictions."""

        if request.detailed_top_k != 0:
            raise ValueError(
                "prediction-cache population requires detailed_top_k=0"
            )
        resolved = self._resolve_request(request)
        if not isinstance(resolved, CompactPresetBank):
            raise TypeError("prediction-cache population requires a compact preset")
        run_id = request.run_id or uuid4().hex
        terminal: ProgressEvent | None = None
        metrics: dict[str, int | float] = {
            "predicted_count": 0,
            "reused_count": 0,
            "prediction_seconds": 0.0,
            "reuse_seconds": 0.0,
        }
        try:
            for event in self._execute(
                run_id,
                request,
                resolved,
                Event(),
                prediction_cache=prediction_cache,
                populate_prediction_cache=True,
                cache_metrics=metrics,
            ):
                if event.event in {"result", "error", "cancelled"}:
                    terminal = event
        finally:
            resolved.close()
        if terminal is None or terminal.event != "result":
            raise RuntimeError(
                terminal.message
                if terminal is not None
                else "cache-populating screening ended without a result"
            )
        content_hash = getattr(prediction_cache, "content_sha256", None)
        cache_sha = (
            str(content_hash())
            if callable(content_hash)
            else hashlib.sha256(
                "\n".join(sorted(prediction_cache)).encode("ascii")
            ).hexdigest().upper()
        )
        return CachePopulationResult(
            screen_result=ScreenResult.model_validate(terminal.payload["result"]),
            cache=CachePopulationMetrics(
                predicted_count=metrics["predicted_count"],
                reused_count=metrics["reused_count"],
                prediction_seconds=metrics["prediction_seconds"],
                reuse_seconds=metrics["reuse_seconds"],
                cache_entry_count=len(prediction_cache),
                cache_content_sha256=cache_sha,
            ),
        )

    def run_preset_with_prediction_cache(
        self,
        request: PresetScreenRequest,
        prediction_cache: Mapping[str, PredictionResult],
        *,
        candidate_realization_map: Mapping[str, str] | None = None,
    ) -> ScreenResult:
        """Re-solve a compact preset assignment with zero surrogate calls."""

        if request.detailed_top_k != 0:
            raise ValueError(
                "cached preset re-solves require detailed_top_k=0"
            )
        resolved = self._resolve_request(request)
        if not isinstance(resolved, CompactPresetBank):
            raise TypeError("cached preset re-solves require a compact preset")
        run_id = request.run_id or uuid4().hex
        terminal: ProgressEvent | None = None
        try:
            for event in self._execute(
                run_id,
                request,
                resolved,
                Event(),
                prediction_cache=prediction_cache,
                candidate_realization_map=(
                    dict(candidate_realization_map)
                    if candidate_realization_map is not None
                    else None
                ),
            ):
                if event.event in {"result", "error", "cancelled"}:
                    terminal = event
        finally:
            resolved.close()
        if terminal is None or terminal.event != "result":
            raise RuntimeError(
                terminal.message
                if terminal is not None
                else "cached preset screening ended without a result"
            )
        return ScreenResult.model_validate(terminal.payload["result"])

    def run_materialized_with_prediction_cache(
        self,
        request: PresetScreenRequest,
        materialized_scenarios: Iterable[MaterializedScenario],
        prediction_cache: Mapping[str, PredictionResult],
    ) -> ScreenResult:
        """Run the shared downstream path over an exact offline scenario set.

        This is used by Arm B, whose two MRST schedules per geology are not a
        Cartesian preset grid. The supplied scenarios still originate from the
        hash-verified compact preset; only their prediction values are swapped.
        """

        if request.detailed_top_k != 0:
            raise ValueError(
                "materialized cache re-solves require detailed_top_k=0"
            )
        resolved = self._resolve_request(request)
        if not isinstance(resolved, CompactPresetBank):
            raise TypeError("materialized cache re-solves require a compact preset")
        scenarios = list(materialized_scenarios)
        if not scenarios:
            resolved.close()
            raise ValueError("materialized cache re-solve requires scenarios")
        run_id = request.run_id or uuid4().hex
        terminal: ProgressEvent | None = None
        try:
            for event in self._execute(
                run_id,
                request,
                resolved,
                Event(),
                prediction_cache=prediction_cache,
                materialized_scenarios=scenarios,
            ):
                if event.event in {"result", "error", "cancelled"}:
                    terminal = event
        finally:
            resolved.close()
        if terminal is None or terminal.event != "result":
            raise RuntimeError(
                terminal.message
                if terminal is not None
                else "materialized cached screening ended without a result"
            )
        return ScreenResult.model_validate(terminal.payload["result"])

    def _economic_results(
        self,
        portfolios: list[PortfolioEconomicInput],
        request: InlineScreenRequest | CompactPresetBank,
        *,
        fiscal_cases: list[Any] | None = None,
    ) -> list[Any]:
        output = []
        for chunk in _chunks(portfolios, ECONOMIC_CHUNK_SIZE):
            result = self.services.economic_evaluator(
                EconomicBatchRequest(
                    portfolios=chunk,
                    carbon_prices=request.carbon_prices,
                    fiscal_cases=fiscal_cases or request.fiscal_cases,
                    assumptions=request.economic_assumptions,
                    provenance=basis_provenance(self.economic_basis),
                )
            )
            output.extend(result.results)
        return output

    def _execute(
        self,
        run_id: str,
        original_request: ScreenRequest,
        request: InlineScreenRequest | CompactPresetBank,
        token: Event,
        *,
        prediction_cache: Mapping[str, PredictionResult] | None = None,
        populate_prediction_cache: bool = False,
        candidate_realization_map: Mapping[str, str] | None = None,
        cache_metrics: dict[str, int | float] | None = None,
        materialized_scenarios: Sequence[MaterializedScenario] | None = None,
    ) -> Iterator[ProgressEvent]:
        sequence = 0
        overall_started = perf_counter()
        stages: dict[str, float] = {}

        def event(kind: str, stage: str, **kwargs: Any) -> ProgressEvent:
            nonlocal sequence
            value = ProgressEvent(run_id=run_id, sequence=sequence, event=kind, stage=stage, **kwargs)
            sequence += 1
            return value

        def cancelled() -> None:
            if token.is_set():
                raise ScreeningCancelled()

        request_fingerprint = _canonical_fingerprint(original_request)
        yield event("run_started", "resolve", message="screening request accepted")

        stage_started = perf_counter()
        if materialized_scenarios is not None:
            materialized = list(materialized_scenarios)
            logical_scenario_count = len(materialized)
        elif isinstance(request, CompactPresetBank):
            logical_scenario_count = request.logical_scenario_count
        else:
            materialized = materialize_inline_scenarios(request)
            logical_scenario_count = len(materialized)
        road_graph = resolve_road_graph(
            getattr(request, "road_network_id", None)
        )
        stages["resolve"] = perf_counter() - stage_started
        yield event(
            "stage_completed",
            "resolve",
            completed=logical_scenario_count,
            total=logical_scenario_count,
            message="request, presets, bases, seed coverage, and solver validated",
        )
        cancelled()

        yield event("stage_started", "surrogate", total=logical_scenario_count)
        stage_started = perf_counter()
        compact_by_fingerprint: dict[str, Any] = {}
        cached_mode = prediction_cache is not None
        field_store = _DetailedFieldStore(
            enabled=request.detailed_top_k > 0 and not cached_mode
        )
        scenarios: list[_ScenarioRecord] = []
        prediction_by_scenario: dict[str, Any] = {}
        if cached_mode:
            if populate_prediction_cache and not isinstance(
                prediction_cache, MutableMapping
            ):
                raise TypeError(
                    "prediction-cache population requires a mutable mapping"
                )
            scenario_iterator = (
                iter(materialized)
                if materialized_scenarios is not None
                else
                request.iter_scenarios(
                    dict(candidate_realization_map)
                    if candidate_realization_map is not None
                    else None
                )
                if isinstance(request, CompactPresetBank)
                else iter(materialized)
            )
            loaded_fingerprints: set[str] = set()
            completed = 0
            for materialized_chunk in _iter_chunks(
                scenario_iterator,
                SURROGATE_CHUNK_SIZE,
            ):
                pending: dict[str, MaterializedScenario] = {}
                for item in materialized_chunk:
                    pending.setdefault(item.input_fingerprint, item)
                    scenarios.append(
                        _ScenarioRecord(
                            scenario_id=item.scenario_id,
                            candidate_id=item.candidate_id,
                            geology_id=item.geology_id,
                            location=item.location,
                            produced_co2=item.produced_co2,
                            schedule=item.schedule,
                            input_fingerprint=item.input_fingerprint,
                            seed_source_class=item.predict_request.seed.source_class,
                            seed_source_id=item.predict_request.seed.source_id,
                        )
                    )
                new_items: list[tuple[str, MaterializedScenario]] = []
                for fingerprint, item in pending.items():
                    if fingerprint in loaded_fingerprints:
                        continue
                    cache_lookup_started = perf_counter()
                    if fingerprint in prediction_cache:
                        compact_by_fingerprint[fingerprint] = (
                            PredictionResult.model_validate(
                                prediction_cache[fingerprint]
                            )
                        )
                        if cache_metrics is not None:
                            cache_metrics["reused_count"] += 1
                            cache_metrics["reuse_seconds"] += (
                                perf_counter() - cache_lookup_started
                            )
                    elif populate_prediction_cache:
                        new_items.append((fingerprint, item))
                    else:
                        raise ValueError(
                            "prediction cache is missing input fingerprint: "
                            f"{fingerprint}"
                        )
                    loaded_fingerprints.add(fingerprint)
                if new_items:
                    prediction_started = perf_counter()
                    compiled = [
                        compile_request(
                            item.predict_request,
                            self.runner.checkpoint["stats"],
                        )
                        for _fingerprint, item in new_items
                    ]
                    predictions = self.runner.predict_compiled_batch(
                        compiled,
                        microbatch_size=16,
                    )
                    for (
                        (fingerprint, _scenario),
                        compiled_item,
                        prediction,
                    ) in zip(new_items, compiled, predictions, strict=True):
                        compact = build_prediction_result(
                            compiled_item,
                            prediction,
                            self.runner,
                            include_fields=False,
                        )
                        compact_by_fingerprint[fingerprint] = compact
                        prediction_cache[fingerprint] = compact
                        loaded_fingerprints.add(fingerprint)
                        if cache_metrics is not None:
                            cache_metrics["predicted_count"] += 1
                    if cache_metrics is not None:
                        cache_metrics["prediction_seconds"] += (
                            perf_counter() - prediction_started
                        )
                for item in materialized_chunk:
                    compact = compact_by_fingerprint[
                        item.input_fingerprint
                    ]
                    prediction_by_scenario[item.scenario_id] = (
                        compact
                        if compact.scenario_id == item.scenario_id
                        else compact.model_copy(
                            update={"scenario_id": item.scenario_id}
                        )
                    )
                completed += len(materialized_chunk)
                yield event(
                    "progress",
                    "surrogate",
                    completed=completed,
                    total=logical_scenario_count,
                )
                cancelled()
            if materialized_scenarios is not None or not isinstance(
                request, CompactPresetBank
            ):
                del materialized
        elif isinstance(request, CompactPresetBank):
            completed = 0
            for materialized_chunk in _iter_chunks(
                request.iter_scenarios(), SURROGATE_CHUNK_SIZE
            ):
                pending: dict[str, MaterializedScenario] = {}
                for item in materialized_chunk:
                    pending.setdefault(item.input_fingerprint, item)
                    scenarios.append(
                        _ScenarioRecord(
                            scenario_id=item.scenario_id,
                            candidate_id=item.candidate_id,
                            geology_id=item.geology_id,
                            location=item.location,
                            produced_co2=item.produced_co2,
                            schedule=item.schedule,
                            input_fingerprint=item.input_fingerprint,
                            seed_source_class=item.predict_request.seed.source_class,
                            seed_source_id=item.predict_request.seed.source_id,
                        )
                    )
                new_items = [
                    (fingerprint, item)
                    for fingerprint, item in pending.items()
                    if fingerprint not in compact_by_fingerprint
                ]
                compiled = [
                    compile_request(item.predict_request, self.runner.checkpoint["stats"])
                    for _fingerprint, item in new_items
                ]
                predictions = self.runner.predict_compiled_batch(compiled, microbatch_size=16)
                for (fingerprint, _scenario), compiled_item, prediction in zip(
                    new_items, compiled, predictions, strict=True
                ):
                    compact_by_fingerprint[fingerprint] = build_prediction_result(
                        compiled_item, prediction, self.runner, include_fields=False
                    )
                    field_store.save(fingerprint, compiled_item, prediction, _scenario)
                for item in materialized_chunk:
                    prediction_by_scenario[item.scenario_id] = compact_by_fingerprint[
                        item.input_fingerprint
                    ].model_copy(update={"scenario_id": item.scenario_id})
                completed += len(materialized_chunk)
                yield event(
                    "progress", "surrogate", completed=completed, total=logical_scenario_count
                )
                cancelled()
                del materialized_chunk, pending, new_items, compiled, predictions
            request.close()
        else:
            unique: dict[str, MaterializedScenario] = {}
            for scenario in materialized:
                unique.setdefault(scenario.input_fingerprint, scenario)
            unique_items = list(unique.items())
            completed = 0
            for chunk in _chunks(unique_items, SURROGATE_CHUNK_SIZE):
                compiled = [
                    compile_request(item.predict_request, self.runner.checkpoint["stats"])
                    for _fingerprint, item in chunk
                ]
                predictions = self.runner.predict_compiled_batch(compiled, microbatch_size=16)
                for (fingerprint, _scenario), compiled_item, prediction in zip(
                    chunk, compiled, predictions, strict=True
                ):
                    compact_by_fingerprint[fingerprint] = build_prediction_result(
                        compiled_item, prediction, self.runner, include_fields=False
                    )
                    field_store.save(fingerprint, compiled_item, prediction, _scenario)
                completed += len(chunk)
                yield event("progress", "surrogate", completed=completed, total=len(unique_items))
                cancelled()
            prediction_by_scenario = {
                item.scenario_id: compact_by_fingerprint[item.input_fingerprint].model_copy(
                    update={"scenario_id": item.scenario_id}
                )
                for item in materialized
            }
            scenarios = [
                _ScenarioRecord(
                    scenario_id=item.scenario_id,
                    candidate_id=item.candidate_id,
                    geology_id=item.geology_id,
                    location=item.location,
                    produced_co2=item.produced_co2,
                    schedule=item.schedule,
                    input_fingerprint=item.input_fingerprint,
                    seed_source_class=item.predict_request.seed.source_class,
                    seed_source_id=item.predict_request.seed.source_id,
                )
                for item in materialized
            ]
            del materialized, unique, unique_items, compiled, predictions
        scenario_by_id = {item.scenario_id: item for item in scenarios}
        # This field is the number of unique prediction payloads represented in
        # the result contract, not a live runner call counter. Cached mode keeps
        # that cardinality while its provenance records zero surrogate calls.
        unique_inference_count = len(compact_by_fingerprint)
        if cached_mode:
            # Downstream work is scenario-keyed. Keeping this second dictionary
            # would retain another 3,240 references (and, for remapped
            # assignments, the source-realization objects) for no purpose.
            compact_by_fingerprint.clear()
        stages["surrogate"] = perf_counter() - stage_started
        yield event(
            "stage_completed",
            "surrogate",
            completed=unique_inference_count,
            total=unique_inference_count,
            message=(
                (
                    f"{cache_metrics['predicted_count']} predictions stored and "
                    f"{cache_metrics['reused_count']} reused"
                )
                if populate_prediction_cache and cache_metrics is not None
                else f"{logical_scenario_count} immutable Feature 007 rollout-cache hits"
                if cached_mode
                else f"{logical_scenario_count - unique_inference_count} request-local cache hits"
            ),
        )

        yield event("stage_started", "preliminary_economics", total=len(scenarios))
        stage_started = perf_counter()
        selection_fiscal = next(
            item for item in request.fiscal_cases if item.case_id == request.selection_fiscal_case_id
        )
        preliminary_portfolios: list[PortfolioEconomicInput] = []
        flat_cost = float(self.assumptions["economics"]["delivered_co2_cost_usd_per_tonne"])
        for scenario in scenarios:
            prediction = prediction_by_scenario[scenario.scenario_id]
            periods = annualize_prediction(
                prediction,
                project_life_years=request.project_life_years,
                produced_co2_fraction=scenario.produced_co2.mole_fraction,
            )
            provenance = [
                EconomicProvenance(
                    source_class=prediction_source_class(prediction),
                    source_id=scenario.scenario_id,
                    notes="Shared preliminary schedule economics.",
                )
            ]
            portfolio = PortfolioEconomicInput(
                portfolio_id=scenario.scenario_id,
                evaluation_stage="preliminary",
                project_life_years=request.project_life_years,
                periods=periods,
                supply=FlatDeliveredSupplyCost(
                    delivered_cost_usd_per_tonne=flat_cost,
                    provenance=[
                        EconomicProvenance(
                            source_class="economic_assumption",
                            source_id="feature005-flat-delivered-cost",
                            notes="Pinned preliminary delivered-cost assumption.",
                        )
                    ],
                ),
                facility=FacilityEconomicInput(
                    capex_usd=0.0,
                    annual_opex_usd=[0.0] * request.project_life_years,
                    provenance=[
                        EconomicProvenance(
                            source_class="engineering_assumption",
                            source_id="feature005-preliminary-zero-facility",
                            notes="Facilities are evaluated only after Feature 002 selection.",
                        )
                    ],
                ),
                uncertainty=uncertainty_from_prediction(prediction, periods, self.economic_basis),
                provenance=provenance,
            )
            preliminary_portfolios.append(portfolio)
        preliminary_results = self._economic_results(
            preliminary_portfolios,
            request,
            fiscal_cases=[selection_fiscal],
        )
        preliminary_by_key = {
            (item.portfolio_id, item.carbon_price_scenario_id): item for item in preliminary_results
        }
        prelogistics_by_key = {
            key: result.npv_usd
            + discounted_supply_cost(result.annual_cashflows, request.economic_assumptions.discount_rate)
            for key, result in preliminary_by_key.items()
        }
        scenarios_by_candidate: dict[str, list[_ScenarioRecord]] = defaultdict(list)
        for scenario in scenarios:
            scenarios_by_candidate[scenario.candidate_id].append(scenario)
        best: dict[tuple[str, str], _ScenarioRecord] = {}
        for carbon in request.carbon_prices:
            for candidate_id, candidate_scenarios in scenarios_by_candidate.items():
                best[(carbon.scenario_id, candidate_id)] = max(
                    candidate_scenarios,
                    key=lambda item: (
                        preliminary_by_key[(item.scenario_id, carbon.scenario_id)].npv_usd,
                        item.scenario_id,
                    ),
                )
        stages["preliminary_economics"] = perf_counter() - stage_started
        yield event(
            "stage_completed",
            "preliminary_economics",
            completed=len(scenarios),
            total=len(scenarios),
            message="flat supply was added back before Feature 002 valuation",
        )
        cancelled()

        yield event("stage_started", "routing", total=len(scenarios_by_candidate))
        stage_started = perf_counter()
        routing_carbon = request.carbon_prices[-1].scenario_id
        routing_demands = []
        for candidate_id in sorted(scenarios_by_candidate):
            scenario = best[(routing_carbon, candidate_id)]
            routing_demands.append(
                pipeline_demand_from_prediction(
                    prediction_by_scenario[scenario.scenario_id],
                    schedule=scenario.schedule,
                    location=scenario.location,
                    pre_logistics_value_usd=0.0,
                    project_life_years=request.project_life_years,
                    produced_co2_fraction=scenario.produced_co2.mole_fraction,
                    candidate_id=candidate_id,
                )
            )
        terrain_id = (
            request.terrain_id
            if isinstance(request, InlineScreenRequest)
            else LEGACY_TERRAIN_ID
        )
        routing_assumptions = routing_assumptions_for_terrain(
            terrain_id,
            self.assumptions["routing"],
        )
        route_library = self.services.route_builder(
            RouteLibraryRequest(
                sources=request.sources,
                well_demands=routing_demands,
                routing_assumptions=routing_assumptions,
            )
        )
        stages["routing"] = perf_counter() - stage_started
        yield event(
            "stage_completed",
            "routing",
            completed=len(routing_demands),
            total=len(routing_demands),
            message="one shared route library built",
        )

        _, trucking_distance_provenance, road_distance_legs = compute_trucking_legs(
            request.sources,
            routing_demands,
            road_graph,
        )
        trucking_km_by_candidate = {leg.candidate_id: leg.distance_km for leg in road_distance_legs}

        assumptions = json.loads(json.dumps(self.assumptions))
        assumptions["pipeline"]["minimum_selected_wells"] = 0
        assumptions["economics"]["discount_rate"] = request.economic_assumptions.discount_rate
        assumptions["economics"]["project_life_years"] = request.project_life_years
        plans: list[CarbonPricePlan] = []
        selected_scenarios: set[str] = set()
        total_milp_seconds = 0.0

        for carbon_index, carbon in enumerate(request.carbon_prices, start=1):
            cancelled()
            yield event(
                "stage_started",
                "portfolio",
                completed=carbon_index - 1,
                total=len(request.carbon_prices),
                message=carbon.scenario_id,
            )
            stage_started = perf_counter()
            demands: list[PipelineWellDemand] = []
            for candidate_id in sorted(scenarios_by_candidate):
                scenario = best[(carbon.scenario_id, candidate_id)]
                demands.append(
                    pipeline_demand_from_prediction(
                        prediction_by_scenario[scenario.scenario_id],
                        schedule=scenario.schedule,
                        location=scenario.location,
                        pre_logistics_value_usd=prelogistics_by_key[
                            (scenario.scenario_id, carbon.scenario_id)
                        ],
                        project_life_years=request.project_life_years,
                        produced_co2_fraction=scenario.produced_co2.mole_fraction,
                        candidate_id=candidate_id,
                    )
                )
            demands = [
                item.model_copy(
                    update={"trucking_distance_km": trucking_km_by_candidate.get(item.candidate_id)}
                )
                for item in demands
            ]
            design_request = PipelineDesignRequest(
                objective_mode="max_net_value",
                supply_scenario_id=f"optimized_pipeline--{carbon.scenario_id}",
                sources=request.sources,
                well_demands=demands,
                route_library=route_library,
                annual_co2_budget_tonnes=request.annual_co2_budget_tonnes,
                assumptions=assumptions,
                cost_case=request.cost_case,
                solver=str(assumptions["pipeline"].get("solver", "cbc")),
            )
            pipeline = self.services.pipeline_solver(design_request)
            total_milp_seconds += pipeline.solve_time_seconds
            flags: list[ScreenFlag] = []
            final_batch: EconomicBatchResult | None = None
            facility = None
            trucking = None
            trucking_route_preview = None
            audit = None
            well_strategies: list[WellStrategyResult] = []
            selected = list(pipeline.selected_wells) if pipeline.domain_status == "accepted" else []
            if pipeline.domain_status != "accepted" or not selected:
                _, preview_provenance, preview_legs = compute_trucking_legs(
                    design_request.sources,
                    demands,
                    road_graph,
                )
                trucking_route_preview = TruckingRoutePreview(
                    distance_provenance=preview_provenance,
                    legs=preview_legs,
                )
                flags.append(
                    ScreenFlag(
                        code=pipeline.domain_status,
                        severity="warning",
                        source_module="feature002",
                        message="Feature 002 returned an explicit non-development outcome.",
                    )
                )
            else:
                selected_scenarios.update(
                    best[(carbon.scenario_id, candidate_id)].scenario_id for candidate_id in selected
                )
                trucked_ids = [w for w in selected if pipeline.supply_mode_by_well.get(w) == "trucking"]
                if trucked_ids:
                    flags.append(
                        ScreenFlag(
                            code="pipeline_hydraulically_inadmissible",
                            severity="info",
                            source_module="feature002",
                            message="Pipeline supply is below the minimum admissible hydraulic flow; selected wells are supplied by road transport.",
                        )
                    )
                    _, preview_provenance, preview_legs = compute_trucking_legs(
                        design_request.sources,
                        [d for d in demands if d.candidate_id in trucked_ids],
                        road_graph,
                    )
                    trucking_route_preview = TruckingRoutePreview(
                        distance_provenance=preview_provenance,
                        legs=preview_legs,
                    )
                facility_request = FacilityPortfolioRequest(
                    portfolio_id=f"facility--{carbon.scenario_id}",
                    cost_case=request.cost_case,
                    design_basis_version="1.0.0",
                    cost_basis_version="1.0.0",
                    wells=[
                        facility_well_from_prediction(
                            prediction_by_scenario[best[(carbon.scenario_id, candidate_id)].scenario_id],
                            candidate_id=candidate_id,
                            schedule=best[(carbon.scenario_id, candidate_id)].schedule,
                            delivery_pressure_bar=pipeline.node_pressures_bar.get(candidate_id, 80.0),
                            produced_co2_fraction=best[
                                (carbon.scenario_id, candidate_id)
                            ].produced_co2.mole_fraction,
                            project_life_years=request.project_life_years,
                            assumptions=assumptions,
                        )
                        for candidate_id in selected
                    ],
                    provenance=[
                        FacilityProvenance(
                            source_class="pipeline_result",
                            source_id=f"pipeline--{carbon.scenario_id}",
                            notes="Selected-well delivery pressures and ownership from Feature 002.",
                        )
                    ],
                )
                facility = self.services.facility_evaluator(facility_request)
                if facility.validation_status != "validated":
                    flags.append(
                        ScreenFlag(
                            code=f"facility_{facility.validation_status}",
                            severity="warning",
                            source_module="feature003",
                            scenario_ids=[
                                best[(carbon.scenario_id, item)].scenario_id for item in selected
                            ],
                            message="selected facility portfolio is outside the validated envelope",
                        )
                    )
                facility_by_well = {item.candidate_id: item for item in facility.well_results}
                for well in facility.well_results:
                    for calibration_flag in well.calibration_flags:
                        flags.append(
                            ScreenFlag(
                                code=calibration_flag,
                                severity="warning",
                                source_module="feature003",
                                scenario_ids=[
                                    best[(carbon.scenario_id, well.candidate_id)].scenario_id
                                ],
                                message="Feature 003 calibration qualification",
                            )
                        )
                allocation_total = sum(pipeline.per_well_allocated_cost_usd.get(item, 0.0) for item in selected)
                if allocation_total <= 0:
                    allocation_total = sum(
                        next(d.annual_demand_tonnes for d in demands if d.candidate_id == item)
                        for item in selected
                    )
                    allocations = {
                        item: next(d.annual_demand_tonnes for d in demands if d.candidate_id == item)
                        / allocation_total
                        for item in selected
                    }
                else:
                    allocations = {
                        item: pipeline.per_well_allocated_cost_usd.get(item, 0.0) / allocation_total
                        for item in selected
                    }
                per_well_portfolios: list[PortfolioEconomicInput] = []
                for candidate_id in selected:
                    scenario = best[(carbon.scenario_id, candidate_id)]
                    prediction = prediction_by_scenario[scenario.scenario_id]
                    periods = annualize_prediction(
                        prediction,
                        project_life_years=request.project_life_years,
                        produced_co2_fraction=scenario.produced_co2.mole_fraction,
                    )
                    periods = apply_facility_surface_loss(periods, facility_by_well[candidate_id])
                    per_well_portfolios.append(
                        PortfolioEconomicInput(
                            portfolio_id=f"well--{carbon.scenario_id}--{candidate_id}",
                            evaluation_stage="final",
                            project_life_years=request.project_life_years,
                            periods=periods,
                            supply=pipeline_raw_supply(
                                pipeline,
                                periods,
                                request.project_life_years,
                                allocation_fraction=allocations[candidate_id],
                            ),
                            facility=facility_for_well(
                                facility_by_well[candidate_id], periods, request.project_life_years
                            ),
                            uncertainty=uncertainty_from_prediction(
                                prediction, periods, self.economic_basis
                            ),
                            provenance=[scenario.produced_co2.provenance],
                        )
                    )
                aggregate = combine_portfolios(
                    per_well_portfolios,
                    portfolio_id=f"portfolio--{carbon.scenario_id}",
                    provenance_notes="Aggregate of Feature 005 selected-well final portfolios.",
                )
                final_batch = self.services.economic_evaluator(
                    EconomicBatchRequest(
                        portfolios=[*per_well_portfolios, aggregate],
                        carbon_prices=request.carbon_prices,
                        fiscal_cases=request.fiscal_cases,
                        assumptions=request.economic_assumptions,
                        provenance=basis_provenance(self.economic_basis),
                    )
                )
                final_by_key = {
                    (item.portfolio_id, item.carbon_price_scenario_id, item.fiscal_case_id): item
                    for item in final_batch.results
                }
                aggregate_designated = final_by_key[
                    (
                        aggregate.portfolio_id,
                        carbon.scenario_id,
                        request.selection_fiscal_case_id,
                    )
                ]
                if aggregate_designated.low_confidence:
                    flags.append(
                        ScreenFlag(
                            code="economic_low_confidence",
                            severity="warning",
                            source_module="feature004",
                            scenario_ids=[
                                best[(carbon.scenario_id, item)].scenario_id for item in selected
                            ],
                            message="aggregate final economics carries low-confidence qualifications",
                        )
                    )
                if not aggregate_designated.reconciliation_passed:
                    flags.append(
                        ScreenFlag(
                            code="economic_reconciliation_failed",
                            severity="blocking",
                            source_module="feature004",
                            scenario_ids=[
                                best[(carbon.scenario_id, item)].scenario_id for item in selected
                            ],
                            message="aggregate final economic accounting did not reconcile",
                        )
                    )
                annual_mass = sum(
                    demand.annual_demand_tonnes
                    for demand in demands
                    if demand.candidate_id in selected
                )
                selected_request = design_request.model_copy(
                    update={
                        "well_demands": [item for item in demands if item.candidate_id in selected]
                    }
                )
                selected_demands = [
                    item for item in demands if item.candidate_id in selected
                ]
                weighted_km, distance_provenance, trucking_legs = (
                    compute_trucking_legs(
                        design_request.sources,
                        selected_demands,
                        road_graph,
                    )
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
                trucking_portfolio = aggregate.model_copy(
                    update={
                        "portfolio_id": f"trucking--{carbon.scenario_id}",
                        "supply": trucking_raw_supply(trucking_supply),
                    }
                )
                trucking_economics = self.services.economic_evaluator(
                    EconomicBatchRequest(
                        portfolios=[trucking_portfolio],
                        carbon_prices=request.carbon_prices,
                        fiscal_cases=request.fiscal_cases,
                        assumptions=request.economic_assumptions,
                        provenance=basis_provenance(self.economic_basis),
                    )
                )
                trucking = TruckingCounterfactual(
                    supply=trucking_supply,
                    economics=trucking_economics,
                )

                audit_demands = []
                value_deltas = {}
                for demand in demands:
                    preliminary_value = demand.pre_logistics_value_usd
                    refined_value = preliminary_value
                    if demand.candidate_id in selected:
                        portfolio = next(
                            item for item in per_well_portfolios if item.portfolio_id.endswith(f"--{demand.candidate_id}")
                        )
                        designated = final_by_key[
                            (
                                portfolio.portfolio_id,
                                carbon.scenario_id,
                                request.selection_fiscal_case_id,
                            )
                        ]
                        raw = portfolio.supply
                        logistics_pv = raw.pipeline_capex_usd + raw.booster_capex_usd
                        for period in portfolio.periods:
                            year = period.year
                            logistics_pv += (
                                raw.annual_maintenance_usd[year - 1]
                                + raw.annual_booster_energy_usd[year - 1]
                                + raw.commodity_supply_usd_per_tonne * period.injected_co2_tonnes
                            ) / ((1.0 + request.economic_assumptions.discount_rate) ** year)
                        refined_value = designated.npv_usd + logistics_pv
                    value_deltas[demand.candidate_id] = refined_value - preliminary_value
                    audit_demands.append(
                        demand.model_copy(update={"pre_logistics_value_usd": refined_value})
                    )
                audit_request = design_request.model_copy(update={"well_demands": audit_demands})
                audit_result = self.services.pipeline_solver(audit_request)
                total_milp_seconds += audit_result.solve_time_seconds
                audit = SelectionDiscrepancyAudit(
                    original_selected_wells=selected,
                    audit_selected_wells=audit_result.selected_wells,
                    entrants=sorted(set(audit_result.selected_wells) - set(selected)),
                    exits=sorted(set(selected) - set(audit_result.selected_wells)),
                    changed=set(audit_result.selected_wells) != set(selected),
                    original_objective_usd=pipeline.objective_value_usd,
                    audit_objective_usd=audit_result.objective_value_usd,
                    value_deltas_usd=value_deltas,
                )

            final_result_map = (
                {
                    (item.portfolio_id, item.carbon_price_scenario_id, item.fiscal_case_id): item
                    for item in final_batch.results
                }
                if final_batch is not None
                else {}
            )
            facility_map = (
                {item.candidate_id: item for item in facility.well_results}
                if facility is not None
                else {}
            )
            demand_map = {item.candidate_id: item for item in demands}
            for candidate_id in sorted(scenarios_by_candidate):
                scenario = best[(carbon.scenario_id, candidate_id)]
                prediction = prediction_by_scenario[scenario.scenario_id]
                prediction_flags = []
                if any(item.is_extrapolation for item in prediction.extrapolation_flags):
                    prediction_flags.append(
                        ScreenFlag(
                            code="surrogate_extrapolation",
                            severity="warning",
                            source_module="feature001",
                            scenario_ids=[scenario.scenario_id],
                            message="one or more scheduled inputs lie outside the promoted training envelope",
                        )
                    )
                prediction_flags.extend(
                    ScreenFlag(
                        code=reason,
                        severity="warning",
                        source_module="feature001",
                        scenario_ids=[scenario.scenario_id],
                        message="surrogate confidence qualification",
                    )
                    for reason in prediction.confidence.low_confidence_reasons
                )
                designated = final_result_map.get(
                    (
                        f"well--{carbon.scenario_id}--{candidate_id}",
                        carbon.scenario_id,
                        request.selection_fiscal_case_id,
                    )
                )
                preliminary = preliminary_by_key[(scenario.scenario_id, carbon.scenario_id)]
                well_strategies.append(
                    WellStrategyResult(
                        candidate_id=candidate_id,
                        scenario_id=scenario.scenario_id,
                        schedule=scenario.schedule,
                        selected=candidate_id in selected,
                        annual_demand_tonnes=demand_map[candidate_id].annual_demand_tonnes,
                        peak_mass_flow_kg_s=demand_map[candidate_id].peak_mass_flow_kg_s,
                        preliminary_npv_usd=preliminary.npv_usd,
                        pre_logistics_value_usd=demand_map[candidate_id].pre_logistics_value_usd,
                        prediction=prediction,
                        facility=(facility_map[candidate_id].model_dump(mode="json") if candidate_id in facility_map else None),
                        designated_economics=(designated.model_dump(mode="json") if designated is not None else None),
                        flags=prediction_flags,
                    )
                )
            locations = {item.candidate_id: item.location for item in scenarios}
            radii = {
                candidate_id: prediction_by_scenario[
                    best[(carbon.scenario_id, candidate_id)].scenario_id
                ].plume.influence_radius_m
                for candidate_id in scenarios_by_candidate
            }
            interference = (
                interference_report(
                    well_ids=selected,
                    locations=locations,
                    influence_radii_m=radii,
                )
                if selected
                else _empty_interference()
            )
            if interference.flagged_pairs:
                flags.append(
                    ScreenFlag(
                        code="surrogate_influence_overlap",
                        severity="warning",
                        source_module="feature005",
                        scenario_ids=[best[(carbon.scenario_id, item)].scenario_id for item in selected],
                        message="selected wells contain geodesic influence-radius overlaps",
                        )
                    )
            route_segments_by_id = {
                segment.id: segment for segment in route_library.segments
            }
            selected_route_geometries = []
            for built in pipeline.built_segments:
                routed = route_segments_by_id.get(built.segment_id)
                if routed is None:
                    continue
                selected_route_geometries.append(
                    {
                        "segment_id": built.segment_id,
                        "from_node": built.from_node,
                        "to_node": built.to_node,
                        "geometry": [
                            point.model_dump(mode="json")
                            for point in routed.geometry
                        ],
                        "elevation_m": list(routed.elevation_m),
                        "terrain_sha256": routed.terrain_sha256,
                        "route_method": routed.method,
                    }
                )
            pipeline.route_provenance = {
                **pipeline.route_provenance,
                "selected_route_geometries": selected_route_geometries,
            }
            plans.append(
                CarbonPricePlan(
                    carbon_price_scenario_id=carbon.scenario_id,
                    carbon_price_usd_per_tonne=carbon.carbon_price_usd_per_tonne,
                    domain_status=pipeline.domain_status,
                    selected_wells=selected,
                    pipeline=pipeline,
                    facility=facility,
                    economics=final_batch,
                    trucking_counterfactual=trucking,
                    trucking_route_preview=trucking_route_preview,
                    well_strategies=well_strategies,
                    interference=interference,
                    discrepancy_audit=audit,
                    flags=flags,
                    logistics_mode=(
                        "none"
                        if not selected
                        else (
                            "hybrid"
                            if 0
                            < len([w for w in selected if pipeline.supply_mode_by_well.get(w) == "trucking"])
                            < len(selected)
                            else (
                                "trucking"
                                if pipeline.supply_mode_by_well.get(selected[0]) == "trucking"
                                else "pipeline"
                            )
                        )
                    ),
                )
            )
            for flag in flags:
                yield event(
                    "warning",
                    "portfolio",
                    completed=carbon_index,
                    total=len(request.carbon_prices),
                    message=flag.message,
                    payload={"flag": flag.model_dump(mode="json")},
                )
            stages[f"portfolio:{carbon.scenario_id}"] = perf_counter() - stage_started
            yield event(
                "stage_completed",
                "portfolio",
                completed=carbon_index,
                total=len(request.carbon_prices),
                message=f"{carbon.scenario_id}: {pipeline.domain_status}",
            )

        cross_price = _selection_comparison(plans)
        shortlist_candidates: dict[str, dict[str, Any]] = {}
        for plan in plans:
            for strategy in plan.well_strategies:
                if not strategy.selected:
                    continue
                entry = shortlist_candidates.setdefault(
                    strategy.scenario_id,
                    {
                        "candidate_id": strategy.candidate_id,
                        "prices": [],
                        "npv": None,
                        "designated_price": None,
                        "reasons": ["selected_by_feature002"],
                    },
                )
                entry["prices"].append(plan.carbon_price_scenario_id)
                if strategy.designated_economics is not None:
                    value = float(strategy.designated_economics["npv_usd"])
                    if (
                        entry["npv"] is None
                        or value > entry["npv"]
                        or (
                            value == entry["npv"]
                            and (
                                entry["designated_price"] is None
                                or plan.carbon_price_scenario_id
                                < entry["designated_price"]
                            )
                        )
                    ):
                        entry["npv"] = value
                        entry["designated_price"] = (
                            plan.carbon_price_scenario_id
                        )
                if strategy.prediction.confidence.low_confidence_reasons:
                    entry["reasons"].append("low_surrogate_confidence")
        ranked = sorted(
            shortlist_candidates.items(),
            key=lambda item: (
                -(item[1]["npv"] if item[1]["npv"] is not None else float("-inf")),
                item[0],
            ),
        )[: request.shortlist_top_k]
        shortlist = [
            ValidationShortlistItem(
                rank=index,
                candidate_id=value["candidate_id"],
                scenario_id=scenario_id,
                carbon_price_scenario_ids=value["prices"],
                designated_carbon_price_scenario_id=value["designated_price"],
                designated_npv_usd=value["npv"],
                reasons=list(dict.fromkeys(value["reasons"])),
            )
            for index, (scenario_id, value) in enumerate(ranked, start=1)
        ]
        detail_ids = [item.scenario_id for item in shortlist[: request.detailed_top_k]]
        if len(detail_ids) < request.detailed_top_k:
            detail_ids.extend(
                sorted(selected_scenarios - set(detail_ids))[: request.detailed_top_k - len(detail_ids)]
            )
        # A rational no-development result has no selected wells, but it still
        # needs inspectable reservoir evidence. Fill any remaining detail slots
        # from the real pre-logistics ranking; do not substitute a demo plume or
        # relabel another field in the frontend.
        if len(detail_ids) < request.detailed_top_k:
            preliminary_detail: dict[str, tuple[float, str]] = {}
            for plan in plans:
                for strategy in plan.well_strategies:
                    value = (
                        float(strategy.preliminary_npv_usd)
                        if strategy.preliminary_npv_usd is not None
                        else float("-inf")
                    )
                    previous = preliminary_detail.get(strategy.scenario_id)
                    if previous is None or value > previous[0]:
                        preliminary_detail[strategy.scenario_id] = (value, strategy.candidate_id)
            fallback_ids = sorted(
                (scenario_id for scenario_id in preliminary_detail if scenario_id not in detail_ids),
                key=lambda scenario_id: (
                    -preliminary_detail[scenario_id][0],
                    preliminary_detail[scenario_id][1],
                    scenario_id,
                ),
            )
            detail_ids.extend(fallback_ids[: request.detailed_top_k - len(detail_ids)])
        detailed = {}
        detailed_reservoirs = {}
        for scenario_id in detail_ids:
            scenario = scenario_by_id[scenario_id]
            detailed[scenario_id] = field_store.attach(
                scenario.input_fingerprint,
                compact_by_fingerprint[scenario.input_fingerprint],
                scenario_id=scenario_id,
            )
            detailed_reservoirs[scenario_id] = field_store.reservoir(
                scenario.input_fingerprint,
                scenario_id=scenario_id,
                geology_id=scenario.geology_id,
                seed_source_class=scenario.seed_source_class,
                seed_source_id=scenario.seed_source_id,
            )
        field_store.cleanup()

        failures = [plan for plan in plans if plan.domain_status != "accepted"]
        warnings = []
        if failures:
            warnings.append(
                f"{len(failures)} of {len(plans)} carbon-price plans did not produce an accepted network"
            )
        result = ScreenResult(
            run_id=run_id,
            request_fingerprint=request_fingerprint,
            status="completed_with_failures" if failures else "completed",
            logical_scenario_count=len(scenarios),
            unique_inference_count=unique_inference_count,
            inference_cache_hits=logical_scenario_count - unique_inference_count,
            plans=plans,
            cross_price_comparison=cross_price,
            shortlist=shortlist,
            detailed_predictions=detailed,
            detailed_reservoirs=detailed_reservoirs,
            timings=RunTimings(
                total_seconds=perf_counter() - overall_started,
                stages_seconds=stages,
                milp_solve_seconds=total_milp_seconds,
            ),
            warnings=warnings,
            provenance_catalog={
                "request_sha256": request_fingerprint,
                "checkpoint": self.runner.info_dict() if hasattr(self.runner, "info_dict") else {},
                "route_library_fingerprint": route_library.fingerprint,
                "economic_basis_version": self.economic_basis.get("version"),
                "facility_design_basis": str(DEFAULT_DESIGN_BASIS),
                "facility_cost_basis": str(DEFAULT_COST_BASIS),
                "preset": (
                    original_request.preset_id if isinstance(original_request, PresetScreenRequest) else "inline"
                ),
                "produced_co2_composition": "explicit_per_candidate_provenance_tagged_assumption",
                "pipeline_minimum_selected_wells": 0,
                "surrogate_evaluation_mode": (
                    "runtime_surrogate_inference_with_durable_cache"
                    if populate_prediction_cache
                    else
                    "immutable_prediction_cache_zero_surrogate_calls"
                    if cached_mode
                    else "runtime_surrogate_inference"
                ),
            },
        )
        yield event(
            "result",
            "complete",
            completed=len(plans),
            total=len(plans),
            payload={"result": result.model_dump(mode="json")},
        )


def build_default_orchestrator(runner: Any) -> ScreeningOrchestrator:
    return ScreeningOrchestrator(runner)
