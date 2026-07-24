# Arm A/B/C Experiment Harness — Design

**Date:** 2026-07-24
**Status:** approved design, pending spec review → implementation plan
**Goal:** Produce the remaining APECX paper figure data — **Figures 4, 5(a/b), 7, 8 and Tables 3/4** — from the now-promoted 3,240-scenario seed bank, by building the experiment driver that runs the locked Arm A/B/C experiment and stages its outputs into the Feature 007 bundle.

## 1. Context & scope

The physics substrate is done: `jatibarang_full_v1` (20 geologies × 162 schedules = 3,240) and `jatibarang_demo_v1` (200) are promoted; `feature007 build` states `scenario_count=3240`, full preset `ready:True`. The reusable **components** exist — the screening orchestrator (`screening/orchestrator.py`, surrogate + mode-choice MILP + economics), the Arm C field-scenario re-solve engine (`paper/field_scenarios.py`: `build_field_scenario_design`, `run_field_scenario_resolves`, `summarize_field_scenario_distributions`, `CachedOrchestratorFieldScenarioResolver`), the economics module the orchestrator uses, and the figure scripts (`paper/figures/fig04/05/07/08`). The **designs** exist in the bundle (`arm_b_design` = 40 rows, `arm_b_replacement_order` = 3,200 rows, `field_scenario_assignments` = K=20). What is **missing** is the top-level driver that runs these into the paper outputs — `feature007.py` only *checks for* `arm_c_screening.json` and the figure CSVs; nothing produces them. `generate_hnp_dataset.m` has no full-simulation mode for Arm A/B (its modes are seed-only `feature005` or training-corpus generation).

This harness is the paper's results engine. It is **not** a science redesign: it wires existing, tested components and adds one MATLAB full-run mode, honoring the vault's locked experiment definition and claim guards.

**Out of scope:** retraining the surrogate; regenerating the seed bank; changing hydraulic assumptions (`min_velocity_m_s`, diameter catalog); Figures 1/2/3/5c/6/9 (already done); the paper text.

## 2. Global constraints (vault-verified — `04 APECX Paper Structure and Main Figures.md`)

- **Arm A** = the fixed central schedule (9,000 m³/day, 45-day injection, 30-day soak, 190-day production, 675 psi BHP, 3 cycles) applied to all 20 candidate geologies for economics, with the **median- and low-permeability representatives confirmed in MRST** (2 accepted runs).
- **Arm B** = exactly **40 accepted** MRST runs, two seeded normalized-maximin schedules per geology; permanent failures are replaced from the deterministic ranking (`arm_b_replacement_order`) until 40 accepted exist.
- **Arm C** = every scenario in the promoted freeze bank (3,240), re-solving selection+economics per field-scenario assignment **K=20 (independent limit)** and per **20 shared-realization sweeps (correlated limit)** across the 4 carbon prices, from the same cached rollouts — **MILP/economics only, no new surrogate or MRST compute**; then **5 unique shortlisted plans confirmed in MRST**; DWSIM checks the **min/median/max** throughput among those five.
- **Fair-comparison invariant:** all three arms use the **same economics module and objective**; only the *information source* differs (Arm A fixed strategy; Arm B 40 MRST-grade values; Arm C surrogate over all 3,240). Fig 8 headline = C−B and C−A in NPV$ with scenario spread, coverage-per-wall-clock, and the five-plan confirmation.
- **Claim guards:** scenario count and screening time come from the actual promoted run; **"2.38 weeks" is a labeled equivalence estimate** derived from manifest runtimes (scenarios_evaluated × mean full-MRST run time), never a measured figure. Fig 7 reports **distributions** (expected-NPV regret across field scenarios), never single-assignment claims. Cite the audit reason string (`below_minimum_hydraulic_flow` / `hydraulically_unreachable`), never "pipelines are uneconomic" alone. Report the pipeline/trucking crossover **across throughput**; never generalize the pilot low-throughput case. No tuning of hydraulic assumptions.
- **Provenance done-criterion:** every output row/table carries a `source_class` label — one of `surrogate_prediction`, `arm_c_integrated_result`, `mrst_and_surrogate_integrated_result`, `mrst_truth_and_surrogate_prediction`, `measured_runtime`, `dwsim_truth`, `screening_cost_proxy`.
- **Freeze discipline:** the immutable `submitted` bundle is created only by the freeze command after all figure/preset/A-B-C gates pass; this harness targets the reproducible `working` bundle.

## 3. Architecture

```
src/jatibarang_ccus/paper/experiment/
  __init__.py
  arm_c.py          # Phase 1: screen promoted preset + field-scenario re-solves  → Fig 4, 5a/b, 7 CSVs + arm_c_screening.json
  arm_ab.py         # Phase 2: drive full-MRST runs for Arm A/B/top-5, read accepted manifests
  dwsim_confirm.py  # Phase 3: DWSIM automation on the 5-plan min/median/max throughputs
  aggregate.py      # Phase 4: combine arms → Fig 8 CSVs + Tables 3/4
  run.py            # phased CLI orchestrator
  schemas.py        # typed row models + CSV writers with source_class stamping (shared)
boreyes2026/data/generate_hnp_dataset.m   # + new `feature007_full` mode (full MRST → accepted scenario_runs manifest, resumable)
```

Each unit has one responsibility, a typed interface, and is testable in isolation. Heavy/slow compute (MRST, DWSIM) is isolated behind resumable manifests; fast compute (surrogate screen, aggregation) re-runs cheaply. `schemas.py` centralizes the exact figure-CSV column contracts so every writer is validated against what `fig0X.py` reads.

**Phase dependency graph:** `arm_c` and `mrst` are independent; `dwsim` needs `arm_c` (the 5 plans); `aggregate` needs `arm_c` + `mrst` + `dwsim`; `stage` needs `aggregate`.

## 4. Phase 1 — Arm C (`arm_c.py`)

**Inputs:** promoted `jatibarang_full_v1` preset (`CompactPresetBank`), surrogate checkpoint (`models/checkpoints/model_b_hnp_prod_v2_boundary_replay_k3_polish_v1_fold0.pt`), economic assumptions (4 carbon prices), route library + road network for the MILP.

**Steps:**
1. Build the orchestrator (`build_default_orchestrator`) and screen all 3,240 scenarios once via `run_with_prediction_cache` (warm-start free-rollout from each launchpad). Rollouts + per-scenario economics (Δoil, Δgas, CO₂ inventory over the horizon) spill to a disk cache (reuse the orchestrator's detailed-field spill so RSS stays under the gate). This is the single ~1–2 hr surrogate pass; resuming skips a populated cache.
2. **`screening_surface.csv`** (Fig 4, `surrogate_prediction`): aggregate the cached per-scenario results across the operating grid — one row per (geology, injection_rate, cycles) with incremental oil and CO₂ retention, plus the geology permeability statistic used for coloring. Column names locked to `fig04_screening_surface.py`'s `load_table` reads (first plan task reads the script to pin exact names).
3. **Field-scenario re-solves** (Fig 7, `arm_c_integrated_result`): `build_field_scenario_design` (K=20 independent + 20 correlated, fixed seed) → `CachedOrchestratorFieldScenarioResolver` over the cache → `run_field_scenario_resolves` → `summarize_field_scenario_distributions`. Emit:
   - `carbon_price_rankings.csv` — `scenario_id, carbon_price_usd_per_tonne, rank` (portfolio extent per price across assignments).
   - `carbon_price_regret.csv` — `chosen_price_scenario, realized_price_scenario, regret_usd` (expected-NPV regret across field scenarios).
   - `npv_vs_carbon_price.csv` — `scenario_id, carbon_price_usd_per_tonne, npv_usd` (+ band columns per fig07 reads).
4. **Fig 5(a/b)** (`srtm_astar_and_arm_c_milp_result` / `coolprop_continuous_pressure_audit`): from the Arm C pilot MILP result → `pipeline_route_final.csv` (per-well supply mode, trucking legs over roads, rejection audit with the reason string, six-diameter evaluation); from a single standalone high-throughput trunk MILP (aggregated commercial demand, no bank) → `pipeline_pressure_final.csv` (continuous CoolProp pressure with `dense_phase_floor_bar`, `maop_bar`, booster lifts). These match the schemas the rewritten `fig05_pipeline.py` already reads.
5. **`arm_c_screening.json`** — the integrated screening result + provenance (checkpoint SHA, preset SHA, price axis, design SHA), the file `feature007.py`'s `arm_c_ready` gate checks.

**Output dir:** `paper/validation/feature007/` (staged in place; Phase 5 rebuilds the bundle).

## 5. Phase 2 — Full MRST (`feature007_full` MATLAB mode + `arm_ab.py`)

**New MATLAB mode `feature007_full`** in `generate_hnp_dataset.m` (mirrors `feature005`'s resumable sharded manifest, but runs the **complete** compositional simulation):
- Input: an arm design JSON (list of `{candidate_id, source_case_id, schedule values}`) + output dir.
- Runs the full HnP schedule (all cycles, full horizon — not the 8-frame seed), exports the complete production history economics needs (per-cycle Δoil, Δgas, cumulative CO₂ inventory, well rates) to a `.mat` per run.
- Writes an **accepted** manifest (`manifest.json`) with per-run `status` (`accepted`/`failed`), `runtime_seconds`, `output_sha256`, and convergence flags; resumable (skips existing hashed runs); a `feature007_replacement` option pulls the next design row on non-convergence until the accepted target is met.
- Reuses the existing compositional solver + PVT/config in the generator; no new physics.

**`arm_ab.py`** (Python driver):
- **Arm A** → run `feature007_full` on the 2 representative geologies (median- and low-permeability) under the fixed central schedule → `data/scenario_a_runs/manifest.json` (target 2 accepted).
- **Arm B** → run `feature007_full` on `arm_b_design` (40), feeding `arm_b_replacement_order` as fallback until 40 accepted → `data/scenario_b_runs/manifest.json`.
- **Top-5** → run `feature007_full` on Arm C's 5 shortlisted plans → `data/scenario_c_topk_runs/manifest.json` (target 5 accepted).
- Reads the `.mat` results back for the aggregator (full-horizon economics inputs). Measures and records one full run's wall time first (spec risk: full run ≈ 4× the seed's cycle count; batch time estimated before launch).

## 6. Phase 3 — DWSIM (`dwsim_confirm.py`)

- From Arm C's 5 plans, compute each plan's facility throughput (annual CO₂ → design mass flow); select min/median/max.
- Drive DWSIM automation on `docs/dwsim-validation/jatibarang_facility.dwxmz` — load flowsheet, set inlet mass flow/conditions for each of the 3 points, run, read compressor/pump/total power, cooling duty, separator capacity. Mechanism: pythonnet loading `DWSIM.Automation.dll` (FluentAPI), or the `DWSIM.Automation.DynamicRunner.exe` path — a **smoke test (load → run → read one value) precedes the batch** to lock the mechanism.
- Output rows stamped with `dwsim_version`, `model_sha256`, `property_package` (matching the Feature 003 `dwsim_reference.csv` format), `source_class=dwsim_truth`. Feeds `topk_confirmation.csv` / Table 4.

## 7. Phase 4 — Aggregate (`aggregate.py`)

All arms through the **same economics module** (fair-comparison invariant):
- **`abc_economics.csv`** (Fig 8a / Table 3): `arm, carbon_price_usd_per_tonne, npv_usd, npv_low_usd, npv_high_usd` (+ `irr`, `payback_years`, `breakeven_carbon_usd_per_tonne`, `breakeven_oil_usd_per_bbl`, `fiscal_case` for Table 3). Arm A = fixed schedule economics over 20 geologies; Arm B = selection+economics from the 40 MRST-grade well values (best of the two schedules per geology → 20 candidates → the same MILP selection); Arm C = the field-scenario distribution central estimate, band = the K-assignment spread.
- **`abc_runtime.csv`** (Fig 8b / Table 4): `arm, wall_clock_seconds, scenarios_evaluated` (Arm B=40, Arm C=3,240; wall-clocks summed from the manifests / surrogate-screen timing). Derived: `mrst_equivalence_weeks = scenarios_evaluated_C × mean_full_mrst_run_seconds / (7×86400)`, written as a labeled estimate column, `source_class=measured_runtime`.
- **`topk_confirmation.csv`** (Fig 8c, `mrst_truth_and_surrogate_prediction`): per plan — `plan_id, surrogate_objective_usd, mrst_objective_usd, relative_error`, plus the 3 DWSIM throughput rows joined by throughput class (min/median/max).
- **Tables 3/4** derive from `abc_economics` + `abc_runtime` (the table generators consume the same CSVs; no separate numbers).

## 8. Phase 5 — Stage + rebuild (`run.py --phase stage`)

Copy the produced CSVs/JSON into `paper/validation/feature007/`, run `python -m jatibarang_ccus.paper.feature007 build --bundle-id working`, and assert Figures 4/5/7/8 flip to `ready` and render (`fig04/05/07/08.py` exit 0). Verification-only; no science.

## 9. CLI, resume, error handling

- **CLI:** `python -m jatibarang_ccus.paper.experiment.run --phase {arm_c|mrst|dwsim|aggregate|stage|all}`; `all` order = arm_c → mrst → dwsim → aggregate → stage. Each phase is independently runnable and idempotent-on-resume.
- **Resume:** MRST full runs resume from the per-scenario manifest (hash-verified). Arm C screening reuses the disk cache. DWSIM overwrites its 3 points. Aggregation/stage are pure recomputation.
- **Errors:** a phase fails **loudly** if a required input is missing (no silent partials). Arm B non-convergence triggers deterministic replacement; Arm A/top-5 non-convergence is a hard error (must converge — flagged with the failing case + reason). MATLAB is driven headless via `matlab -batch`; MRST at `C:\Users\mauli\mrst-2025b\...`.

## 10. Testing

- **Unit (pure functions):** aggregation math (NPV/IRR/break-even per arm), screening-surface aggregation, runtime/equivalence computation, field-scenario summary (extend existing `field_scenarios` tests), and **CSV-schema conformance** — each writer's columns asserted against the exact names `fig04/05/07/08.py` read.
- **Integration smoke:** `arm_c` on a 2-geology subset end-to-end producing valid CSVs; one `feature007_full` MRST run (convergence + manifest shape); one DWSIM automation run (value read). These validate wiring without the full multi-hour compute.
- **Acceptance:** `feature007 build` clean + `fig04/05/07/08.py` render without missing-column/BLOCKED errors + `_preset_readiness`/`_accepted_manifest_status` all green (2/40/5).

## 11. Risks & feasibility notes

- **Full-MRST run time is unmeasured** — the seed was ~62 s for 8 frames (cycle 1); a full 3–4-cycle run is longer. Measure one before committing the 47-run batch; the batch is resumable if it spans sessions (launch detached, per the seed-bank lesson).
- **DWSIM automation mechanism** — FluentAPI vs DynamicRunner is settled by the pre-batch smoke test; if neither Python path works headlessly, fall back to the DynamicRunner CLI on a generated flowsheet.
- **Fig 4 / Fig 7-npv / Fig 8-confirmation exact column names** — pinned by reading each `fig0X.py` as the first task of its plan slice, so writers match on the first build.
- **The pivot result itself** (Fig 7) is the scientific unknown — the harness reports whatever the re-solves produce (pivot strong, weak, or absent); assumptions are never tuned to force a headline (per the guard and the pre-registered pivot-risk flag).
- **Same-economics wiring for Arm B** — Arm B must call the identical economics/objective path as Arm C with only its information set swapped; a divergence would invalidate the C−B claim. Covered by a unit test asserting identical economics on identical inputs.
