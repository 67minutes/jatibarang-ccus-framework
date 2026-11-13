from __future__ import annotations

from collections import OrderedDict
from collections.abc import Iterator, MutableMapping
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any, Mapping
import zlib

from jatibarang_ccus.surrogate.schemas import PredictionResult


SCHEMA_VERSION = "feature007-prediction-cache-v1"
MEMORY_ENTRY_LIMIT = 4096


def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


class PredictionCache(MutableMapping[str, PredictionResult]):
    """SQLite-backed compact prediction cache with immutable run identity.

    Values deliberately contain only the compact ``PredictionResult`` used by
    downstream screening. Detailed spatial arrays remain owned by the existing
    transient detailed-field store.
    """

    def __init__(
        self,
        path: Path | str,
        *,
        identity: Mapping[str, str],
    ) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.identity = {
            str(key): str(value)
            for key, value in sorted(identity.items())
        }
        self._connection = sqlite3.connect(self.path)
        self._read_cache: OrderedDict[str, PredictionResult] = OrderedDict()
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS predictions (
                fingerprint TEXT PRIMARY KEY,
                realization_id TEXT NOT NULL,
                payload_zlib BLOB NOT NULL,
                payload_sha256 TEXT NOT NULL
            )
            """
        )
        try:
            self._initialize_or_validate_identity()
        except Exception:
            self._connection.close()
            raise

    def _initialize_or_validate_identity(self) -> None:
        expected = {
            "schema_version": SCHEMA_VERSION,
            "identity_json": _canonical_json(self.identity).decode("utf-8"),
        }
        current = dict(
            self._connection.execute("SELECT key, value FROM metadata").fetchall()
        )
        if not current:
            self._connection.executemany(
                "INSERT INTO metadata(key, value) VALUES (?, ?)",
                sorted(expected.items()),
            )
            self._connection.commit()
            return
        if current != expected:
            raise ValueError(
                "prediction cache identity does not match the requested "
                "checkpoint/preset/design basis"
            )

    def __getitem__(self, fingerprint: str) -> PredictionResult:
        cached = self._read_cache.get(fingerprint)
        if cached is not None:
            self._read_cache.move_to_end(fingerprint)
            return cached
        row = self._connection.execute(
            """
            SELECT payload_zlib, payload_sha256
            FROM predictions
            WHERE fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()
        if row is None:
            raise KeyError(fingerprint)
        encoded = zlib.decompress(row[0])
        actual_sha = hashlib.sha256(encoded).hexdigest().upper()
        if actual_sha != row[1]:
            raise ValueError(
                f"prediction cache payload hash mismatch for {fingerprint}"
            )
        prediction = PredictionResult.model_validate_json(encoded)
        self._read_cache[fingerprint] = prediction
        self._read_cache.move_to_end(fingerprint)
        if len(self._read_cache) > MEMORY_ENTRY_LIMIT:
            self._read_cache.popitem(last=False)
        return prediction

    def __setitem__(
        self,
        fingerprint: str,
        prediction: PredictionResult,
    ) -> None:
        value = PredictionResult.model_validate(prediction)
        encoded = _canonical_json(
            value.model_dump(
                mode="json",
                exclude={"fields"},
                exclude_none=True,
            )
        )
        payload_sha = hashlib.sha256(encoded).hexdigest().upper()
        realization_id = str(
            value.provenance.get("seed_source_id")
            or value.provenance.get("source_id")
            or value.scenario_id
        )
        existing = self._connection.execute(
            """
            SELECT payload_sha256
            FROM predictions
            WHERE fingerprint = ?
            """,
            (fingerprint,),
        ).fetchone()
        if existing is not None and existing[0] != payload_sha:
            raise ValueError(
                f"prediction cache refuses conflicting payload for {fingerprint}"
            )
        self._connection.execute(
            """
            INSERT OR IGNORE INTO predictions(
                fingerprint,
                realization_id,
                payload_zlib,
                payload_sha256
            ) VALUES (?, ?, ?, ?)
            """,
            (
                fingerprint,
                realization_id,
                sqlite3.Binary(zlib.compress(encoded, level=6)),
                payload_sha,
            ),
        )
        self._connection.commit()
        self._read_cache[fingerprint] = value
        self._read_cache.move_to_end(fingerprint)
        if len(self._read_cache) > MEMORY_ENTRY_LIMIT:
            self._read_cache.popitem(last=False)

    def __delitem__(self, fingerprint: str) -> None:
        cursor = self._connection.execute(
            "DELETE FROM predictions WHERE fingerprint = ?",
            (fingerprint,),
        )
        if cursor.rowcount == 0:
            raise KeyError(fingerprint)
        self._connection.commit()
        self._read_cache.pop(fingerprint, None)

    def __iter__(self) -> Iterator[str]:
        rows = self._connection.execute(
            "SELECT fingerprint FROM predictions ORDER BY fingerprint"
        )
        yield from (str(row[0]) for row in rows)

    def __len__(self) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) FROM predictions"
        ).fetchone()
        return int(row[0])

    def __contains__(self, fingerprint: object) -> bool:
        if not isinstance(fingerprint, str):
            return False
        if fingerprint in self._read_cache:
            return True
        row = self._connection.execute(
            "SELECT 1 FROM predictions WHERE fingerprint = ?",
            (fingerprint,),
        ).fetchone()
        return row is not None

    def content_sha256(self) -> str:
        digest = hashlib.sha256()
        digest.update(_canonical_json(self.identity))
        for fingerprint, payload_sha in self._connection.execute(
            """
            SELECT fingerprint, payload_sha256
            FROM predictions
            ORDER BY fingerprint
            """
        ):
            digest.update(str(fingerprint).encode("ascii"))
            digest.update(str(payload_sha).encode("ascii"))
        return digest.hexdigest().upper()

    def close(self) -> None:
        self._read_cache.clear()
        self._connection.close()

    def __enter__(self) -> "PredictionCache":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()
