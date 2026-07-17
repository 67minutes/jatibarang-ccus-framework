from __future__ import annotations

import json
from pathlib import Path

from jatibarang_ccus.phase1.abstract_numbers import ABSTRACT_KEYS, generate_abstract_numbers
from jatibarang_ccus.phase1.case_study import DEFAULT_ASSUMPTIONS, load_assumptions, run_screening
from jatibarang_ccus.phase1.metrics import mrst_mean_runtime_seconds


def test_case_study_assumptions_have_required_inputs() -> None:
    assumptions = load_assumptions(DEFAULT_ASSUMPTIONS)
    assert len(assumptions["candidates"]) == 20
    assert assumptions["mrst_timing"]["curated_validation_case_limit"] == 5
    grid = assumptions["screening_grid"]
    assert len(grid["injection_rate_m3_day"]) * len(grid["soak_days"]) * len(grid["production_days"]) > 0
    assert "current_idx" in assumptions["carbon_prices_usd_per_tonne"]
    assert "jcm_bilateral" in assumptions["carbon_prices_usd_per_tonne"]


def test_screening_smoke_outputs_required_fields() -> None:
    assumptions = load_assumptions(DEFAULT_ASSUMPTIONS)
    result = run_screening(assumptions, mrst_mean_seconds=mrst_mean_runtime_seconds())
    assert result["scenario_count"] == 3240
    assert result["equivalent_mrst_weeks"] > 0
    assert result["by_price"]["jcm_bilateral"]["portfolio_npv_usd"] > result["by_price"]["current_idx"]["portfolio_npv_usd"]
    assert result["candidate_count"] == 20
    assert "A* SRTM routing" in result["method"]
    assert "Pyomo/CBC MILP" in result["method"]
    assert result["by_price"]["current_idx"]["pipeline"]["selected_wells"]


def test_abstract_number_generation_has_no_blanks(tmp_path: Path) -> None:
    result = generate_abstract_numbers(output_dir=tmp_path)
    entries = {entry["key"]: entry for entry in result["entries"]}
    assert set(ABSTRACT_KEYS) == set(entries)
    for key in ABSTRACT_KEYS:
        item = entries[key]
        assert item["value"] not in (None, "")
        assert item["units"]
        assert item["source"]
        assert item["method"]
    assert "[x]" not in result["filled_excerpt"]

    payload = json.loads((tmp_path / "abstract_numbers.json").read_text(encoding="utf-8"))
    assert payload["filled_excerpt"] == result["filled_excerpt"]
    assert (tmp_path / "abstract_numbers.csv").exists()
    assert (tmp_path / "abstract_numbers.md").exists()
    assert "lightweight integrated screening" not in payload["filled_excerpt"]
    for item in payload["entries"]:
        assert "proxy routing" not in item["method"].lower()
        assert "greedy" not in item["method"].lower()
