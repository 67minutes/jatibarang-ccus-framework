# Feature 003 DWSIM Validation

This directory contains the tracked offline process model and process-flow diagram
used to validate the Feature 003 thermodynamic duty correlations. DWSIM is never
imported or launched by the screening runtime.

## Recorded verdict

- Mechanical evidence: **PASS**.
- Engineering validation: **PASS** across eight converged cases.
- Compressor power MAPE: `0.0000165%`.
- Pump power MAPE: `0.0000000074%`.
- Total-power MAPE: `0.0000147%`.
- Maximum individual power error: `0.0000198%`.
- Maximum DWSIM stream mass-balance residual: `0.0%`.
- DWSIM version: `10.0.9650.13551`.
- Model SHA-256:
  `c9e966f194d3178905a11b9ffc65ed158902006bca8d80b5817c2ad743abfdb0`.

The very small duty differences are expected because both implementations use
CoolProp state properties. DWSIM remains an independent flowsheet and unit-operation
calculation path, not an independent equation-of-state validation.

## Tracked files

- `jatibarang_facility.dwxmz`: solved, compressed DWSIM source flowsheet.
- `process_flow_diagram.png`: publication-ready ownership and process boundary.
- `methodology.md`: case matrix, topology, error gates, and limitations.

The comparison tables, plots, verdicts, and hashes are under
`paper/validation/feature003/`.

## Model scope

The model contains a pure-CO2 equivalent production boundary, `SEP-01`, a labeled
dehydration boundary, three recycle compressors, three coolers, a fresh/recycle
mixer, and the wellhead injection pump. The final recycle cooler returns CO2 to
`27 C` before mixing, which preserves a dense pump-suction state at the 80 bar edge
of the envelope.

DWSIM validates recycle compression, cooling, combined-stream pump duty, convergence,
and mass balance. Python separately sizes the separator from gas and assumed liquid
loads and applies the tracked screening cost correlations. No DWSIM result is
presented as native CAPEX, a vendor quote, or FEED.

## Refresh

Set `DWSIM_HOME` to a DWSIM installation containing `DWSIM.Automation.dll`, then use
Visual Studio MSBuild because the DWSIM 10 automation assemblies target .NET Framework
4.7.2:

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

Use `--create-model` only when intentionally rebuilding the topology. A model rebuild
changes the pinned model hash and requires a complete eight-case comparison refresh.

The official automation surface is documented by the
[DWSIM automation guide](https://dwsim.org/wiki/index.php?title=Automation) and
[Automation API](https://dwsim.org/api_help/html/N_DWSIM_Automation.htm).
