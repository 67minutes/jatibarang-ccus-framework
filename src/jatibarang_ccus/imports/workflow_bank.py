"""Compile one common-schedule MRST smoke export into per-well launch-pad banks."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from .launchpads import write_launchpad_bank
from .mrst import load_mrst_reservoir


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def build_workflow_launchpad_catalog(
    catalog_path: Path,
    exporter_manifest_path: Path,
    output_root: Path,
) -> dict[str, Any]:
    """Attach one real, shared-fingerprint launch-pad bank to every catalog well."""

    catalog = json.loads(Path(catalog_path).read_text(encoding="utf-8"))
    manifest_path = Path(exporter_manifest_path).resolve()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = manifest.get("entries", [])
    if isinstance(entries, dict):
        entries = [entries]
    if (
        manifest.get("completed_runs") != manifest.get("requested_runs")
        or manifest.get("completed_runs") != len(entries)
    ):
        raise ValueError("workflow MRST exporter manifest is incomplete")
    if manifest.get("raw_training_corpus_copied") is not False:
        raise ValueError("workflow exporter must declare raw_training_corpus_copied=false")
    by_well = {str(item.get("candidate_id")): item for item in entries}
    catalog_entries = catalog.get("entries", [])
    if not isinstance(catalog_entries, list) or set(by_well) != {
        str(item.get("well_id")) for item in catalog_entries
    }:
        raise ValueError("workflow exporter wells do not match the reservoir catalog")

    output_root = Path(output_root).resolve()
    banks_dir = output_root / "banks"
    banks_dir.mkdir(parents=True, exist_ok=True)
    updated = []
    fingerprints: set[str] = set()
    for item in catalog_entries:
        well_id = str(item["well_id"])
        exported = by_well[well_id]
        output_file = str(exported.get("output_file", ""))
        if Path(output_file).name != output_file:
            raise ValueError(f"unsafe exporter output_file for {well_id}")
        seed_path = manifest_path.parent / output_file
        if not seed_path.is_file():
            raise FileNotFoundError(f"workflow seed is missing for {well_id}: {seed_path}")
        expected_sha = str(exported.get("output_sha256", "")).upper()
        if len(expected_sha) != 64 or _sha256(seed_path) != expected_sha:
            raise ValueError(f"workflow seed SHA-256 mismatch for {well_id}")
        if str(exported.get("source_case_id")) != str(item.get("source_case_id")):
            raise ValueError(f"workflow source case mismatch for {well_id}")
        imported = load_mrst_reservoir(seed_path)
        fingerprint = str(exported.get("schedule_fingerprint", "")).upper()
        if imported.seed.schedule_fingerprint.upper() != fingerprint:
            raise ValueError(f"workflow schedule fingerprint mismatch for {well_id}")
        fingerprints.add(fingerprint)
        bank_path = banks_dir / f"{well_id}.launchpads.npz"
        bank_sha256 = write_launchpad_bank(bank_path, {fingerprint: imported.seed})
        updated.append(
            {
                **item,
                "bank_path": str(bank_path),
                "bank_sha256": bank_sha256,
                "workflow_schedule_fingerprint": fingerprint,
            }
        )
    if len(fingerprints) != 1:
        raise ValueError("workflow launch-pad banks do not share one schedule fingerprint")

    output = {
        **catalog,
        "entries": updated,
        "workflow_smoke": {
            "purpose": "end_to_end_ui_smoke_not_paper_evidence",
            "schedule_fingerprint": next(iter(fingerprints)),
            "exporter_manifest": str(manifest_path),
            "exporter_manifest_sha256": _sha256(manifest_path),
            "raw_training_corpus_copied": False,
        },
    }
    output_path = output_root / "reservoir_catalog.workflow.json"
    output_path.write_text(json.dumps(output, indent=2, sort_keys=True), encoding="utf-8")
    return {**output, "catalog_path": str(output_path)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Build real one-schedule per-well launch-pad banks.")
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--exporter-manifest", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    args = parser.parse_args()
    result = build_workflow_launchpad_catalog(
        args.catalog,
        args.exporter_manifest,
        args.output_root,
    )
    print(json.dumps({
        "catalog_path": result["catalog_path"],
        "count": len(result["entries"]),
        "schedule_fingerprint": result["workflow_smoke"]["schedule_fingerprint"],
    }))


if __name__ == "__main__":
    main()
