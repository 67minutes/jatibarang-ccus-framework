# Feature 001 Data Model

## Grid2D

- `shape`: exactly `[64, 64]`
- `values`: exactly 4096 finite row-major values

## GeologyInput

- physical permeability in mD, porosity fraction, structure in metres
- fracture proxy, barrier, facies, well mask, completion mask
- anisotropy ratio, reservoir temperature, and physical grid dimensions
- all maps share the same fixed shape; physical fractions are bounded `[0, 1]`

## OperatingSchedule

- injection rate in surface-equivalent m3/day and its reference pressure/temperature
- injection, soak, and production durations in days
- production BHP in psi and positive cycle count
- state sequence: inject -> soak -> produce -> next cycle

## SeedHistory

- pre-operation pressure/gas/`z_co2` state
- exactly eight chronological pressure/gas/`z_co2` frames
- eight non-negative oil and gas production increments in surface m3
- `source_class`, `source_id`, and schedule fingerprint

## PredictionResult

- complete time axis and production series
- optional full spatial frames
- CO2 inventory/injected/produced-back series and reconciliation status
- plume/influence summaries
- extrapolation flags, confidence, and checkpoint/provenance metadata

## BatchPredictRequest

- unique geology and seed registries referenced by scenario definitions
- 1-256 scenarios
- zero to ten scenario IDs requesting full fields
