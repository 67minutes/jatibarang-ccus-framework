from __future__ import annotations

import json
from types import SimpleNamespace
from pathlib import Path

import pytest

from jatibarang_ccus.paper.experiment import run


def test_mrst_memory_gate_requires_reserve_and_measured_worker(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        run.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(available=2 * 1024**3),
    )
    with pytest.raises(RuntimeError, match="locked RAM formula"):
        run._assert_mrst_memory_reserve(
            tmp_path,
            require_measured_worker=False,
        )
    blocked = json.loads(
        (tmp_path / "mrst_execution_preflight.json").read_text(
            encoding="utf-8"
        )
    )
    assert blocked["last_gate"]["selected_workers"] == 0

    blocked["runs"] = [
        {
            "phase": "smoke",
            "returncode": 0,
            "peak_worker_rss_bytes": 1024**3,
        }
    ]
    (tmp_path / "mrst_execution_preflight.json").write_text(
        json.dumps(blocked),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        run.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(available=4 * 1024**3),
    )
    run._assert_mrst_memory_reserve(
        tmp_path,
        require_measured_worker=True,
    )
    ready = json.loads(
        (tmp_path / "mrst_execution_preflight.json").read_text(
            encoding="utf-8"
        )
    )
    assert ready["last_gate"]["selected_workers"] == 1
