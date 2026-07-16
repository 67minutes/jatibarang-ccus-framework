from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class LedgerEntry:
    key: str
    value: int | float | str
    units: str
    source: str
    method: str
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def entry(
    key: str,
    value: int | float | str,
    units: str,
    source: str,
    method: str,
    timestamp: str,
) -> LedgerEntry:
    return LedgerEntry(key=key, value=value, units=units, source=source, method=method, timestamp=timestamp)

