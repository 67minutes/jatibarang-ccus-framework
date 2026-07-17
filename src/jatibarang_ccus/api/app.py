from __future__ import annotations

from contextlib import asynccontextmanager
import math
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from ..imports.launchpads import LaunchpadBankError, load_launchpad_bank
from ..imports.mrst import MrstImportError, load_mrst_reservoir
from ..imports.store import ImportStore
from ..imports.terrain import Heightmap, TerrainImportError, TerrainRegistry
from ..screening.progress import RunBusyError, sse_encode
from ..screening.schemas import HealthResponse, PresetInfo, ScreenRequest, ScreenResult

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


class TerrainImportRequest(BaseModel):
    path: str


class ReservoirImportRequest(BaseModel):
    model_path: str
    bank_path: str | None = None


def create_app(
    runner_factory: RunnerFactory = load_surrogate,
    *,
    screening_factory: ScreeningFactory | None = None,
    terrain_registry: TerrainRegistry | None = None,
    import_store: ImportStore | None = None,
) -> FastAPI:
    registry = terrain_registry or TerrainRegistry(_REPO_ROOT / "data" / "imports")
    artifacts = import_store or ImportStore(_REPO_ROOT / "data" / "imports")

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
    def terrain_import(payload: TerrainImportRequest) -> dict[str, Any]:
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
    def reservoir_import(payload: ReservoirImportRequest) -> dict[str, Any]:
        try:
            imported = load_mrst_reservoir(Path(payload.model_path))
        except MrstImportError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        stored = artifacts.put(Path(payload.model_path))
        bank_id = bank_sha = None
        bank = {}
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
            "native_seed": imported.seed.model_dump(mode="json"),
            "bank_seeds": {
                fingerprint: seed.model_dump(mode="json")
                for fingerprint, seed in sorted(bank.items())
            },
            "well_ij": list(imported.well_ij),
            "completion_ij": [list(pair) for pair in imported.completion_ij],
            "launchpads": {
                "bank_id": bank_id, "bank_sha256": bank_sha,
                "covered_fingerprints": covered,
            },
        }

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
