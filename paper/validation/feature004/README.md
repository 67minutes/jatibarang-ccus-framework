# Feature 004 Economic-Engine Validation

This directory is the tracked promotion bundle for the independently runnable
Feature 004 economic engine. The fixtures are deterministic screening examples;
they are not Jatibarang field forecasts or exact PSC calculations.

## Artifacts

- `reference_cashflows.csv` contains year-0 through year-8 component cash flows.
- `accounting_reconciliation.csv` records USD and storage cross-check residuals.
- `metric_verification.json` checks a closed-form IRR, fractional payback, and
  multiple/no-root statuses.
- `carbon_price_sensitivity.csv` records the four pinned price cases under all
  three parametric fiscal modes.
- `uncertainty_ranking.csv` records low/base/high ordering and stability.
- `performance_benchmark.json` records the warmed 200 x 4 x 3 gate over the three
  active campaign years with 200 distinct cash-flow vectors.
- `schema_validation.json` records request/result JSON Schema validation.
- `validation_summary.json` separates the promotion verdict from qualification.
- `artifact_manifest.json` carries SHA-256 hashes for every other artifact here.

## Interpretation boundary

`accounting_verdict = PASS` means the cash-flow identities reconcile within the
Feature 004 tolerance. `promotion_verdict = PASS` additionally requires metric,
schema, manifest, and local performance gates. Neither verdict upgrades the
economic basis beyond screening-grade parametric fiscal sensitivity. Feature 005
coupling, A/B/C execution, and final-paper economic claims remain pending.

## Reproduce

```powershell
python -m jatibarang_ccus.infrastructure.economic_validation `
  --basis data/jatibarang/economic_basis.json `
  --output paper/validation/feature004

python -m jatibarang_ccus.infrastructure.economic_validation `
  --output paper/validation/feature004 --verify-only
```
