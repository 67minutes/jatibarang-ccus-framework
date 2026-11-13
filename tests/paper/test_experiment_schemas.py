from __future__ import annotations

import csv
from pathlib import Path

import pytest
from pydantic import ValidationError

from jatibarang_ccus.paper.experiment.schemas import (
    ScreeningSurfaceRow,
    TopKConfirmationRow,
    atomic_write_csv,
    read_validated_csv,
)


def test_atomic_csv_writer_locks_figure_columns_and_source_class(
    tmp_path: Path,
) -> None:
    output = tmp_path / "screening_surface.csv"
    row = ScreeningSurfaceRow(
        geology_id="W01",
        mean_permeability_md=100.0,
        injection_rate_m3_day=9000.0,
        incremental_oil_m3=20.0,
        co2_retention_fraction=0.8,
        cycles=3,
        sample_count=9,
        incremental_oil_p10_m3=18.0,
        incremental_oil_p90_m3=22.0,
        co2_retention_p10_fraction=0.7,
        co2_retention_p90_fraction=0.9,
        source_class="surrogate_prediction",
    )
    assert atomic_write_csv(output, [row], model=ScreeningSurfaceRow) == 1

    with output.open(encoding="utf-8", newline="") as handle:
        written = list(csv.DictReader(handle))
    assert written[0]["mean_permeability_md"] == "100.0"
    assert written[0]["source_class"] == "surrogate_prediction"

    with pytest.raises(ValidationError):
        ScreeningSurfaceRow.model_validate(
            {**row.model_dump(), "source_class": "invented_result"}
        )


def test_topk_contract_uses_live_figure_08_column_names() -> None:
    row = TopKConfirmationRow(
        plan_id="plan-1",
        designated_carbon_price_scenario_id="p40",
        carbon_price_usd_per_tonne=40.0,
        fiscal_case="article6_jcm",
        surrogate_value=10.0,
        mrst_value=8.0,
        relative_error=0.25,
        absolute_relative_error=0.25,
        source_class="mrst_truth_and_surrogate_prediction",
    )
    payload = row.model_dump()
    assert "surrogate_value" in payload
    assert "mrst_value" in payload
    assert "surrogate_objective_usd" not in payload


def test_optional_metrics_round_trip_as_blank_csv_cells(
    tmp_path: Path,
) -> None:
    path = tmp_path / "topk_confirmation.csv"
    row = TopKConfirmationRow(
        plan_id="plan-1",
        designated_carbon_price_scenario_id="p40",
        carbon_price_usd_per_tonne=40.0,
        fiscal_case="pre_tax",
        surrogate_value=10.0,
        mrst_value=9.0,
        relative_error=1 / 9,
        absolute_relative_error=1 / 9,
        source_class="mrst_truth_and_surrogate_prediction",
    )
    atomic_write_csv(path, [row], model=TopKConfirmationRow)

    restored = read_validated_csv(
        path,
        model=TopKConfirmationRow,
    )
    assert restored[0].throughput_class is None
    assert restored[0].dwsim_total_power_kw is None
