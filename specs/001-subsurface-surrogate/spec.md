# Feature 001: Subsurface Surrogate Inference Service

## Purpose

Wrap the existing pre-trained ED-ConvLSTM surrogate as a stateless inference service
that, given a geology and a set of operational parameters, returns the predicted CO₂
plume evolution, pressure/saturation fields, and production profile. This is the
foundation every other module depends on. **The model is frozen — this feature is
inference and serving only, no retraining, no architecture changes.**

## The Model (as built, do not modify)

- Designation: `Model B`, `production_v2`, `Tin = 8`.
- Channels: 20 stored dynamic channels, of which the promoted checkpoint consumes
  channels 0-12 (13 channels), plus 12 static input channels. Stored transition
  channels 13-19 are retained for tensor compatibility but are not consumed because
  the promoted checkpoint has `use_transition_features = false`.
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
- **Physical dynamic seed history** (`Tin = 8` timesteps): pressure, gas saturation,
  and `z_co2` maps plus seed-period oil/gas production increments. The service builds
  the 20 stored dynamic channels from the seed and schedule. Oil saturation is an
  output, not an autoregressive input. A pre-operation state and seed provenance are
  required; Feature 001 never invents a cold start or calls MRST at runtime.
- **Scalar controls**: injection rate, production BHP, cycle count, stage timing
  (inject / soak / produce durations).
- **Grid physics**: physical grid dimensions/cell volume and reservoir temperature,
  used for the qualified CO2 inventory estimate in tonnes.

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
- Batch responses are compact by default. Full spatial frames may be requested for at
  most ten named scenarios in a call.
- Never silently extrapolate. If inputs are out of range, predict anyway but flag it
  loudly in the response.

## Endpoints

- `POST /predict` — one scenario → full field frames + production + inventory + flags.
- `POST /predict/batch` — many scenarios → array of the above, optimized for throughput.
- `GET /model/info` — checkpoint id, channel definitions, trained ranges, documented
  accuracy bands. Single source of truth the frontend and other modules read.

## Dependencies

- PyTorch (CPU build).
- FastAPI and Pydantic v2 for the service boundary.
- CoolProp for CO2 density and surface-reference mass conversion.
- The model architecture definition and checkpoint loader, copied self-contained from
  the training repo (`boreyes2026`) so this service runs without the full training
  codebase.
- NumPy.

## Done Criteria

- [x] Promoted checkpoint loads at startup; `GET /model/info` reports its id and the
      trained ranges.
- [x] `POST /predict` reproduces, within numerical tolerance, the surrogate's known
      metrics on a held-out test case from the training repo (regression guard against
      a broken port).
- [x] Channel order and normalization verified identical to training (documented test
      comparing against a reference tensor exported from `boreyes2026`).
- [x] Cumulative production is monotonic for all test cases (zero violations).
- [x] Out-of-range inputs produce extrapolation flags.
- [x] Batch endpoint handles at least 200 scenarios in a single call.
- [x] Warm one-step latency is under one second on CPU; a 24-step single rollout is
      under three seconds on the paper hardware, with 200-scenario throughput and
      memory recorded in a benchmark artifact.

## Locked Training and Rollout Constraints

- Schedule discretization is four injection frames, two soak frames, and six
  production frames per cycle.
- Injection duration: 45-60 days.
- Soak duration: 25-35 days.
- Production duration: 170-210 days.
- Three cycles require 28 predicted frames after the seed; four cycles require 40.
- Upstream metrics validate free rollout through 24 predicted steps. Longer rollouts
  must carry an extended-horizon low-confidence flag.

## Completion Status

Feature 001 is implemented. The complete repository suite has 41 passing tests, the
five-case local validation is mechanically **PASS** and scientifically
**CONDITIONAL**, and the recorded performance gate is **PASS**:

- warm one-step p95: `0.0737 s`;
- 24-step rollout p95: `1.7610 s`;
- compact `200 x 24` batch: `281.12 s` with `806,875,136` bytes peak RSS.

The scientific qualification is part of the contract, not an unfinished code task:
inventory/produced-back CO2 is an engineering approximation, the local validation
bundle contains five curated cases, and forecast steps beyond 24 are marked as
extended-horizon low confidence. Integration into the coupled screening workflow is
owned by Feature 005.
