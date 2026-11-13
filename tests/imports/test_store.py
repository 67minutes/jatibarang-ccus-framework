from __future__ import annotations

from pathlib import Path

import pytest

from jatibarang_ccus.imports.store import ImportStore


def test_put_is_idempotent_and_resolvable(tmp_path: Path) -> None:
    source = tmp_path / "model.mat"
    source.write_bytes(b"payload-bytes")
    store = ImportStore(tmp_path / "imports")
    first = store.put(source)
    second = store.put(source)
    assert first.artifact_id == second.artifact_id
    assert store.resolve(first.artifact_id).read_bytes() == b"payload-bytes"


def test_put_bytes_is_hash_addressed_and_rejects_paths(tmp_path: Path) -> None:
    store = ImportStore(tmp_path / "imports")

    stored = store.put_bytes("screening-spatial.json.gz", b"compressed-result")

    assert stored.sha256 == "3B257C2340577178FB4B8F2E73E6D5FC2C5922FCDB6C88DAEDFDE57D592DBAC3"
    assert store.resolve(stored.artifact_id).read_bytes() == b"compressed-result"
    with pytest.raises(ValueError, match="basename"):
        store.put_bytes("../escape.json", b"payload")
