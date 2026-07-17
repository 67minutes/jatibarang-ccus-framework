# Feature 003 Validation Evidence

This directory is the reproducible validation bundle for the surface-facility model.

## Verdict

- Mechanical verdict: **PASS**.
- Engineering validation verdict: **PASS**.
- Cases: 8/8 converged.
- Compressor/pump/total-power MAPE: `0.0000165%`, `0.0000000074%`, and
  `0.0000147%`.
- Maximum individual power error: `0.0000198%`.
- Maximum DWSIM mass-balance residual: `0.0%`.
- Monotonic screening sweep and exact ownership reconciliation: **PASS**.

This is an offline fixed-flowsheet comparison. It validates thermodynamic duties and
mass balance inside the pinned envelope; it does not turn screening cost correlations
into FEED or vendor estimates.

## Files

- `dwsim_reference.csv`: eight native DWSIM results with version and source hashes.
- `runtime_comparison.csv`: runtime values, DWSIM values, and pointwise errors.
- `correlation_error_summary.json`: thresholds and separate mechanical/engineering
  verdicts.
- `process_mass_balance.csv`: runtime loss-ledger reconciliation and DWSIM residuals.
- `equipment_cost_curve.csv`: seven-point monotonic Python screening-cost sweep.
- `facility_validation.png` and `facility_cost_curve.png`: paper-ready plots.
- `artifact_manifest.json`: SHA-256 ledger for every evidence artifact and input.

The process model, PFD, and detailed method are in `docs/dwsim-validation/`.

## Regenerate and verify

Refresh `dwsim_reference.csv` with the offline runner documented in
`docs/dwsim-validation/README.md`, then run:

```powershell
python -m jatibarang_ccus.infrastructure.facility_validation `
  --mode compare `
  --cases data/jatibarang/facility_validation_cases.json `
  --design-basis data/jatibarang/facility_design_basis.json `
  --cost-basis data/jatibarang/facility_cost_basis.json `
  --dwsim-reference paper/validation/feature003/dwsim_reference.csv `
  --output paper/validation/feature003

python -c "from jatibarang_ccus.infrastructure.facility_validation import verify_artifact_manifest; assert not verify_artifact_manifest('paper/validation/feature003/artifact_manifest.json')"
```

A runtime-only evidence run intentionally reports engineering validation as
`UNVALIDATED`; only compare mode with eight matching, converged DWSIM rows can emit an
engineering `PASS`.
