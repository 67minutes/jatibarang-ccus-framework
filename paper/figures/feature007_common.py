"""Shared loading and honesty gates for Feature 007 figure scripts."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BUNDLE = ROOT / "paper" / "results" / "feature007" / "working"


class FigureBlockedError(RuntimeError):
    """Raised when a paper panel lacks its declared real evidence."""


def parser(figure_number: int, description: str) -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=description)
    result.add_argument("--bundle", type=Path, default=DEFAULT_BUNDLE)
    result.set_defaults(figure_number=str(figure_number))
    return result


def load_manifest(bundle: Path) -> dict[str, Any]:
    path = bundle / "manifest.json"
    if not path.exists():
        raise FigureBlockedError(
            f"Feature 007 bundle is absent: {path}. Build it before generating figures."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def require_ready(bundle: Path, number: str) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = load_manifest(bundle)
    figure = manifest.get("figures", {}).get(number)
    if not figure:
        raise FigureBlockedError(f"bundle does not declare Figure {number}")
    if figure.get("status") != "ready":
        blockers = "; ".join(figure.get("blockers", [])) or "unspecified dependency"
        raise FigureBlockedError(f"Figure {number} is BLOCKED: {blockers}")
    return manifest, figure


def load_table(bundle: Path, manifest: dict[str, Any], name: str) -> list[dict[str, str]]:
    record = manifest.get("tables", {}).get(name)
    if not record:
        raise FigureBlockedError(f"bundle table is unavailable: {name}")
    path = bundle / record["path"]
    if not path.exists():
        raise FigureBlockedError(f"bundle table is missing: {path}")
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def blocked_main(function) -> int:
    try:
        function()
    except FigureBlockedError as exc:
        print(str(exc))
        return 2
    return 0
