# Feature 001: Subsurface Surrogate Inference Service

## Purpose

Wrap the existing pre-trained ED-ConvLSTM surrogate as a stateless inference service
that, given a geology and a set of operational parameters, returns the predicted CO₂
plume evolution, pressure/saturation fields, and production profile. This is the
foundation every other module depends on. **The model is frozen — this feature is
inference and serving only, no retraining, no architecture changes.**

## The Model (as built, do not modify)

- Designation: `Model B`, `production_v2`, `Tin = 8`.
- Channels: 13 dynamic input channels, 12 static input channels.
- Backbone: static geology encoder (12 → 32 → 48 → 32), full-resolution ConvLSTM
  (hidden 48), downsample 48 → 64, half-resolution ConvLSTM (hidden 96), CBAM
  attention bottleneck, transpose upsample, skip decode to 32.
- Heads:
  - Map head: `pressure_next`, `gas_sat_next`, `z_co2_next`.
  - Oil map head: `oil_sat_next`.
  - Production MLP: → `delta_oil_next`, `delta_gas_next`.
  - Stage experts: 3 residual heads (injection / soak / produce).
  - Transition gas-fraction correction head: gated for soak→produce contexts.
- Parameter count: ~891k.
- Reporting checkpoint: the promoted checkpoint per the repo's project facts file.
  Inference must load whichever checkpoint is designated as the promoted/reporting
  checkpoint, not an arbitrary one. The checkpoint path is a configuration value, not
  hard-coded.

## Inputs

A single inference request describes one geology + one operational scenario:

- **Static geology maps** (per the model's 12 static channels): permeability map,
  porosity map, structure map, fracture proxy map, barrier map, facies map, well mask,
  completion mask, plus any derived static channels the checkpoint expects. The exact
  channel order and any normalization must match the training pipeline exactly — copy
  the channel definition and the normalization constants from the training repo; do
  not re-derive them.
- **Dynamic seed history** (`Tin = 8` timesteps × 13 dynamic channels): pressure,
  gas saturation, z_co2, oil saturation, stage flags, controls, dt, cycle info. For a
  forward screening run the seed is the initial condition sequence.
- **Scalar controls**: injection rate, production BHP, cycle count, stage timing
  (inject / soak / produce durations).

## Outputs

- **Spatial field frames** per output timestep: `pressure`, `gas_sat`, `z_co2`,
  `oil_sat` on the 64×64 grid. Returned as arrays the frontend can colormap.
- **Production series**: per-timestep `delta_oil`, `delta_gas`, and the externally
  accumulated `cumulative_oil`, `cumulative_gas`. Cumulative quantities are computed
  by summing deltas (never predicted directly), preserving monotonicity by
  construction.
- **CO₂ inventory series**: total CO₂ in reservoir per timestep, derived from the
  `z_co2` × `gas_sat` × pore-volume integral over the grid. Used downstream for net
  storage. (See Module 4 spec for how net stored CO₂ is computed and its uncertainty.)
- **Extrapolation flags**: for each scalar control and aggregate geology statistic,
  a boolean indicating whether the input fell outside the trained range (see
  constitution Data Constraints). Any true flag must be returned and propagated.
- **Confidence metadata**: rollout horizon reached, and the documented accuracy band
  for that horizon (e.g. one-step vs. T+5 vs. T+10+), so downstream modules can attach
  uncertainty.

## Behavior Rules

- Stateless. Each request is independent. The checkpoint is loaded once at service
  startup and held in memory.
- CPU inference only. No GPU assumption.
- Deterministic. Same input → same output (eval mode, no dropout, fixed seeds where
  any sampling exists).
- Batch endpoint required: screening sends hundreds of scenarios; the service must
  accept a batch and return results efficiently rather than forcing per-scenario HTTP
  round-trips.
- Never silently extrapolate. If inputs are out of range, predict anyway but flag it
  loudly in the response.

## Endpoints

- `POST /predict` — one scenario → full field frames + production + inventory + flags.
- `POST /predict/batch` — many scenarios → array of the above, optimized for throughput.
- `GET /model/info` — checkpoint id, channel definitions, trained ranges, documented
  accuracy bands. Single source of truth the frontend and other modules read.

## Dependencies

- PyTorch (CPU build).
- The model architecture definition and checkpoint loader, copied self-contained from
  the training repo (`boreyes2026`) so this service runs without the full training
  codebase.
- NumPy.

## Done Criteria

- [ ] Promoted checkpoint loads at startup; `GET /model/info` reports its id and the
      trained ranges.
- [ ] `POST /predict` reproduces, within numerical tolerance, the surrogate's known
      metrics on a held-out test case from the training repo (regression guard against
      a broken port).
- [ ] Channel order and normalization verified identical to training (documented test
      comparing against a reference tensor exported from `boreyes2026`).
- [ ] Cumulative production is monotonic for all test cases (zero violations).
- [ ] Out-of-range inputs produce extrapolation flags.
- [ ] Batch endpoint handles ≥200 scenarios in a single call.
- [ ] Single-scenario latency is well under one second on CPU.
