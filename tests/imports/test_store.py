from __future__ import annotations

from pathlib import Path

from jatibarang_ccus.imports.store import ImportStore


def test_put_is_idempotent_and_resolvable(tmp_path: Path) -> None:
    source = tmp_path / "model.mat"
    source.write_bytes(b"payload-bytes")
    store = ImportStore(tmp_path / "imports")
    first = store.put(source)
    second = store.put(source)
    assert first.artifact_id == second.artifact_id
    assert store.resolve(first.artifact_id).read_bytes() == b"payload-bytes"
