from __future__ import annotations

from contextlib import asynccontextmanager
import gzip
import hashlib
import json
import math
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..imports.launchpads import LaunchpadBankError, load_launchpad_bank
from ..imports.mrst import MrstImportError, load_mrst_reservoir
from ..imports.roads import RoadsImportError, RoadsRegistry
from ..imports.store import ImportStore
from ..imports.terrain import Heightmap, TerrainImportError, TerrainRegistry
from ..screening.progress import RunBusyError, sse_encode
from ..screening.schemas import (
    HealthResponse,
    PresetInfo,
    ReservoirVisualization,
    ScreenRequest,
    ScreenResult,
)

from ..surrogate.metadata import public_metadata
from ..surrogate.postprocessing import build_prediction_result
from ..surrogate.preprocessing import compile_request
from ..surrogate.runner import SurrogateRunner, load_surrogate
from ..surrogate.schemas import (
    BatchPredictRequest,
    BatchPredictionResult,
    PredictRequest,
    PredictionResult,
)


RunnerFactory = Callable[[], SurrogateRunner]
ScreeningFactory = Callable[[SurrogateRunner], Any]

# repo_root/src/jatibarang_ccus/api/app.py -> repo_root
_REPO_ROOT = Path(__file__).resolve().parents[3]
_FRONTEND_DIST = _REPO_ROOT / "frontend" / "dist"


def _mount_frontend(application: FastAPI) -> None:
    """Serve the built screening-workbench SPA from the same process.

    This is packaging only: it exposes the static Vite build at ``/`` so the
    frontend and API share one origin (no CORS, no second process). It is a
    no-op when the SPA has not been built, so the test suite and API-only dev
    keep working. Must be called after all API routes are registered so route
    matching takes precedence over the static mount.
    """
    if not (_FRONTEND_DIST / "index.html").is_file():
        return
    application.mount("/", StaticFiles(directory=_FRONTEND_DIST, html=True), name="app")


class ServerSentEventsResponse(StreamingResponse):
    media_type = "text/event-stream"


def _json_safe_validation_detail(value: Any) -> Any:
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, dict):
        return {key: _json_safe_validation_detail(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_validation_detail(item) for item in value]
    if value is None or isinstance(value, (str, int, bool)):
        return value
    return str(value)


# The import routes take local filesystem paths in JSON bodies by design:
# this is a loopback-only single-user tool and browser file inputs cannot
# carry paths (spec 2026-07-17 §6). That design is safe only while the server
# binds 127.0.0.1 (start_workbench.bat) and no CORS middleware is added.
# _require_local_client keeps the file-reading surface refused if the app is
# ever exposed on a non-loopback interface. Do not relax either guard.
_LOCAL_CLIENT_HOSTS = {"127.0.0.1", "::1", "localhost", "testclient"}


def _require_local_client(request: Request) -> None:
    client = request.client
    if client is not None and client.host not in _LOCAL_CLIENT_HOSTS:
        raise HTTPException(
            status_code=403,
            detail="import endpoints accept local file paths and are loopback-only",
        )


class TerrainImportRequest(BaseModel):
    path: str


class ReservoirImportRequest(BaseModel):
    model_path: str
    bank_path: str | None = None


class ReservoirCatalogEntry(ReservoirImportRequest):
    well_id: str = Field(min_length=1)


class ReservoirCatalogImportRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    entries: list[ReservoirCatalogEntry] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def _unique_wells(self) -> "ReservoirCatalogImportRequest":
        well_ids = [entry.well_id for entry in self.entries]
        if len(well_ids) != len(set(well_ids)):
            raise ValueError("reservoir catalog well IDs must be unique")
        return self


class RoadsImportRequest(BaseModel):
    path: str
    terrain_id: str


class SpatialResultArchive(BaseModel):
    """The cell-scale portion of one result, persisted beside imported inputs."""

    model_config = ConfigDict(extra="forbid")

    request_fingerprint: str = Field(min_length=64, max_length=64)
    detailed_predictions: dict[str, PredictionResult] = Field(min_length=1)
    detailed_reservoirs: dict[str, ReservoirVisualization] = Field(min_length=1)

    @model_validator(mode="after")
    def _aligned_scenarios(self) -> "SpatialResultArchive":
        prediction_ids = set(self.detailed_predictions)
        reservoir_ids = set(self.detailed_reservoirs)
        if prediction_ids != reservoir_ids:
            raise ValueError("spatial prediction and reservoir scenario IDs must match")
        for scenario_id in sorted(prediction_ids):
            prediction = self.detailed_predictions[scenario_id]
            reservoir = self.detailed_reservoirs[scenario_id]
            if prediction.scenario_id != scenario_id or reservoir.scenario_id != scenario_id:
                raise ValueError("spatial archive keys must match embedded scenario IDs")
            if prediction.fields is None:
                raise ValueError("spatial archives require detailed prediction fields")
        return self


def _reservoir_payload(
    model_path: Path,
    model_id: str,
    model_sha: str,
    bank_path: Path | None,
    bank_id: str | None,
    bank_sha: str | None,
) -> dict[str, Any]:
    imported = load_mrst_reservoir(model_path)
    bank = load_launchpad_bank(bank_path) if bank_path is not None else {}
    covered = sorted(
        {imported.seed.schedule_fingerprint, *bank.keys()}
    )
    return {
        "model_id": model_id,
        "sha256": model_sha,
        "source_file": model_path.name,
        "geology": imported.geology.model_dump(),
        "native_schedule": imported.schedule.model_dump(),
        "native_fingerprint": imported.seed.schedule_fingerprint,
        "native_seed": imported.seed.model_dump(mode="json"),
        "bank_seeds": {
            fingerprint: seed.model_dump(mode="json")
            for fingerprint, seed in sorted(bank.items())
        },
        "well_ij": list(imported.well_ij),
        "completion_ij": [list(pair) for pair in imported.completion_ij],
        "launchpads": {
            "bank_id": bank_id,
            "bank_sha256": bank_sha,
            "covered_fingerprints": covered,
        },
    }


def create_app(
    runner_factory: RunnerFactory = load_surrogate,
    *,
    screening_factory: ScreeningFactory | None = None,
    terrain_registry: TerrainRegistry | None = None,
    import_store: ImportStore | None = None,
    roads_registry: RoadsRegistry | None = None,
) -> FastAPI:
    registry = terrain_registry or TerrainRegistry(_REPO_ROOT / "data" / "imports")
    artifacts = import_store or ImportStore(_REPO_ROOT / "data" / "imports")
    roads = roads_registry or RoadsRegistry(_REPO_ROOT / "data" / "imports")

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        application.state.surrogate = runner_factory()
        if screening_factory is None:
            from ..screening.orchestrator import build_default_orchestrator

            application.state.screening = build_default_orchestrator(application.state.surrogate)
        else:
            application.state.screening = screening_factory(application.state.surrogate)
        yield

    application = FastAPI(
        title="Jatibarang CCUS Surrogate API",
        version="0.1.0",
        lifespan=lifespan,
    )

    def store_reservoir(payload: ReservoirImportRequest) -> dict[str, Any]:
        try:
            model_path = Path(payload.model_path)
            load_mrst_reservoir(model_path)
        except MrstImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        stored = artifacts.put(model_path)
        bank_id = bank_sha = None
        bank_path = None
        if payload.bank_path:
            try:
                bank_path = Path(payload.bank_path)
                load_launchpad_bank(bank_path)
            except LaunchpadBankError as exc:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            stored_bank = artifacts.put(bank_path)
            bank_id, bank_sha = stored_bank.artifact_id, stored_bank.sha256
            stored_bank_path = stored_bank.path
        else:
            stored_bank_path = None
        return _reservoir_payload(
            stored.path,
            stored.artifact_id,
            stored.sha256,
            stored_bank_path,
            bank_id,
            bank_sha,
        )

    @application.exception_handler(RequestValidationError)
    async def request_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        detail = []
        for error in exc.errors():
            item = {
                "type": error.get("type", "value_error"),
                "loc": list(error.get("loc", ())),
                "msg": error.get("msg", "invalid request"),
            }
            if "ctx" in error:
                item["ctx"] = _json_safe_validation_detail(error["ctx"])
            detail.append(item)
        return JSONResponse(
            status_code=422,
            content={"detail": detail},
        )

    def runner(request: Request) -> SurrogateRunner:
        value = getattr(request.app.state, "surrogate", None)
        if value is None:
            raise HTTPException(status_code=503, detail="surrogate checkpoint is not loaded")
        return value

    def screening(request: Request) -> Any:
        value = getattr(request.app.state, "screening", None)
        if value is None:
            raise HTTPException(status_code=503, detail="screening dependencies are not initialized")
        return value

    def screening_error(exc: Exception) -> HTTPException:
        if isinstance(exc, RunBusyError):
            return HTTPException(status_code=429, detail=str(exc))
        if isinstance(exc, (FileNotFoundError, OSError)):
            return HTTPException(status_code=503, detail=str(exc))
        return HTTPException(status_code=422, detail=str(exc))

    @application.get(
        "/model/info",
        summary="Report the promoted model contract and evidence",
        responses={200: {"description": "Model metadata"}},
    )
    def model_info(request: Request) -> dict[str, Any]:
        active = runner(request)
        payload = active.info_dict()
        payload["normalization_stats"] = dict(active.checkpoint["stats"])
        payload.update(public_metadata())
        return payload

    @application.post(
        "/predict",
        response_model=PredictionResult,
        summary="Run one detailed warm-start surrogate forecast",
        responses={
            200: {"description": "Detailed prediction"},
            422: {"description": "Invalid physical or structural input"},
        },
    )
    def predict(payload: PredictRequest, request: Request) -> PredictionResult:
        active = runner(request)
        try:
            compiled = compile_request(payload, active.checkpoint["stats"])
            prediction = active.predict_compiled(compiled)
            return build_prediction_result(compiled, prediction, active, include_fields=True)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post(
        "/predict/batch",
        response_model=BatchPredictionResult,
        summary="Run 1-256 compact warm-start forecasts",
        responses={
            200: {"description": "Compact results plus selected full fields"},
            422: {"description": "Invalid registry, scenario, or selection"},
        },
    )
    def predict_batch(payload: BatchPredictRequest, request: Request) -> BatchPredictionResult:
        active = runner(request)
        started = perf_counter()
        try:
            compiled = []
            for scenario in payload.scenarios:
                single = PredictRequest(
                    scenario_id=scenario.scenario_id,
                    geology=payload.geologies[scenario.geology_id],
                    schedule=scenario.schedule,
                    seed=payload.seeds[scenario.seed_id],
                )
                compiled.append(compile_request(single, active.checkpoint["stats"]))
            predictions = active.predict_compiled_batch(compiled, microbatch_size=16)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

        selected = set(payload.full_field_scenario_ids)
        results = [
            build_prediction_result(
                compiled_item,
                prediction,
                active,
                include_fields=prediction.scenario_id in selected,
            )
            for compiled_item, prediction in zip(compiled, predictions, strict=True)
        ]
        return BatchPredictionResult(
            results=results,
            scenario_count=len(results),
            full_field_scenario_ids=payload.full_field_scenario_ids,
            elapsed_seconds=perf_counter() - started,
        )

    @application.post(
        "/screen",
        response_model=ScreenResult,
        summary="Run the integrated CCUS screening workflow synchronously",
        responses={
            200: {"description": "Integrated screening result"},
            422: {"description": "Invalid request or missing seed coverage"},
            429: {"description": "Another screening run is active"},
            503: {"description": "A required runtime dependency is unavailable"},
        },
    )
    def screen(payload: ScreenRequest, request: Request) -> ScreenResult:
        try:
            return screening(request).run(payload)
        except Exception as exc:
            raise screening_error(exc) from exc

    @application.post(
        "/screen/stream",
        response_class=ServerSentEventsResponse,
        summary="Stream the integrated CCUS screening workflow as SSE",
        responses={
            200: {
                "description": "Progress events ending in result, error, or cancelled",
                "content": {"text/event-stream": {"schema": {"type": "string"}}},
            },
            422: {"description": "Invalid request or missing seed coverage"},
            429: {"description": "Another screening run is active"},
            503: {"description": "A required runtime dependency is unavailable"},
        },
    )
    def screen_stream(payload: ScreenRequest, request: Request) -> StreamingResponse:
        active = screening(request)
        try:
            events = active.stream(payload)
        except Exception as exc:
            raise screening_error(exc) from exc
        return ServerSentEventsResponse(
            (sse_encode(event) for event in events),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @application.delete(
        "/screen/runs/{run_id}",
        summary="Request cooperative cancellation of an active screening run",
        status_code=202,
        responses={
            202: {"description": "Cancellation requested"},
            404: {"description": "Run is not active"},
        },
    )
    def cancel_screen(run_id: str, request: Request) -> dict[str, str]:
        if not screening(request).cancel(run_id):
            raise HTTPException(status_code=404, detail="run is not active")
        return {"run_id": run_id, "status": "cancellation_requested"}

    @application.get(
        "/presets",
        response_model=list[PresetInfo],
        summary="List screening presets and local readiness",
        responses={200: {"description": "Preset metadata"}},
    )
    def presets(request: Request) -> list[PresetInfo]:
        return screening(request).list_presets()

    @application.post(
        "/terrain/import",
        summary="Register a GeoTIFF terrain and return its basin overview",
        responses={200: {"description": "Terrain record with overview heightmap"},
                   422: {"description": "Path is missing or not a readable raster"}},
    )
    def terrain_import(payload: TerrainImportRequest, request: Request) -> dict[str, Any]:
        _require_local_client(request)
        try:
            stored = artifacts.put(Path(payload.path))
            record = registry.imports(stored.path)
            overview = registry.overview(record.terrain_id)
        except (TerrainImportError, FileNotFoundError, OSError) as exc:
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
    def reservoir_import(payload: ReservoirImportRequest, request: Request) -> dict[str, Any]:
        _require_local_client(request)
        return store_reservoir(payload)

    @application.post(
        "/reservoir/import-batch",
        summary="Import a well-keyed catalog of derived MRST reservoir models",
        responses={
            200: {"description": "Well-keyed typed reservoir payloads"},
            422: {"description": "Catalog, model, or bank is unreadable"},
        },
    )
    def reservoir_import_batch(
        payload: ReservoirCatalogImportRequest,
        request: Request,
    ) -> dict[str, Any]:
        _require_local_client(request)
        reservoirs: dict[str, dict[str, Any]] = {}
        for entry in payload.entries:
            reservoirs[entry.well_id] = store_reservoir(
                ReservoirImportRequest(
                    model_path=entry.model_path,
                    bank_path=entry.bank_path,
                )
            )
        return {"reservoirs": reservoirs, "count": len(reservoirs)}

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
            if bank_path is not None
            else None
        )
        try:
            return _reservoir_payload(
                model_path,
                model_id,
                model_sha,
                bank_path,
                bank_id,
                bank_sha,
            )
        except (MrstImportError, LaunchpadBankError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    @application.post(
        "/screening/spatial",
        summary="Persist detailed screening fields for a portable study memo",
        responses={200: {"description": "Hash-addressed spatial-result reference"}},
    )
    def screening_spatial_put(
        payload: SpatialResultArchive,
        request: Request,
    ) -> dict[str, Any]:
        _require_local_client(request)
        encoded = json.dumps(
            payload.model_dump(mode="json"),
            separators=(",", ":"),
            sort_keys=True,
            allow_nan=False,
        ).encode("utf-8")
        compressed = gzip.compress(encoded, compresslevel=6, mtime=0)
        stored = artifacts.put_bytes("screening-spatial.json.gz", compressed)
        return {
            "artifact_id": stored.artifact_id,
            "sha256": stored.sha256,
            "request_fingerprint": payload.request_fingerprint,
            "scenario_count": len(payload.detailed_predictions),
            "compressed_bytes": len(compressed),
        }

    @application.get(
        "/screening/spatial/{artifact_id}",
        summary="Re-link detailed screening fields from the artifact store",
        responses={
            200: {"description": "Verified spatial-result archive"},
            404: {"description": "Spatial-result artifact is missing"},
            422: {"description": "Stored spatial-result artifact is invalid"},
        },
    )
    def screening_spatial_get(artifact_id: str) -> dict[str, Any]:
        try:
            path = artifacts.resolve(artifact_id)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        compressed = path.read_bytes()
        digest = hashlib.sha256(compressed).hexdigest().upper()
        if digest[:16].lower() != artifact_id.lower():
            raise HTTPException(status_code=422, detail="spatial-result artifact ID mismatch")
        try:
            payload = SpatialResultArchive.model_validate_json(gzip.decompress(compressed))
        except (OSError, ValueError) as exc:
            raise HTTPException(status_code=422, detail="stored spatial-result artifact is invalid") from exc
        return {
            "artifact_id": artifact_id.lower(),
            "sha256": digest,
            "payload": payload.model_dump(mode="json"),
        }

    @application.post(
        "/roads/import",
        summary="Import an OSM extract as the study road network",
        responses={200: {"description": "Road network record"},
                   404: {"description": "Terrain is not registered"},
                   422: {"description": "File is not a readable OSM extract with roads in the extent"}},
    )
    def roads_import(
        payload: RoadsImportRequest,
        request: Request,
    ) -> dict[str, Any]:
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
                "road_network_id": record.road_network_id,
                "sha256": record.sha256,
                "source_path": record.source_path,
                "bbox": list(record.bbox),
                "node_count": record.node_count,
                "edge_count": record.edge_count,
            }
            for record in roads.list()
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

    @application.get(
        "/health",
        response_model=HealthResponse,
        summary="Report screening dependency readiness",
        responses={200: {"description": "Service health and dependency status"}},
    )
    def health(request: Request) -> HealthResponse:
        return screening(request).health()

    _mount_frontend(application)

    return application


app = create_app()
