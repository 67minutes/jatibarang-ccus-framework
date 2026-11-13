# Feature 007: Paper-Locked Results and Reservoir Visualization

## Purpose

Produce the APECX 2026 numerical evidence, publication figures, normalized result
tables, and interactive paper-result views from one provenance-locked source. The
Matplotlib figures remain the publication renderer. Frontend parity means identical
values, units, selections, limits, source classes, and qualification state; it does
not mean reproducing the paper's pixel layout.

Feature 007 consumes the implemented Features 001-005 and offline MRST/DWSIM
evidence. It must never replace a missing scientific result with a development
proxy, synthetic plume, or relabeled field.

## Canonical result bundles

Every paper-facing result is assembled under
`paper/results/feature007/<bundle_id>/`. A bundle contains:

- a manifest with the actual scenario count, experiment definitions, hashes,
  seeds, source classes, readiness, validation verdicts, and freeze basis;
- normalized CSV/JSON tables consumed by both Matplotlib and the frontend;
- hash-referenced reservoir payloads for spatial comparison; and
- one readiness record per Figure 1-8, including explicit blockers.

`working` is reproducible and may be rebuilt as evidence arrives. `submitted` is
created only by the freeze command from a scientifically ready, hash-valid 200- or
3,240-scenario bundle and is never overwritten. If the complete 3,240-scenario run
finishes after submission, it is frozen separately as `full_3240`; it does not
change the submitted result.

Missing inputs remain `pending` or `unavailable`. Mechanical hash verification is
not the same as a scientific or paper-promotion verdict.

## Execution and freeze policy

1. Finish and promote `jatibarang_demo_v1`: 20 geologies x 10 schedules = 200
   scenarios.
2. Reuse those outputs while continuing `jatibarang_full_v1`: 20 x 162 = 3,240
   scenarios.
3. Benchmark three MRST exports before launching the bank. Then set concurrency to
   `min(4, floor((available RAM - 3 GiB) / peak worker RSS), floor(physical cores / 2))`.
   Workers write separate deterministic shards, which are resumed and hash-merged.
4. At the July 21, 2026 18:00 WIB freeze, use 3,240 only if every designed case and
   hash is complete. Otherwise freeze the promoted 200-scenario result and display
   that count everywhere.

Raw MRST files stay in `boreyes2026`. This repository imports only derived static
maps, warm histories, compact results, and manifests required to run, validate, or
write up the framework.

## Locked A/B/C experiment

### Arm A: fixed current-practice schedule

Apply one schedule to all 20 candidate geologies:

- injection rate: 9,000 m3/day;
- injection duration: 45 days;
- soak duration: 30 days;
- production duration: 190 days;
- production BHP: 675 psi; and
- cycles: 3.

Confirm the declared median- and low-permeability representatives with MRST.

### Arm B: limited full-physics search

Use exactly 40 accepted MRST scenarios: two schedules per geology selected by
seeded normalized maximin sampling across injection rate, soak duration, production
duration, production BHP, and cycles. Permanently failed attempts stay in the audit;
the next deterministic same-geology replacement is run until 40 accepted results
exist. A partial Arm B is not promoted as the locked comparison.

### Arm C: surrogate-enabled integrated search

Use every scenario in the promoted freeze bank. Re-simulate five unique shortlisted
plans with MRST. Among those five, run offline DWSIM spot-checks for the minimum,
median, and maximum facility throughput.

### Field-scenario Monte Carlo and correlation bracketing (2026-07-17 amendment)

The field is 20 disjoint 900×600 m sector boxes; no single geomodel contains the
corridor, and a well↔realization assignment is a sampled field scenario, not site
knowledge. Selection and economics are therefore re-solved from the cached
rollouts:

- **Independent limit (main):** K = 20 seeded well↔realization assignments; pivot,
  break-even, and regret are reported as distributions across assignments.
- **Correlated limit (bracketing ablation):** one shared realization stamped at
  all 20 sectors, swept over the 20 realizations.

Both reuse the same 3,240 surrogate rollouts (rollouts depend only on
realization × schedule); the Monte Carlo costs MILP/economics solves only. No
single-assignment ranking of named wells is promoted as a paper claim.

The result is reported as observed. Assumptions must not be tuned to force a
carbon-price pivot, a viable pipeline network, positive NPV, or positive C-B value.

## Figure map

Each figure has one Matplotlib script under `paper/figures/` and reads the canonical
bundle wherever numerical or spatial data apply.

1. **Integrated framework:** four-module, two-pass workflow and typed quantities.
2. **Case-study atlas:** terrain, candidate wells, proxy geologies, schedule grid,
   and carbon-price basis.
3. **Surrogate credibility:** declared median case, MRST/surrogate/residual plume,
   production and rollout diagnostics, and validated-horizon boundary.
4. **Learned screening surface:** raw surrogate response, geology classes,
   per-cycle inset, and the Arm A marker.
5. **Infrastructure result:** selected Article 6/JCM network, continuous pressure
   audit, and throughput crossover.
6. **Facility evidence:** eight-case DWSIM parity and screening cost curves.
7. **Carbon-price response:** portfolio extent versus price with the
   field-scenario band and correlated-limit overlay, break-even distribution,
   and expected-regret matrix (no single-assignment bump chart).
8. **A/B/C result:** economics, coverage versus wall-clock, and top-five MRST
   confirmation.

Every caption identifies MRST truth, surrogate prediction, engineering correlation,
or proxy assumption. Figures 4, 5, 7, and 8 must exit as blocked when their real
inputs are absent.

## Backend contracts and read-only API

`ReservoirVisualization` represents the 64 x 64 x 1 grid, 900 x 600 x 6 m geometry,
structure, permeability, porosity, facies, barriers, fractures, well/completion
masks, baseline state, units, field limits, and provenance. `ScreenResult` retains
all existing fields and adds `detailed_reservoirs`, keyed to the same top-K scenario
IDs as `detailed_predictions`.

`PaperResultsIndex` and typed per-figure payloads are identified by `bundle_id`.
The API exposes:

- `GET /paper/results`;
- `GET /paper/results/{bundle_id}`; and
- `GET /paper/results/{bundle_id}/reservoirs/{case_id}`.

Incomplete bundles and missing fields return explicit status. They never load demo
data or another physical field as a substitute.

## Simulator-style reservoir renderer

The renderer reconstructs 65 x 65 node elevations from cell-centered `structure_m`
and draws bounded warped hexahedral geometry without per-cell React components. It
preserves the 900:600 footprint, approximately 14.06 x 9.38 m cells, and constant
6 m thickness.

- Default fill: log10 permeability in mD on a perceptually uniform scale.
- Alternatives: porosity and discrete facies.
- Reservoir vertical exaggeration: separate from terrain, default 8x, range 1-20x.
- Wells: simulator-style trajectories plus completion markers.
- Coordinates: a local proxy anchored to the selected well, not surveyed orientation
  or true subsea depth.

Independent layers are terrain; wells; labels; routes; boosters; structural grid and
edges; permeability fill; facies, barrier, and fracture overlays; dynamic response;
and legacy SECARB response columns.

Pressure displays delta-P from the final warm-start frame. Oil displays
`So,baseline - So,t`. Gas saturation and `z_CO2` use thresholded translucent
occupancy. Only one dynamic scalar is active, with opacity and plume-threshold
controls. Unavailable field selectors are disabled.

Paper validation views synchronize MRST, surrogate, and residual panes by camera,
timeline, probe, and physical limits. The frontend paper study displays the active
bundle ID, freeze basis, actual scenario count, and source class.

## Workspace behavior

The left, right, and bottom panels are accessible split panes:

- left: 248 px default, constrained to 180-420 px;
- right: 320 px default, constrained to 260-520 px; and
- bottom: 340 px default, constrained from 180 px to 70% of center height.

Handles support pointer capture, keyboard adjustment, double-click reset, and
collapse/restore with the last session-local size. There is no browser persistence
or docking framework.

## Validation and promotion

Promotion requires:

- manifest-hash verification for every MRST shard, preset, table, reservoir payload,
  figure, and frontend payload;
- Feature 005 mechanical PASS before a preset is used;
- typed contract/OpenAPI round trips, including unavailable-field behavior;
- renderer tests for dimensions, warping, thickness, property colors, blending,
  probes, shared comparison scales, and bounded draw calls;
- split-pane, figure-navigation, layer, opacity, timeline, and responsive UI tests;
  and
- full Python, figure-regeneration, frontend unit/type/build, and Playwright checks.

## Implementation record: 2026-07-17

- The deterministic builder, verifier, freeze guard, Arm B design, and replacement
  order are implemented.
- `working` verifies with no hash errors but is **partial and unfrozen**:
  `scenario_count=0`, mechanical status `BLOCKED`, scientific status `NOT_RUN`, and
  `fabricated_result=false`.
- Figures 1, 2, 3, and 6 are bundle-driven where data apply, rendered, and
  hash-registered. Figures 4, 5, 7, and 8 are explicitly blocked.
- The real Figure 3 median case, `case_0016`, is included with MRST truth, frozen
  surrogate output, residuals, static geology, and provenance. Its current linked
  dynamic comparison field is gas saturation.
- The Arm B design contains 40 primary rows across 20 geologies and a deterministic
  3,200-row replacement order. Accepted Arm A, B, and C result counts remain zero.
- The MRST preflight yielded zero safe workers under the locked RAM formula, so the
  three-run benchmark and both preset-bank exports were not launched.
- No `submitted` or `full_3240` bundle exists. No A/B/C paper number is promoted.

## Implementation record: 2026-07-18

- Arm C now has a deterministic 40-assignment correlation-bracket design: 20
  seeded bijective well-to-realization assignments for the independent limit and
  20 shared-realization sweeps for the correlated limit. The working bundle
  carries the 800-row well-level assignment table.
- The Feature 005 orchestrator exposes a cache-only downstream resolve path. It
  validates complete prediction-cache coverage, makes zero surrogate calls, and
  still executes route/network selection, facility sizing, and two-pass
  economics. The Feature 007 adapter runs it once per assignment and projects
  the declared carbon-price cells without recomputing rollouts.
- The working bundle declares `resolve_grouping=assignment_x_carbon_price`,
  `rollout_policy=reuse_the_same_3240_cached_rollouts`, and
  `named_well_single_assignment_claim=false`. Build and hash verification pass
  for present artifacts.
- These are orchestration and experiment-design results, not promoted Arm C
  numbers. The full 3,240-case cache and `arm_c_screening.json` remain missing,
  so Arm C is still scientifically `NOT_RUN` and the bundle remains blocked.
- A separate 20-well, one-common-schedule MRST workflow bank is permitted only
  as end-to-end UI evidence. It cannot satisfy the 200/3,240 paper bank gate or
  be used as an A/B/C result.

The feature is not done until a 200- or 3,240-scenario bundle is scientifically ready,
all eight figures are ready, the locked A/B/C confirmations exist, and an immutable
submission bundle passes verification.
