# Jatibarang CCUS Framework

Spec Kit workspace for an integrated CO2 Huff-and-Puff CCUS screening and
planning framework for Jatibarang-class fractured carbonate reservoirs.

The repo is organized around the paper/demo framework, not the upstream training
pipeline. The frozen surrogate checkpoint and selected derived validation
artifacts are consumed here; the 177-case MRST training corpus stays in
`C:\Users\mauli\Documents\boreyes2026`.

## Start Here

- Project rules: `.specify/memory/constitution.md`
- Feature specs: `specs/`
- Active Spec Kit feature pointer: `.specify/feature.json`
- Local checkpoint drop zone: `models/checkpoints/`
- Local data drop zones: `data/terrain/`, `data/validation_cases/`,
  `data/scenario_b_runs/`

## Feature Map

1. `specs/001-subsurface-surrogate/` - frozen surrogate inference service
2. `specs/002-pipeline-optimizer/` - CO2 routing and logistics
3. `specs/003-facility-model/` - surface facility sizing and cost model
4. `specs/004-economic-engine/` - Indonesian carbon-regulation economics
5. `specs/005-screening-api/` - coupled screening API
6. `specs/006-frontend/` - live demo frontend
7. `specs/007-paper-figures/` - paper and presentation figures

## Data Policy

Commit small source/configuration data that the app needs to run. Keep large
binary artifacts out of git:

- PyTorch checkpoints: `models/checkpoints/`
- SRTM/terrain rasters: `data/terrain/`
- Full MRST plume-validation cases: `data/validation_cases/`
- Scenario B limited-simulation runs/results: `data/scenario_b_runs/`

Tiny surrogate regression fixtures may live in `tests/fixtures/surrogate/` when
they are intentionally small enough to review and version.
