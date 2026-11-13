from __future__ import annotations

from collections import Counter
from pathlib import Path

import h5py
import numpy as np

from jatibarang_ccus.paper.experiment.arm_ab import (
    _arm_a_design,
    _arm_b_design,
    prediction_result_from_mrst,
)


def _row(
    *,
    candidate: str,
    source_case: str,
    rank: int,
    fingerprint: str,
) -> dict[str, str]:
    return {
        "selection_rank": str(rank),
        "replacement_rank": str(rank),
        "candidate_id": candidate,
        "source_case_id": source_case,
        "schedule_fingerprint": fingerprint,
        "injection_rate_m3_day": "9000",
        "injection_duration_days": "45",
        "soak_duration_days": str(25 + rank % 3 * 5),
        "production_duration_days": "190",
        "production_bhp_psi": "675",
        "cycles": "3",
    }


def test_arm_a_representatives_and_schedule_are_locked() -> None:
    params = {
        "case_0090": {"geo_iteration_rung": 1.0},
        "case_0109": {"geo_iteration_rung": 2.0},
    }
    design = _arm_a_design("A" * 64, params)

    assert [
        (slot.candidate_id, slot.source_case_id)
        for slot in design.slots
    ] == [
        ("W09", "case_0090"),
        ("W12", "case_0109"),
    ]
    assert {
        tuple(slot.attempts[0].schedule.values())
        for slot in design.slots
    } == {(9000.0, 45.0, 30.0, 190.0, 675.0, 3)}
    assert all(not slot.replacement_allowed for slot in design.slots)


def test_arm_b_replacements_are_deterministic_same_geology_lanes() -> None:
    primary = []
    replacements = []
    params = {}
    selection_rank = 0
    for index in range(1, 21):
        candidate = f"W{index:02d}"
        source_case = f"case_{index:04d}"
        params[source_case] = {"geo_iteration_rung": 1.0}
        for lane in range(2):
            selection_rank += 1
            primary.append(
                _row(
                    candidate=candidate,
                    source_case=source_case,
                    rank=selection_rank,
                    fingerprint=f"{candidate}-primary-{lane}",
                )
            )
        for rank in range(1, 7):
            row = _row(
                candidate=candidate,
                source_case=source_case,
                rank=rank,
                fingerprint=f"{candidate}-replacement-{rank}",
            )
            row["replacement_rank"] = str(rank)
            replacements.append(row)

    first = _arm_b_design(primary, replacements, "B" * 64, params)
    second = _arm_b_design(primary, replacements, "B" * 64, params)

    assert first == second
    assert len(first.slots) == 40
    assert Counter(slot.candidate_id for slot in first.slots) == {
        f"W{index:02d}": 2 for index in range(1, 21)
    }
    for candidate in {slot.candidate_id for slot in first.slots}:
        lanes = [slot for slot in first.slots if slot.candidate_id == candidate]
        replacement_attempts = [
            {attempt.attempt_id for attempt in slot.attempts[1:]}
            for slot in lanes
        ]
        assert replacement_attempts[0].isdisjoint(replacement_attempts[1])
        assert all(
            attempt.source_case_id == lanes[0].source_case_id
            for slot in lanes
            for attempt in slot.attempts
        )


def test_full_mrst_adapter_preserves_all_steps_and_zero_uncertainty(
    tmp_path: Path,
) -> None:
    path = tmp_path / "full.mat"
    stages = np.tile(
        np.array([1] * 4 + [2] * 2 + [3] * 6, dtype=np.int64),
        3,
    )
    count = len(stages)
    with h5py.File(path, "w") as handle:
        params = handle.create_group("params")
        for key, value in {
            "anisotropy_ratio": 0.1,
            "inj_rate_surf": 9000.0,
            "t_inj_days": 45.0,
            "t_soak_days": 30.0,
            "t_prod_days": 190.0,
            "prod_bhp_psi": 675.0,
            "n_cycles": 3.0,
        }.items():
            params.create_dataset(key, data=np.array([value]))
        dynamic = {
            "pressure": np.full((count, 64, 64), 100.0),
            "gas_sat": np.full((count, 64, 64), 0.1),
            "z_co2": np.full((count, 64, 64), 0.8),
            "oil_sat": np.full((count, 64, 64), 0.9),
        }
        static = {
            "perm_map": np.full((64, 64), 2.0),
            "poro_map": np.full((64, 64), 0.2),
            "structure_map": np.zeros((64, 64)),
            "fracture_proxy_map": np.zeros((64, 64)),
            "barrier_map": np.zeros((64, 64)),
            "facies_map": np.ones((64, 64)),
            "well_mask": np.zeros((64, 64)),
            "completion_mask": np.zeros((64, 64)),
        }
        static["well_mask"][32, 32] = 1.0
        static["completion_mask"][32, 32] = 1.0
        for key, value in {**dynamic, **static}.items():
            handle.create_dataset(key, data=value)
        handle.create_dataset("dt_days", data=np.ones(count))
        handle.create_dataset("stage_labels", data=stages)
        handle.create_dataset(
            "well_oil_rate",
            data=np.full(count, -1.0e-5),
        )
        handle.create_dataset(
            "well_gas_rate",
            data=np.full(count, -2.0e-5),
        )
        handle.create_dataset("well_ij", data=np.array([33, 33]))
        handle.create_dataset(
            "completion_ij",
            data=np.array([[33], [33]]),
        )

    result = prediction_result_from_mrst(
        path,
        scenario_id="mrst-full",
        include_fields=True,
    )

    assert len(result.timeline) == count
    assert [step.cycle for step in result.timeline[::12]] == [1, 2, 3]
    assert {step.origin for step in result.timeline} == {"mrst"}
    assert result.confidence.metrics["trajectory_uncertainty_fraction"] == 0.0
    assert result.provenance["source_class"] == "mrst_truth"
    assert result.fields is not None
    assert len(result.fields) == count
    assert {frame.origin for frame in result.fields} == {"mrst"}
