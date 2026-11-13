# Arm A/B/C Experiment Harness Implementation Plan

> **Execution boundary:** Implement and validate the standalone experiment
> harness and rebuild only the mutable Feature 007 `working` bundle. Do not
> change manuscript prose, retrain the surrogate, regenerate the promoted bank,
> copy the raw 177-case corpus, freeze `submitted`, commit, or push.

**Goal:** Run the locked Arm A/B/C comparison from `jatibarang_full_v1`, retain
resumable simulator evidence, and produce the canonical inputs for Figures 4,
5, 7, and 8 and Tables 3/4.

**Architecture:** A new
`src/jatibarang_ccus/paper/experiment/` package owns typed row contracts,
resumable phases, aggregation, and staging. The screening orchestrator remains
the only reservoir-to-pipeline-to-facility-to-economics execution path.
Surrogate predictions are stored in an identity-locked SQLite cache. MRST and
DWSIM remain offline confirmation tools whose outputs are adapted into, but do
not replace, the framework accounting path.

**Locked evidence counts:** Arm C `3,240` scenarios; `20` independent and `20`
correlated-limit assignments over four prices (`160` downstream resolves);
Arm A/B/top-five MRST accepted counts `2/40/5`; DWSIM confirmation count `3`.

## Global invariants

- Preserve the execution order reservoir → pipeline → facility → economics.
- Use the same framework economics evaluator and objective for all three arms.
- Use the four carbon-price scenarios and Article 6/JCM fiscal case already
  stored in the promoted preset. Verify their hashes at runtime; do not copy
  prices or preset hashes into source code.
- Keep physical candidate identity and location fixed during field-scenario
  assignments. Only the assigned seed/realization changes the surrogate input
  fingerprint.
- Never invoke the surrogate during a cached downstream resolve.
- Never turn `no_viable_network` into a selected development and never tune
  hydraulics, costs, or fiscal inputs to improve a result.
- A mechanical validation PASS is not the scientific promotion verdict.
- Write caches and intermediate files only below ignored
  `output/feature007-experiment/`. Stage compact validated CSV/JSON artifacts
  atomically.
- Raw MRST `.mat` outputs stay ignored under `data/scenario_*_runs/`; only
  manifests, provenance READMEs, and compact derived tables are reviewable.

## Output contracts

The staging phase publishes:

| File | Logical bundle table | Primary consumer |
|---|---|---|
| `screening_surface.csv` | `screening_surface` | Figure 4 |
| `pipeline_route.csv` | `pipeline_route_final` | Figure 5(a) |
| `pipeline_pressure_profile.csv` | `pipeline_pressure_final` | Figure 5(b) |
| `pipeline_cost_crossover.csv` | `pipeline_cost_crossover_final` | Figure 5(c) |
| `carbon_price_rankings.csv` | `carbon_price_rankings` | Figure 7(a) |
| `carbon_price_regret.csv` | `carbon_price_regret` | Figure 7(b) |
| `npv_vs_carbon_price.csv` | `npv_vs_carbon_price` | Figure 7(c) |
| `abc_economics.csv` | `abc_economics` | Figure 8(a), Table 3 |
| `abc_runtime.csv` | `abc_runtime` | Figure 8(b), Table 4 |
| `topk_confirmation.csv` | `topk_confirmation` | Figure 8(c), Table 4 |
| `arm_c_screening.json` | Arm C dependency record | bundle readiness |

Every CSV row has exactly one approved `source_class`:
`surrogate_prediction`, `arm_c_integrated_result`,
`mrst_and_surrogate_integrated_result`,
`mrst_truth_and_surrogate_prediction`, `measured_runtime`, `dwsim_truth`, or
`screening_cost_proxy`.

---

### Task 1: Lock the typed artifact contracts

**Files**

- Create: `src/jatibarang_ccus/paper/experiment/__init__.py`
- Create: `src/jatibarang_ccus/paper/experiment/schemas.py`
- Create: `tests/paper/test_experiment_schemas.py`

- [ ] Define Pydantic row models for Figure 4, Figure 5 route/pressure/crossover,
  Figure 7 ranking/NPV/regret, A/B/C economics/runtime, top-five confirmation,
  and DWSIM confirmation.
- [ ] Define MRST design, attempt, entry, and manifest models. An accepted entry
  requires solver convergence, finite arrays, the expected complete step count,
  the existing pressure/sanity gates, and a SHA-256-verified output.
- [ ] Reject `NaN`, infinities, unknown source classes, duplicate identities,
  invalid pressure envelopes, and malformed hashes.
- [ ] Add atomic CSV and JSON writers using a same-directory temporary file,
  `fsync`, and `os.replace`.
- [ ] Test required columns, optional blank metrics, finite-value rejection,
  source-class rejection, uniqueness rules, and atomic replacement.

**Validation**

```powershell
python -m pytest tests/paper/test_experiment_schemas.py -q
```

### Task 2: Add the resumable prediction cache

**Files**

- Create: `src/jatibarang_ccus/screening/prediction_cache.py`
- Modify: `src/jatibarang_ccus/screening/__init__.py`
- Modify: `src/jatibarang_ccus/screening/schemas.py`
- Modify: `src/jatibarang_ccus/screening/orchestrator.py`
- Create: `tests/screening/test_prediction_cache.py`
- Modify: `tests/screening/test_orchestration_integration.py`

- [ ] Implement a standard-library SQLite cache with WAL mode and zlib-compressed
  compact `PredictionResult` JSON payloads.
- [ ] Lock a cache to checkpoint SHA, preset ID, preset payload SHA, and preset
  design SHA. Reject a stale or mixed cache before inference.
- [ ] Key entries by the existing input fingerprint, store a payload SHA, and
  validate it on every read.
- [ ] Add `run_and_populate_prediction_cache`. Stream the compact bank in bounded
  chunks, infer only missing unique fingerprints, and commit each batch.
- [ ] Record predicted count, reused count, entry count, content hash, and stage
  timings.
- [ ] Add `run_preset_with_prediction_cache`, which fails on any cache miss and
  makes zero inference calls.
- [ ] Preserve the existing strict inline `run_with_prediction_cache` behavior.
- [ ] Add an exact-materialized cached entry point for Arm B's non-Cartesian
  two-schedules-per-geology design.
- [ ] Test interruption/resume, stale identity rejection, payload tampering,
  zero-call replay, and exact scenario preservation.

**Validation**

```powershell
python -m pytest tests/screening/test_prediction_cache.py `
  tests/screening/test_orchestration_integration.py -q
```

### Task 3: Add compact field-scenario assignment support

**Files**

- Modify: `src/jatibarang_ccus/screening/presets.py`
- Modify: `src/jatibarang_ccus/paper/field_scenarios.py`
- Modify: `tests/paper/test_field_scenarios.py`

- [ ] Extend compact-preset iteration with a candidate-to-realization mapping.
  Retain the candidate's physical ID/location and use the assigned
  realization's geology and seed when computing the input fingerprint.
- [ ] Let `CachedOrchestratorFieldScenarioResolver` resolve directly from the
  compact bank and global SQLite cache.
- [ ] Return selected scenario IDs, portfolio signature, NPV and uncertainty at
  all four realized prices, regret at all four realized prices, and downstream
  timing.
- [ ] Define policies as `chosen:<price_scenario_id>`.
- [ ] For chosen price `c` and realized price `r`, compute:

  `max(0, oracle selected at r valued at r − policy selected at c valued at r)`.

- [ ] Test independent bijections, correlated shared-realization assignments,
  deterministic seeds, cache-only replay, and exact regret arithmetic.

**Validation**

```powershell
python -m pytest tests/paper/test_field_scenarios.py `
  tests/screening/test_orchestration_integration.py -q
```

### Task 4: Implement Arm C and Figures 4/5/7 inputs

**Files**

- Create: `src/jatibarang_ccus/paper/experiment/arm_c.py`
- Modify: `paper/figures/fig07_carbon_price_pivot.py`
- Add unit/integration cases under: `tests/paper/`

- [ ] Open `jatibarang_full_v1`, verify its manifest payload/design hashes, load
  the frozen checkpoint, and populate/resume exactly 3,240 cache entries.
- [ ] Build `screening_surface.csv` as arithmetic aggregates over schedules with
  the same geology, injection rate, and cycle count. Retain sample count and
  p10/p90 spread columns.
- [ ] Run 20 independent and 20 correlated-limit assignments over four prices
  without inference. Require 80 records per limit and 160 total resolves.
- [ ] Emit independent mean plus p10/p90, and correlated-limit median, for NPV
  and regret. Render the independent band and correlated dashed overlay.
- [ ] Select five unique plans by maximum designated NPV. Record the price that
  produced each maximum; break ties by scenario ID.
- [ ] Select the median-NPV independent assignment at `$40/t` for the Article
  6/JCM representative network.
- [ ] Extract Figure 5 route rows and continuous hydraulic rows from actual
  routing/pipeline results. If the selected result is non-development, preserve
  its audit reason and leave Figure 5 blocked.
- [ ] Build the mandatory 500,000 t/y centroid hub and approximately 15.85 kg/s
  commercial reference trunk using the same route builder, pipe catalog, floor,
  MAOP, and hydraulic solver.
- [ ] Recompute the existing three-mode crossover on the actual representative
  full-route and commercial-trunk distances while retaining the locked 5 km
  hybrid last-mile screening basis.
- [ ] Write a compact `arm_c_screening.json` with counts, timings, shortlist,
  assignment summary, cache identity/content hash, checkpoint hash, preset
  hashes, and explicit no-tuning/no-fabrication provenance.

**Fast fixture**

```powershell
python -m pytest tests/paper/test_field_scenarios.py `
  tests/paper/test_experiment_schemas.py -q
```

**Production command**

```powershell
python -m jatibarang_ccus.paper.experiment.run arm-c
```

### Task 5: Admit MRST truth through the shared framework contracts

**Files**

- Modify: `src/jatibarang_ccus/surrogate/schemas.py`
- Modify: `src/jatibarang_ccus/contracts.py`
- Modify: `src/jatibarang_ccus/screening/adapters.py`
- Modify: `src/jatibarang_ccus/infrastructure/economic_adapters.py`
- Modify: `src/jatibarang_ccus/imports/mrst.py`
- Create: MRST adapter tests under `tests/paper/` and `tests/imports/`

- [ ] Admit `mrst` timeline/spatial origins and `mrst_truth` facility/economic
  provenance without weakening existing surrogate validation.
- [ ] Export/import complete schedule `dt_days` and stage labels.
- [ ] Implement `prediction_result_from_mrst` using the existing MRST importer,
  plume/timeline schemas, CoolProp conversion, and reservoir inventory
  functions.
- [ ] Preserve all accepted full-state/rate steps.
- [ ] Set MRST trajectory uncertainty to zero with an explicit provenance
  caveat. Do not invent an ensemble band.
- [ ] Stamp mixed outputs as `mrst_and_surrogate_integrated_result` or
  `mrst_truth_and_surrogate_prediction`.

### Task 6: Generate and verify resumable MRST designs

**Files**

- Create: `src/jatibarang_ccus/paper/experiment/arm_ab.py`
- Modify outside repo by explicit plan authority:
  `C:\Users\mauli\Documents\boreyes2026\data\generate_hnp_dataset.m`
- Preserve backup:
  `generate_hnp_dataset.m.pre-feature007-20260724.bak`
- Modify: `.gitignore`

- [ ] Back up the sibling MATLAB source before editing and record its before and
  after SHA-256 in every Feature 007 manifest.
- [ ] Add MATLAB `mode=feature007_full` with options for design path, output
  path, target accepted count, resume, and optional smoke slot limit.
- [ ] Run complete schedules and persist the manifest after every attempt.
- [ ] Accept only solver success, complete expected steps, finite arrays, and
  existing pressure/sanity gates. Do not apply training-morphology rejection to
  paper truth.
- [ ] Store ordinary non-convergence in `failed_runs`; reserve `failed_hashes`
  for corrupt or mismatched accepted artifacts.
- [ ] Generate Arm A slots for W09/case_0090 low permeability and
  W12/case_0109 nearest median using the fixed 9,000/45/30/190/675/3 schedule.
- [ ] Generate 40 Arm B slots from the existing seeded maximin design with
  deterministic same-geology replacement attempts.
- [ ] Generate five exact top-five slots with no replacements.
- [ ] Verify arm identity, design hash, exact accepted count, unique slot
  identity, scientific gates, output existence, and output hash.
- [ ] Ignore raw outputs under `data/scenario_a_runs/`,
  `data/scenario_b_runs/`, and `data/scenario_c_topk_runs/`, retaining their
  manifest/README files.

**Static validation**

```powershell
matlab -batch "checkcode('C:/Users/mauli/Documents/boreyes2026/data/generate_hnp_dataset.m')"
python -m jatibarang_ccus.paper.experiment.run prepare-mrst
```

**Smoke then production**

```powershell
python -m jatibarang_ccus.paper.experiment.run mrst-smoke
python -m jatibarang_ccus.paper.experiment.run mrst
python -m jatibarang_ccus.paper.experiment.run verify-mrst
```

Do not launch MRST when the locked RAM preflight selects zero safe workers.
That condition is a runtime blocker, not permission to reduce 2/40/5.

### Task 7: Run comparable Arm A and Arm B economics

**Files**

- Continue: `src/jatibarang_ccus/paper/experiment/arm_ab.py`
- Add comparison tests under: `tests/paper/`

- [ ] Arm A: evaluate the central schedule across all 20 compact surrogate
  geologies; treat the two accepted MRST runs as confirmation only.
- [ ] Arm B: for each price, choose the better of the two accepted MRST
  schedules per geology, then run the exact shared route, facility, MILP, and
  economics path.
- [ ] Ensure MRST predictions change the information source only; route,
  facility, fiscal, and objective assumptions remain shared.
- [ ] Store complete per-price results and timings in
  `output/feature007-experiment/arm_ab_results.json`.
- [ ] Test that identical prediction inputs produce identical economics across
  the Arm B and Arm C adapters.

**Command**

```powershell
python -m jatibarang_ccus.paper.experiment.run arm-ab
```

### Task 8: Generalize and run DWSIM confirmation

**Files**

- Modify: `tools/dwsim/FacilityValidationRunner/Program.cs`
- Create: `src/jatibarang_ccus/paper/experiment/dwsim_confirm.py`
- Create: `tests/paper/test_experiment_dwsim.py`

- [ ] Read optional top-level `expected_case_count`; default to eight so the
  Feature 003 case document remains unchanged.
- [ ] Continue loading a fresh flowsheet for every case.
- [ ] Rank the five plans by total facility inlet design mass flow and select
  minimum, third/median, and maximum with plan-ID tie-breaking.
- [ ] Generate cases from the locked Feature 003 fixed basis plus each plan's
  injection rate, delivery pressure, peak produced gas, and produced-CO2
  fraction.
- [ ] Build with a modern installed MSBuild; do not fall back to the .NET
  Framework compiler when it cannot compile C# 7.3.
- [ ] Run one-case smoke then all three cases.
- [ ] Require convergence, current model hash, CoolProp, recorded DWSIM version,
  and mass-balance residual ≤0.001.

**Validation**

```powershell
python -m pytest tests/paper/test_experiment_dwsim.py -q
python -m jatibarang_ccus.paper.experiment.run dwsim-confirm
```

### Task 9: Aggregate Figure 8 and Tables 3/4

**Files**

- Create: `src/jatibarang_ccus/paper/experiment/aggregate.py`
- Add aggregation tests under: `tests/paper/`

- [ ] Arm C NPV is the independent-assignment mean with p10/p90. Other finite
  economic metrics use their independent mean and report validity counts;
  undefined metrics remain blank.
- [ ] Arm A/B use integrated framework economics and their native uncertainty.
  MRST-only trajectory uncertainty remains zero.
- [ ] Runtime coverage is Arm A `2` accepted confirmations with
  `economics_scenarios=20`; Arm B `40` accepted with failed-attempt time
  separate; Arm C `3,240` surrogate scenarios with initial screen and
  downstream-resolve times separate.
- [ ] Compute `mrst_equivalence_weeks` from `3,240 × measured mean accepted full
  MRST runtime`. Label it an estimate; never force 2.38 weeks.
- [ ] Compare each top-five surrogate/MRST NPV at the same designated price,
  fiscal case, logistics, and allocation. Attach DWSIM only to the selected
  three throughput cases.
- [ ] Require exactly five unique top-five rows and three valid DWSIM joins.

**Command**

```powershell
python -m jatibarang_ccus.paper.experiment.run aggregate
```

### Task 10: Add the phased CLI and atomic stage

**Files**

- Create: `src/jatibarang_ccus/paper/experiment/run.py`
- Modify: `src/jatibarang_ccus/paper/feature007.py`
- Modify only after evidence exists:
  `paper/validation/feature007/README.md`
- Modify only after evidence exists:
  `paper/results/feature007/README.md`

- [ ] Expose `arm-c`, `prepare-mrst`, `mrst-smoke`, `mrst`, `verify-mrst`,
  `arm-ab`, `dwsim-confirm`, `aggregate`, `stage`, and `all`.
- [ ] Retain compatibility with
  `--phase {arm_c|mrst|dwsim|aggregate|stage|all}`.
- [ ] Before staging, require Arm C complete counts, aggregate complete status,
  exact 2/40/5 MRST manifests, five unique top-five confirmations, and three
  converged DWSIM rows.
- [ ] Copy all staged files through a temporary directory and atomically replace
  destinations only after every file validates.
- [ ] Harden Feature 007 to require exact accepted counts and hashes, full Arm C
  cache/assignment counts, approved row source classes, and DWSIM
  min/median/max evidence.
- [ ] Keep mechanical PASS distinct from scientific readiness.
- [ ] Rebuild and verify only `working`, then render Figures 4/5/7/8.
- [ ] If any scientific result is non-development, preserve it and keep the
  corresponding figure blocked with the exact reason.

**Command**

```powershell
python -m jatibarang_ccus.paper.experiment.run stage
```

### Task 11: Final validation and evidence reconciliation

- [ ] Preserve the paper baseline:

```powershell
python -m pytest tests/paper/test_feature007.py `
  tests/paper/test_field_scenarios.py -q
```

- [ ] Run targeted screening, paper, import, infrastructure, and facility tests.
- [ ] Run the full Python suite:

```powershell
python -m pytest -q
```

- [ ] Rebuild and verify:

```powershell
python -m jatibarang_ccus.paper.feature007 build --bundle-id working
python -m jatibarang_ccus.paper.feature007 verify --bundle-id working
```

- [ ] Render:

```powershell
python paper/figures/fig04_screening_surface.py --bundle paper/results/feature007/working
python paper/figures/fig05_pipeline.py --bundle paper/results/feature007/working
python paper/figures/fig07_carbon_price_pivot.py --bundle paper/results/feature007/working
python paper/figures/fig08_abc_comparison.py --bundle paper/results/feature007/working
```

- [ ] Reconcile only the Feature 007 validation/results READMEs from the files
  actually produced. Record simulator versions, hashes, exact accepted/failed
  counts, timings, mechanical verdict, and scientific verdict.
- [ ] Leave `submitted` untouched.

## Done condition

Implementation is complete when the code and fast tests pass and every
unavailable external run is reported as a concrete evidence blocker.
Scientific experiment completion additionally requires all four target figures
to report `ready`, exact 3,240/20+20/2+40+5/3 counts, verified hashes, approved
source classes, and a separately stated mechanical PASS and scientific verdict.
