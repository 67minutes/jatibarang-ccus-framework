from __future__ import annotations

from types import SimpleNamespace

import pytest

from jatibarang_ccus.paper.experiment.aggregate import runtime_rows


def _manifest(
    *,
    accepted: int,
    accepted_seconds: float,
    failed_seconds: tuple[float, ...] = (),
) -> SimpleNamespace:
    entries = [
        SimpleNamespace(status="accepted", runtime_seconds=accepted_seconds)
        for _ in range(accepted)
    ]
    entries.extend(
        SimpleNamespace(status="failed", runtime_seconds=value)
        for value in failed_seconds
    )
    return SimpleNamespace(entries=entries)


def test_runtime_rows_separate_assignment_resolves_and_equivalence() -> None:
    records = [
        {
            "assignment_id": f"independent-{assignment:02d}",
            "result": {"downstream_total_seconds": 2.0},
        }
        for assignment in range(20)
        for _price in range(4)
    ]
    correlated = [
        {
            "assignment_id": f"correlated-{assignment:02d}",
            "result": {"downstream_total_seconds": 2.0},
        }
        for assignment in range(20)
        for _price in range(4)
    ]
    arm_c = {
        "screen_result": {"timings": {"total_seconds": 120.0}},
        "timings": {"initial_screen_seconds": 345.0},
        "field_scenario": {
            "independent": records,
            "correlated": correlated,
        },
    }
    manifests = {
        "arm_a": _manifest(
            accepted=2,
            accepted_seconds=100.0,
        ),
        "arm_b": _manifest(
            accepted=40,
            accepted_seconds=100.0,
            failed_seconds=(30.0,),
        ),
        "top5": _manifest(
            accepted=5,
            accepted_seconds=100.0,
        ),
    }

    by_arm = {row.arm: row for row in runtime_rows(arm_c, manifests)}
    assert by_arm["A"].economics_scenarios == 20
    assert by_arm["B"].attempted_runs == 41
    assert by_arm["B"].failed_attempt_seconds == 30.0
    # Each assignment solve evaluates all four prices once; the 160 logical
    # cells must not count the same 40 assignment wall-clocks four times.
    assert by_arm["C"].wall_clock_seconds == 345.0
    assert by_arm["C"].downstream_resolve_seconds == 80.0
    assert by_arm["C"].mrst_equivalence_weeks == pytest.approx(
        3240 * 100.0 / (7 * 86_400)
    )
