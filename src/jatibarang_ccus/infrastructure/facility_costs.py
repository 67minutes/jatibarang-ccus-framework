from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Any, Literal


CostCase = Literal["low", "base", "high"]


@dataclass(frozen=True)
class BasisDocument:
    path: Path
    payload: dict[str, Any]
    sha256: str

    @property
    def version(self) -> str:
        return str(self.payload["version"])


def _canonical_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest().upper()


def load_basis(path: Path | str, *, expected_type: str) -> BasisDocument:
    resolved = Path(path).resolve()
    payload = json.loads(resolved.read_text(encoding="utf-8"))
    if payload.get("basis_type") != expected_type:
        raise ValueError(f"Expected {expected_type} at {resolved}, found {payload.get('basis_type')!r}.")
    if not payload.get("version") or not payload.get("schema_version"):
        raise ValueError(f"Basis file {resolved} is missing version metadata.")
    if "screening_proxy" not in str(payload.get("status", "")) and expected_type != "facility_validation_cases":
        raise ValueError(f"Basis file {resolved} must declare its screening-proxy status.")
    if expected_type == "facility_cost_basis":
        _validate_cost_basis(payload)
    return BasisDocument(path=resolved, payload=payload, sha256=_canonical_hash(payload))


def load_design_basis(path: Path | str) -> BasisDocument:
    return load_basis(path, expected_type="facility_design_basis")


def load_cost_basis(path: Path | str) -> BasisDocument:
    return load_basis(path, expected_type="facility_cost_basis")


def load_validation_cases(path: Path | str) -> BasisDocument:
    document = load_basis(path, expected_type="facility_validation_cases")
    cases = document.payload.get("cases", [])
    if len(cases) != 8 or len({case.get("case_id") for case in cases}) != 8:
        raise ValueError("Feature 003 calibration requires exactly eight uniquely identified cases.")
    return document


def _validate_cost_basis(payload: dict[str, Any]) -> None:
    required_equipment = {
        "injection_pump",
        "recycle_compressor",
        "intercooler",
        "dehydration",
        "three_phase_separator",
    }
    for case_name in ("low", "base", "high"):
        case = payload.get("cases", {}).get(case_name)
        if not case:
            raise ValueError(f"Missing facility cost case {case_name}.")
        if set(case.get("equipment", {})) != required_equipment:
            raise ValueError(f"Cost case {case_name} has an incomplete equipment coefficient set.")
        for equipment_type, coefficient in case["equipment"].items():
            for key in ("reference_duty", "duty_unit", "reference_cost_usd", "exponent", "installation_factor"):
                if key not in coefficient:
                    raise ValueError(f"{case_name}/{equipment_type} is missing {key}.")
            numeric = [
                coefficient["reference_duty"],
                coefficient["reference_cost_usd"],
                coefficient["exponent"],
                coefficient["installation_factor"],
            ]
            if not all(math.isfinite(float(value)) and float(value) > 0 for value in numeric):
                raise ValueError(f"{case_name}/{equipment_type} contains a non-positive coefficient.")


def train_counts(duty: float, *, maximum_per_train: float, spare_trains: int) -> tuple[int, int]:
    if duty <= 0:
        return 0, 0
    active = max(1, math.ceil(float(duty) / float(maximum_per_train)))
    return active, active + max(0, int(spare_trains))


def installed_equipment_capex(
    equipment_type: str,
    duty: float,
    *,
    duty_train_count: int,
    installed_train_count: int,
    cost_basis: BasisDocument,
    cost_case: CostCase,
) -> float:
    if duty <= 0 or duty_train_count <= 0 or installed_train_count <= 0:
        return 0.0
    coefficient = cost_basis.payload["cases"][cost_case]["equipment"][equipment_type]
    per_train_duty = float(duty) / float(duty_train_count)
    scaled = float(coefficient["reference_cost_usd"]) * (
        per_train_duty / float(coefficient["reference_duty"])
    ) ** float(coefficient["exponent"])
    return scaled * float(coefficient["installation_factor"]) * int(installed_train_count)


def annual_opex(
    *,
    power_kw: float,
    operating_hours_per_year: float,
    capex_usd: float,
    cost_basis: BasisDocument,
    cost_case: CostCase,
) -> tuple[float, float, float]:
    case = cost_basis.payload["cases"][cost_case]
    energy = max(0.0, float(power_kw)) * max(0.0, float(operating_hours_per_year)) * float(
        case["electricity_usd_per_kwh"]
    )
    maintenance = max(0.0, float(capex_usd)) * float(case["maintenance_fraction"])
    return energy, maintenance, energy + maintenance


def balance_of_plant_capex(direct_capex_usd: float, *, cost_basis: BasisDocument, cost_case: CostCase) -> float:
    fraction = float(cost_basis.payload["cases"][cost_case]["balance_of_plant_fraction"])
    return max(0.0, float(direct_capex_usd)) * fraction
