# Feature 004 Quickstart

## Install and test

```powershell
python -m pip install -e ".[test]"
python -m pytest -q tests/economics
```

## Generate and verify evidence

```powershell
python -m jatibarang_ccus.infrastructure.economic_validation `
  --basis data/jatibarang/economic_basis.json `
  --output paper/validation/feature004

python -c "from jatibarang_ccus.infrastructure.economic_validation import verify_artifact_manifest; assert not verify_artifact_manifest('paper/validation/feature004/artifact_manifest.json')"
```

The evidence CLI runs closed-form metric cases, storage/accounting cases, a synthetic
carbon-price ranking pivot, and the warmed 200 x 4 x 3 performance benchmark. It does
not run MRST, DWSIM, the Feature 005 API, or the final A/B/C study.

## Interpretation

- Final pipeline evaluation must use `pipeline_raw`; do not pass Feature 002's
  levelized delivered cost in addition to raw network costs.
- Missing project years mean zero physical activity. The engine never repeats the
  supplied campaign.
- Post-fiscal results are parameter sensitivities, not exact PSC statements.
- `accounting_verdict = PASS` proves internal reconciliation. The evidence remains
  scientifically and fiscally screening-grade because physical and fiscal assumptions
  are not field-contract data.

