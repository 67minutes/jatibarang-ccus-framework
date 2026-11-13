"""Materialize compact per-well reservoir artifacts from an upstream design."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from .mrst import write_derived_reservoir


def build_reservoir_catalog(
    design_path: Path,
    source_root: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Write derived-only NPZ files and a frontend-loadable JSON catalog."""

    design_path = Path(design_path).resolve()
    source_root = Path(source_root).resolve()
    output_root = Path(output_root).resolve()
    design = json.loads(design_path.read_text(encoding="utf-8"))
    geologies = design.get("geologies")
    if not isinstance(geologies, list) or not 1 <= len(geologies) <= 20:
        raise ValueError("upstream design must declare 1 to 20 geologies")

    entries: list[dict[str, Any]] = []
    expected_ids = [f"W{index:02d}" for index in range(1, len(geologies) + 1)]
    for expected_id, item in zip(expected_ids, geologies, strict=True):
        if not isinstance(item, dict) or item.get("candidate_id") != expected_id:
            raise ValueError(
                f"upstream geologies must be ordered contiguously; expected {expected_id}"
            )
        source_name = item.get("source_output_file")
        if not isinstance(source_name, str) or Path(source_name).name != source_name:
            raise ValueError(f"{expected_id} has an unsafe source_output_file")
        source = source_root / source_name
        if not source.is_file():
            raise FileNotFoundError(f"MRST source is missing for {expected_id}: {source}")
        case_id = str(item.get("source_case_id", Path(source_name).stem))
        target = output_root / "reservoirs" / f"{expected_id}--{case_id}.reservoir.npz"
        derived_sha256 = write_derived_reservoir(source, target)
        entries.append(
            {
                "well_id": expected_id,
                "model_path": str(target),
                "bank_path": None,
                "source_case_id": case_id,
                "derived_sha256": derived_sha256,
            }
        )

    catalog = {
        "schema_version": "1.0",
        "design_id": design.get("design_id"),
        "design_sha256": design.get("design_sha256"),
        "artifact_policy": "derived_static_maps_and_eight_frame_seed_only",
        "raw_training_corpus_copied": False,
        "entries": entries,
    }
    output_root.mkdir(parents=True, exist_ok=True)
    catalog_path = output_root / "reservoir_catalog.json"
    catalog_path.write_text(
        json.dumps(catalog, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {**catalog, "catalog_path": str(catalog_path)}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build compact per-well reservoir artifacts without copying MRST targets."
    )
    parser.add_argument("--design", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_reservoir_catalog(args.design, args.source_root, args.output_root)
    print(json.dumps({
        "catalog_path": result["catalog_path"],
        "count": len(result["entries"]),
        "raw_training_corpus_copied": result["raw_training_corpus_copied"],
    }))


if __name__ == "__main__":
    main()
