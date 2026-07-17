# Feature 001 Quickstart

## Prerequisites

1. Python 3.11+ environment.
2. The promoted checkpoint in `models/checkpoints/` with the pinned SHA-256.
3. Optional local five-case files under `data/validation_cases/` for scientific validation.

Install the package and test dependencies from the repository root:

```powershell
python -m pip install -e ".[test]"
```

## Validate

```powershell
python -m pytest -q
python -m jatibarang_ccus.surrogate.validation --skip-benchmark
```

The test suite must pass without importing the upstream training repository. The
validation command refreshes the five-case CSV/JSON reports when the ignored local
MRST files are available. Omit `--skip-benchmark` to repeat the full `200 x 24`
performance gate; the recorded CPU run takes about five minutes.

Current tracked evidence:

- 41 tests: **PASS**;
- five-case validation: **PASS mechanically; CONDITIONAL scientifically**;
- warm one-step p95: `0.0737 s`;
- 24-step rollout p95: `1.7610 s`;
- compact `200 x 24` batch: `281.12 s`, `806,875,136` bytes peak RSS.

## Serve

```powershell
uvicorn jatibarang_ccus.api.app:app --app-dir src --host 127.0.0.1 --port 8000
```

Verify `GET /model/info`, then use `POST /predict` for a detailed result or
`POST /predict/batch` for compact screening summaries. Out-of-range but structurally
valid controls return predictions with flags rather than HTTP errors.

Open `http://127.0.0.1:8000/docs` for the generated request/response schema. The saved
contract is [`contracts/openapi.yaml`](contracts/openapi.yaml).

## Required warm start

Every prediction requires:

- a pre-operation pressure/gas-saturation/`z_co2` state;
- exactly eight chronological physical state frames;
- eight seed-period oil and gas production increments;
- seed provenance and a fingerprint matching the declared schedule used to construct
  the eight seed control frames.

Feature 001 intentionally rejects cold starts. A caller must provide an MRST,
field-observed, or explicitly derived seed whose provenance is serialized in the
response.

## Result interpretation

- Full 3-cycle and 4-cycle forecasts contain 28 and 40 predicted frames after the
  eight-frame seed.
- Forecast steps beyond 24 carry an extended-horizon low-confidence reason.
- Inventory tonnes and produced-back CO2 are engineering approximations based on
  pore volume, gas saturation, `z_co2`, and CoolProp density; they are not direct
  outputs from a produced-CO2 model head.
- Batch responses omit full spatial frames by default. At most ten scenario IDs may
  request them through `full_field_scenario_ids`.
