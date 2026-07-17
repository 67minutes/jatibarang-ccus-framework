from __future__ import annotations

import pytest

import jatibarang_ccus.phase1.case_study as case_study
from jatibarang_ccus.infrastructure.facility import evaluate_facility_portfolio as real_evaluator


def selected_values(count: int = 2):
    assumptions = case_study.load_assumptions()
    params = case_study._scenario_parameters(assumptions["screening_grid"])[0]
    price = float(assumptions["carbon_prices_usd_per_tonne"]["current_idx"])
    values = {
        candidate.id: case_study._evaluate_candidate(
            candidate,
            params,
            assumptions["economics"],
            price,
        )
        for candidate in case_study._candidate_models(assumptions)[:count]
    }
    return assumptions, values


def test_selected_phase1_wells_are_evaluated_in_one_portfolio_call(monkeypatch) -> None:
    assumptions, values = selected_values()
    calls = []

    def recording_evaluator(request, *args, **kwargs):
        calls.append(request)
        return real_evaluator(request, *args, **kwargs)

    monkeypatch.setattr(case_study, "evaluate_facility_portfolio", recording_evaluator)
    result = case_study._evaluate_selected_facility_portfolio(
        best_for_selected=values,
        node_pressures_bar={candidate_id: 100.0 for candidate_id in values},
        assumptions=assumptions,
        cost_case="base",
        portfolio_id="phase1-test",
    )

    assert len(calls) == 1
    assert set(item.candidate_id for item in calls[0].wells) == set(values)
    assert set(item.candidate_id for item in result.well_results) == set(values)


def test_adapter_does_not_apply_a_selected_well_multiplier() -> None:
    assumptions, values = selected_values()
    result = case_study._evaluate_selected_facility_portfolio(
        best_for_selected=values,
        node_pressures_bar={candidate_id: 100.0 for candidate_id in values},
        assumptions=assumptions,
        cost_case="base",
        portfolio_id="phase1-test",
    )
    assert result.total_capex_usd == pytest.approx(sum(item.capex_usd for item in result.well_results))
    assert all(len(item.equipment) == 6 for item in result.well_results)
