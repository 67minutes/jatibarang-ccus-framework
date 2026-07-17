# Feature 002 Quickstart

## Prerequisites

Install the project and tests, ensure CBC is on `PATH`, and place the pinned West Java
SRTM raster at the path documented in `data/terrain/README.md`.

```powershell
python -m pip install -e ".[test,validation]"
cbc -stop
```

## Focused verification

```powershell
python -m pytest -q tests/infrastructure
```

Expected: routing, exclusion, hydraulic, MILP, multi-source, empty-portfolio, trucking,
and accounting tests pass.

## Full Jatibarang evidence run

```powershell
python -m jatibarang_ccus.infrastructure.validation `
  --assumptions data/jatibarang/case_study_assumptions.json `
  --output paper/validation/feature002
```

Expected: the full 20-well CBC solve completes within 30 seconds at <=2% gap, every
active segment passes continuous pressure/velocity/MAOP verification, and the output
directory contains the machine-readable audit plus route, pressure, hydraulic-curve,
cost, and solver figures/tables.

## Complete regression

```powershell
python -m pytest -q
```

Feature 001 request/response and saved OpenAPI contracts must remain unchanged.

