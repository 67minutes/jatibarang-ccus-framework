# Feature 003 Quickstart

Feature 003 is a Python/CoolProp runtime module with a separate offline DWSIM evidence
workflow. Normal screening never imports or starts DWSIM.

## Install and run focused tests

```powershell
python -m pip install -e ".[test,validation]"
python -m pytest -q tests/facility
```

The tracked runtime inputs are:

- `data/jatibarang/facility_design_basis.json`;
- `data/jatibarang/facility_cost_basis.json`;
- `data/jatibarang/facility_validation_cases.json`.

## Generate runtime-only evidence

```powershell
python -m jatibarang_ccus.infrastructure.facility_validation `
  --mode runtime-only `
  --cases data/jatibarang/facility_validation_cases.json `
  --design-basis data/jatibarang/facility_design_basis.json `
  --cost-basis data/jatibarang/facility_cost_basis.json `
  --output paper/validation/feature003-runtime-only
```

Runtime-only mode validates contracts, duties, monotonicity, accounting, and artifact
hashing but deliberately reports engineering validation as `UNVALIDATED`. The normal
in-envelope facility response carries the previously pinned DWSIM calibration status;
a new evidence run cannot inherit scientific PASS without reading matching DWSIM rows.

## Refresh the DWSIM reference

The installed DWSIM 10 automation assemblies target .NET Framework 4.7.2, so build
the helper with Visual Studio MSBuild:

```powershell
$env:DWSIM_HOME = "$env:LOCALAPPDATA\DWSIM"
$msbuild = 'C:\Program Files\Microsoft Visual Studio\2022\Community\MSBuild\Current\Bin\MSBuild.exe'
& $msbuild tools/dwsim/FacilityValidationRunner/FacilityValidationRunner.csproj `
  /t:Build /p:Configuration=Release

& tools/dwsim/FacilityValidationRunner/bin/Release/FacilityValidationRunner.exe `
  --model docs/dwsim-validation/jatibarang_facility.dwxmz `
  --cases data/jatibarang/facility_validation_cases.json `
  --output paper/validation/feature003/dwsim_reference.csv
```

Use `--create-model` only for an intentional topology rebuild. It changes the model
hash and requires all eight reference cases to be refreshed. Missing or non-converged
cases cause the runner or comparison workflow to fail.

## Compare and regenerate the tracked bundle

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

Promotion requires eight converged cases, power MAPE no greater than 5%, no power
point above 10% error, DWSIM residual no greater than 0.1%, monotonic screening
responses, exact ownership reconciliation, and matching artifact hashes.

The pinned bundle passes with `0.0000147%` total-power MAPE, `0.0000198%` maximum
power error, and zero reported DWSIM mass-balance residual.

## Complete regression

```powershell
python -m pytest -q
git diff --check
```

Feature 001 behavior and Feature 002 route/hydraulic/solver contracts remain
unchanged. Feature 005 still owns replacement of the analytic Phase 1 candidate proxy
with real batched surrogate outputs.
