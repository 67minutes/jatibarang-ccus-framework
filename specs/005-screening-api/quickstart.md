# Feature 005 Quickstart

## Prerequisites

Install the existing package/test dependencies, place the promoted checkpoint and
terrain raster at their documented local paths, install CBC, and materialize at least
the demo preset payload described in `data/screening_presets/README.md`.

```powershell
python -m pip install -e ".[test]"
```

## Test and validate

```powershell
python -m pytest -q tests/screening
python -m pytest -q
python -m jatibarang_ccus.screening.validation `
  --preset jatibarang_demo_v1 `
  --output paper/validation/feature005
python -m jatibarang_ccus.screening.validation `
  --output paper/validation/feature005 --verify-only
```

The validation command never calls MRST or DWSIM. A missing ignored preset payload is
reported as `BLOCKED` with exit code `2`, not replaced with synthetic data. The
subsequent `--verify-only` command still validates the blocked bundle's hashes.

Generate a deterministic upstream design and import completed derived exports with:

```powershell
python -m jatibarang_ccus.screening.preset_builder design `
  --preset jatibarang_demo_v1
python -m jatibarang_ccus.screening.preset_builder import `
  --design data/screening_presets/jatibarang_demo_v1/upstream_design.json `
  --seed-root C:\Users\mauli\Documents\boreyes2026\exports_feature005_demo
```

MRST executes only in the upstream repo and never inside the API or validation CLI.

## Serve

```powershell
uvicorn jatibarang_ccus.api.app:app --app-dir src --host 127.0.0.1 --port 8000
```

Use `GET /health` and `GET /presets`, then submit a small preset request:

```json
{"mode":"preset","preset_id":"jatibarang_demo_v1"}
```

`POST /screen/stream` returns SSE. The first event supplies the run ID; send
`DELETE /screen/runs/{run_id}` for cooperative cancellation.

## Interpretation

Mechanical PASS proves typed orchestration, accounting reconciliation, propagation,
and endpoint behavior. It does not promote a carbon-price pivot or final paper NPV.
The full 3240-scenario execution remains a Feature 007 paper run.
