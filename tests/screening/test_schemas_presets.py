from __future__ import annotations

import json
import hashlib

import numpy as np
import pytest
from pydantic import ValidationError

import jatibarang_ccus.screening.presets as presets_module
from jatibarang_ccus.contracts import Coordinate, EconomicProvenance
from jatibarang_ccus.screening.presets import (
    CompactPresetBank,
    CompactPresetCandidate,
    CompactPresetMetadata,
    PresetManifest,
    PresetRegistry,
    materialize_inline_scenarios,
)
from jatibarang_ccus.screening.preset_builder import build_upstream_design, import_seed_bank
from jatibarang_ccus.screening.orchestrator import _chunks
from jatibarang_ccus.screening.schemas import (
    InlineScreenRequest,
    OperationalGrid,
    ProducedCO2Assumption,
    PresetScreenRequest,
    ScreeningCandidate,
)
from jatibarang_ccus.surrogate.preprocessing import schedule_fingerprint

from .helpers import economic_dimensions, geology, schedule, seed, source


def inline_request(*, rates=(9000.0,), candidates=1) -> InlineScreenRequest:
    prices, fiscal, assumptions = economic_dimensions()
    schedules = [schedule(rate=rate) for rate in rates]
    seeds = {f"seed-{index}": seed(item) for index, item in enumerate(schedules)}
    candidate_rows = []
    for index in range(candidates):
        candidate_rows.append(
            ScreeningCandidate(
                candidate_id=f"W{index + 1:02d}",
                location=Coordinate(latitude=-6.5 - index * 0.001, longitude=107.6 + index * 0.001),
                geology_id="g",
                seed_by_schedule_fingerprint={
                    schedule_fingerprint(item): f"seed-{offset}" for offset, item in enumerate(schedules)
                },
                produced_co2=ProducedCO2Assumption(
                    mole_fraction=0.65,
                    provenance=EconomicProvenance(source_class="engineering_assumption", source_id="fixture"),
                ),
            )
        )
    return InlineScreenRequest(
        geologies={"g": geology()},
        seeds=seeds,
        candidates=candidate_rows,
        sources=[source()],
        schedules=schedules,
        annual_co2_budget_tonnes=300_000.0,
        carbon_prices=prices,
        fiscal_cases=fiscal,
        economic_assumptions=assumptions,
    )


def test_operational_grid_expands_lexicographically() -> None:
    grid = OperationalGrid(
        injection_rate_m3_day=[8000.0, 9000.0],
        injection_duration_days=[45.0],
        soak_duration_days=[30.0],
        production_duration_days=[190.0],
        production_bhp_psi=[675.0],
        cycles=[3, 4],
    )
    expanded = grid.expand()
    assert [(item.injection_rate_m3_day, item.cycles) for item in expanded] == [
        (8000.0, 3),
        (8000.0, 4),
        (9000.0, 3),
        (9000.0, 4),
    ]


def test_materialization_requires_exact_seed_coverage() -> None:
    request = inline_request(rates=(8000.0, 9000.0))
    candidate = request.candidates[0].model_copy(update={"seed_by_schedule_fingerprint": {}})
    request = request.model_copy(update={"candidates": [candidate]})
    with pytest.raises(ValueError, match="missing compatible seed"):
        materialize_inline_scenarios(request)


def test_materialization_is_deterministic_and_capped() -> None:
    request = inline_request(rates=(8000.0, 9000.0), candidates=2)
    materialized = materialize_inline_scenarios(request)
    assert [item.scenario_id for item in materialized] == sorted(item.scenario_id for item in materialized)
    assert len(materialized) == 4

    too_many = request.model_copy(update={"scenario_limit": 3})
    with pytest.raises(ValueError, match="scenario limit"):
        materialize_inline_scenarios(too_many)

    hard_limit = request.model_copy(
        update={"schedules": [schedule()] * 4097, "scenario_limit": 4096, "candidates": request.candidates[:1]}
    )
    with pytest.raises(ValueError, match="4096"):
        materialize_inline_scenarios(hard_limit)


def test_internal_module_chunks_never_exceed_256() -> None:
    chunks = list(_chunks(list(range(4096)), 256))
    assert len(chunks) == 16
    assert all(len(chunk) == 256 for chunk in chunks)
    assert [len(chunk) for chunk in _chunks(list(range(257)), 256)] == [256, 1]


def test_inline_request_rejects_grid_and_schedule_list_together() -> None:
    request = inline_request()
    with pytest.raises(ValidationError, match="exactly one"):
        InlineScreenRequest.model_validate(
            {
                **request.model_dump(mode="json"),
                "operational_grid": {
                    "injection_rate_m3_day": [9000.0],
                    "injection_duration_days": [45.0],
                    "soak_duration_days": [30.0],
                    "production_duration_days": [190.0],
                    "production_bhp_psi": [675.0],
                    "cycles": [3],
                },
            }
        )


def test_preset_registry_reports_missing_payload_without_fabrication(tmp_path) -> None:
    registry = PresetRegistry(root=tmp_path)
    rows = {item.preset_id: item for item in registry.list_presets()}
    assert set(rows) == {"jatibarang_demo_v1", "jatibarang_full_v1"}
    assert rows["jatibarang_demo_v1"].ready is False
    assert set(rows["jatibarang_demo_v1"].component_catalog) == {
        "geology",
        "terrain",
        "supply",
        "well_locations",
    }
    with pytest.raises(FileNotFoundError, match="unavailable"):
        registry.resolve("jatibarang_demo_v1")


def test_upstream_design_has_deterministic_demo_and_full_dimensions(tmp_path) -> None:
    source_manifest = tmp_path / "manifest.json"
    source_manifest.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "case_id": f"case_{index:04d}",
                        "status": "accepted",
                        "usable_for_training": True,
                        "output_file": f"case_{index:04d}.mat",
                        "params": {
                            "poro_mean": 0.15 + index * 0.001,
                            "perm_mult": 0.8 + index * 0.02,
                            "anisotropy_ratio": 1.0 + index * 0.05,
                            "corridor_width_norm": 0.05 + index * 0.002,
                            "dip_relief_m": 0.5 + index * 0.04,
                            "local_structure_amp_m": 0.2 + index * 0.01,
                        },
                    }
                    for index in range(25)
                ]
            }
        ),
        encoding="utf-8",
    )
    demo = build_upstream_design(
        preset_id="jatibarang_demo_v1", source_manifest_path=source_manifest
    )
    full = build_upstream_design(
        preset_id="jatibarang_full_v1", source_manifest_path=source_manifest
    )

    assert (len(demo["geologies"]), len(demo["schedules"]), demo["logical_scenarios"]) == (20, 10, 200)
    assert (len(full["geologies"]), len(full["schedules"]), full["logical_scenarios"]) == (20, 162, 3240)
    assert [item["source_case_id"] for item in demo["geologies"]] == [
        item["source_case_id"] for item in full["geologies"]
    ]
    assert demo["design_sha256"] == build_upstream_design(
        preset_id="jatibarang_demo_v1", source_manifest_path=source_manifest
    )["design_sha256"]


def test_compact_preset_materializes_seeds_lazily(tmp_path, monkeypatch) -> None:
    prices, fiscal, assumptions = economic_dimensions()
    schedules = [schedule(cycles=3), schedule(cycles=4)]
    metadata = CompactPresetMetadata(
        preset_id="jatibarang_demo_v1",
        candidates=[
            CompactPresetCandidate(
                candidate_id="W01",
                location=Coordinate(latitude=-6.5, longitude=107.6),
                produced_co2=ProducedCO2Assumption(
                    mole_fraction=0.65,
                    provenance=EconomicProvenance(
                        source_class="engineering_assumption", source_id="fixture"
                    ),
                ),
            )
        ],
        schedules=schedules,
        sources=[source()],
        annual_co2_budget_tonnes=300_000.0,
        carbon_prices=prices,
        fiscal_cases=fiscal,
        economic_assumptions=assumptions,
    )
    preset_dir = tmp_path / "jatibarang_demo_v1"
    preset_dir.mkdir()
    payload_path = preset_dir / "payload.npz"
    maps = np.zeros((1, 8, 4096), dtype=np.float32)
    maps[0, 0] = 100.0
    maps[0, 1] = 0.2
    maps[0, 3] = 0.2
    maps[0, 5] = 1.0
    maps[0, 7, 0] = 1.0
    frames = np.zeros((1, 2, 8, 3, 4096), dtype=np.float32)
    frames[:, :, :, 0] = 55.0
    frames[:, :, :, 1] = 0.01
    frames[:, :, :, 2] = 0.02
    np.savez_compressed(
        payload_path,
        metadata_json_utf8=np.frombuffer(metadata.model_dump_json().encode(), dtype=np.uint8),
        geology_maps=maps,
        geology_scalars=np.asarray([[2.0, 91.0, 900.0, 600.0, 6.0]], dtype=np.float32),
        seed_frames=frames,
        seed_oil_delta=np.ones((1, 2, 8), dtype=np.float32),
        seed_gas_delta=np.ones((1, 2, 8), dtype=np.float32),
    )
    digest = hashlib.sha256(payload_path.read_bytes()).hexdigest().upper()
    manifest = PresetManifest(
        preset_id="jatibarang_demo_v1",
        logical_scenarios=2,
        geology_count=1,
        schedule_count=2,
        payload_file="payload.npz",
        payload_sha256=digest,
        design_sha256="D" * 64,
        source_manifest="fixture",
        generated_at="2026-07-16T00:00:00Z",
        provenance={"payload_format": "compact_array_bank_v2"},
    )
    (preset_dir / "manifest.json").write_text(manifest.model_dump_json(), encoding="utf-8")

    monkeypatch.setitem(presets_module.EXPECTED_PRESETS, "jatibarang_demo_v1", (2, 1, 2))
    bank = PresetRegistry(tmp_path).resolve("jatibarang_demo_v1")
    assert isinstance(bank, CompactPresetBank)
    bank.configure(PresetScreenRequest(preset_id="jatibarang_demo_v1"))
    scenarios = list(bank.iter_scenarios())
    assert len(scenarios) == 2
    assert scenarios[0].predict_request.seed.schedule_fingerprint == schedule_fingerprint(
        scenarios[0].schedule
    )
    bank.close()


def test_seed_import_rejects_an_incomplete_upstream_exporter_manifest(tmp_path) -> None:
    active_schedule = schedule()
    design = {
        "preset_id": "jatibarang_demo_v1",
        "design_sha256": "A" * 64,
        "source_manifest": "fixture",
        "geologies": [{"candidate_id": "W01"}],
        "schedules": [
            {
                "values": active_schedule.model_dump(mode="json"),
                "schedule_fingerprint": schedule_fingerprint(active_schedule),
            }
        ],
    }
    design_path = tmp_path / "design.json"
    design_path.write_text(json.dumps(design), encoding="utf-8")
    seed_root = tmp_path / "seeds"
    seed_root.mkdir()
    (seed_root / "manifest.json").write_text(
        json.dumps({"design_sha256": "A" * 64, "completed_runs": 0, "entries": []}),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="incomplete"):
        import_seed_bank(design_path=design_path, seed_root=seed_root, output_root=tmp_path)
