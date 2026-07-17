# Abstract-State to Full-Paper Implementation Gap

## Purpose

This document defines the gap between:

1. the **current abstract-state implementation** in this repository; and
2. the **full APECX 2026 paper and demo implementation** described by the project
   constitution and Feature Specifications 001-007.

It is an implementation and evidence audit, not a claim that the current repository
already satisfies the full specification. Its main purpose is to prevent the current
Phase 1 outputs, proxy calculations, or submitted-abstract numbers from being reused as
final paper results without completing the missing coupling and validation work.

## Scope Baseline Used

The target state in this document is the intent described by:

- [Project Constitution](.specify/memory/constitution.md)
- [Feature 001: Subsurface Surrogate](specs/001-subsurface-surrogate/spec.md)
- [Feature 002: Pipeline Optimizer](specs/002-pipeline-optimizer/spec.md)
- [Feature 003: Facility Model](specs/003-facility-model/spec.md)
- [Feature 004: Economic Engine](specs/004-economic-engine/spec.md)
- [Feature 005: Screening API](specs/005-screening-api/spec.md)
- [Feature 006: Frontend](specs/006-frontend/spec.md)
- [Feature 007: Paper Figures and Case Study](specs/007-paper-figures/spec.md)

The current working-tree versions of the constitution, Feature 002, and Feature 005
contain uncommitted scope changes relative to Git `HEAD`. This audit treats the current
working-tree specifications as the intended full-paper target because they define the
MILP-coupled `Module 2 -> Module 1 -> Module 3 -> Module 4` workflow that matches the
paper concept. That target should be committed or otherwise frozen before further
implementation so the formal baseline is unambiguous.

## Status Vocabulary

| Status | Meaning |
|---|---|
| **Implemented** | Working code exists and is exercised by at least a focused test or saved artifact. |
| **Partial** | A useful implementation exists, but it does not satisfy the full feature contract. |
| **Proxy** | The code returns a value, but the value is generated from a screening assumption or analytic placeholder rather than the specified upstream module. |
| **Missing** | The specified behavior or deliverable does not exist. |
| **Validation outstanding** | Code exists, but the evidence needed for a paper-facing claim has not been produced. |

## Executive Verdict

The repository now contains completed standalone Features 001-004, a mechanically
implemented Feature 005 production orchestration path, the Feature 006 screening
workbench, a deterministic Feature 007 bundle pipeline, and the retained **Phase 1
development-only integration proxy**. It is not yet the promoted full-paper system.

The strongest reusable components are:

- the completed Feature 001 physical-input compiler, deterministic batched CPU runner,
  FastAPI endpoints, physical post-processing, regression fixtures, and saved
  validation/benchmark evidence around the frozen promoted checkpoint;
- typed Pydantic contracts across the major domain objects;
- real SRTM terrain loading and A* route generation;
- CoolProp real-gas property functions;
- a Pyomo/CBC network and well-selection MILP skeleton;
- validated screening-grade facility and annual economic engines;
- synchronous/SSE orchestration, cancellation, readiness, deterministic caching,
  interference/discrepancy audits, and selected-set trucking in Feature 005;
- the typed reservoir/paper-result API, simulator-style reservoir renderer,
  accessible split-pane workbench, and interactive paper-result study;
- the hash-verifiable Feature 007 working bundle and one-script-per-figure factory;
- pinned assumptions, terrain/checkpoint provenance, and an abstract-number ledger.

The production `/screen` path calls the real surrogate and no longer uses
[`_evaluate_candidate()`](src/jatibarang_ccus/phase1/case_study.py). That analytic path
is retained only for the historical abstract-number workflow. The decisive evidence
gap is now data and execution: the fixed 200/3,240 MRST-derived warm-seed payloads have
not been fully generated and imported, so no real preset result has been promoted.
The saved legacy 3,240-scenario result remains a proxy and is not silently relabeled.
The July 17 MRST preflight returned zero safe workers under the locked RAM-reserve
formula, so neither the three-run benchmark nor either bank export was launched.

## Current and Target Data Flows

### Retained legacy abstract-state flow

```text
20 assumption-defined candidate wells
        x
162 operating combinations
        |
        v
Analytic candidate-response formula
(oil factor, storage factor, retention formula)
        |
        v
Preliminary flat-cost NPV and best schedule per well
        |
        v
Top 12 candidates by preliminary value
        |
        v
SRTM A* route library + CoolProp hydraulic coefficients
        |
        v
Pyomo/CBC network and well-selection MILP
        |
        v
Per-selected-well facility calculation
        |
        v
Feature 004 annual DCF through the development-only compatibility adapter
        |
        v
paper/tables/abstract_numbers.*
```

### Full-paper target flow

```text
Pinned Jatibarang proxy geologies + candidate-well locations
        x
in-range operating schedule grid
        |
        v
Batched frozen-surrogate rollout
        |
        +--> pressure/gas/z_co2/oil frames
        +--> oil and gas production deltas and cumulative series
        +--> CO2 inventory, injected/produced-back mass balance
        +--> influence radii, confidence, and extrapolation flags
        |
        v
Pass 1 economics with flat delivered-cost assumption
        |
        v
Per-carbon-price A* + MILP network/well selection
        |
        v
Facility sizing for the selected portfolio
        |
        v
Pass 2 economics with raw pipeline/trucking and facility cash flows
        |
        +--> selection-discrepancy flag
        +--> interference report
        +--> top-K MRST/DWSIM validation shortlist
        |
        v
FastAPI result + reproducible A/B/C paper artifacts + live demo
```

## Feature-Level Gap Summary

| Feature | Current status | Current implementation | Full-paper gap |
|---|---|---|---|
| 001 Surrogate inference | **Implemented / scientific verdict conditional** | Frozen checkpoint, exact physical tensor compiler, scheduled deterministic batch rollout, production/inventory/plume post-processing, FastAPI endpoints, flags, provenance, and validation evidence | Consumed by Feature 005; real fixed-preset seeds and Feature 007 top-K confirmation remain outstanding. Extended horizons and inventory remain qualified outputs |
| 002 Pipeline optimizer | **Implemented standalone / screening-grade evidence PASS** | Projected exclusion-aware SRTM routing, deterministic free junctions, multi-source typed contracts, CoolProp/Darcy-Weisbach DCC PWL hydraulics, Pyomo/CBC network/booster design, continuous verification, flow-based allocation, and low/base/high pipeline-versus-trucking evidence | Consumed by Feature 005 with real typed demand/value adapters. Costs and public exclusions remain screening proxies, not FEED, vendor quotes, or field-survey data |
| 003 Facility model | **Implemented standalone / DWSIM evidence PASS** | Typed dedicated-skid portfolio contract, standard-volume conversion, recycle-only compression, final dense-phase cooling, mixed-stream pump duty, separator/dehydration/intercooler sizing, low/base/high costs, mass loss ledger, exact allocation, and eight-case DWSIM evidence | Feature 005 now invokes it only for selected wells using surrogate production loads and explicit CO2 composition; real preset/top-K execution remains pending |
| 004 Economic engine | **Implemented standalone / screening-grade evidence PASS** | Typed annual portfolio DCF, raw supply ownership, dual storage reconciliation, oil/gas/carbon revenue, pre-tax plus cost-recovery/gross-split sensitivities, deterministic uncertainty, rankings, IRR/payback/break-even metrics, schema, benchmark, and hashed evidence | Feature 005 consumes real prediction profiles in code and synthetic integration tests. Fiscal cases remain parametric sensitivities, and final A/B/C economics remain Feature 007 work |
| 005 Screening API | **Implemented mechanically / real-preset promotion blocked** | `/screen`, SSE, cancellation, presets/health, 4,096/256 limits, exact seed coverage, real 001-004 adapters, per-price MILPs, selected-well facilities, final/trucking economics, discrepancy/interference, shortlist, provenance, and focused contract/integration coverage | Fixed upstream MRST demo/full payloads are not yet complete; the hash-verified promotion bundle records `BLOCKED` without fabricated results. Feature 007 still owns scientific/paper promotion |
| 006 Frontend | **Implemented / paper-result data remains partial** | Vite/React workbench, generated API types, screening workflow, shared selection, offline real-case result, physical reservoir renderer, layer manager, accessible split panes, and APECX Paper Results study | Final scientific views remain limited by unavailable Feature 007 fields and the unfrozen bundle; presentation-machine rehearsal remains pending |
| 007 Paper case study | **Deterministic partial working bundle / scientific NOT RUN** | Bundle builder/verifier/freeze guard, exact Arm B design, read-only API, real `case_0016` comparison payload, and Figures 1, 2, 3, and 6 rendered and hash-registered | Scenario count is zero; Figures 4, 5, 7, and 8, all A/B/C result manifests, the promoted bank, top-K confirmation, and immutable submitted bundle remain outstanding |

## Detailed Gap: Feature 001 - Subsurface Surrogate

### What is implemented

- The promoted `production_v2`, `Tin = 8` checkpoint path and expected SHA-256 are
  pinned in [`surrogate/config.py`](src/jatibarang_ccus/surrogate/config.py).
- [`verify_checkpoint()`](src/jatibarang_ccus/surrogate/runner.py) rejects a missing or
  substituted checkpoint.
- [`HNPSurrogateModel`](src/jatibarang_ccus/surrogate/model_hnp.py) contains the static
  encoder, two-resolution ConvLSTM backbone, CBAM bottleneck, decoder, oil head,
  production-delta MLP, stage experts, and soak-to-produce gas correction used by the
  promoted checkpoint.
- [`preprocessing.py`](src/jatibarang_ccus/surrogate/preprocessing.py) converts typed
  physical inputs into the exact checkpoint tensors. It applies `log10(mD)` before
  checkpoint normalization, preserves all 20 stored dynamic channels, advances the
  4/2/6 inject-soak-produce schedule with midpoint progress, and emits trained-range
  records for every controlled quantity.
- The public request contract requires a pre-operation state and exactly eight
  physical history frames. It rejects schedule-fingerprint mismatches and does not
  invent an unvalidated cold start.
- [`SurrogateRunner`](src/jatibarang_ccus/surrogate/runner.py) performs deterministic
  scheduled CPU rollout in horizon-grouped microbatches. It replaces only pressure,
  gas saturation, and `z_co2` autoregressive channels while retaining scheduled future
  controls. Oil saturation remains an output only.
- Production deltas are converted from the checkpoint normalization to surface m3 per
  frame and accumulated into monotonic seed-plus-forecast totals.
- [`postprocessing.py`](src/jatibarang_ccus/surrogate/postprocessing.py) calculates the
  qualified CoolProp density-based reservoir inventory, injected and inventory-derived
  produced-back CO2, reconciliation residual, plume areas, gas-support area, and
  influence radius.
- [`api/app.py`](src/jatibarang_ccus/api/app.py) loads and hash-verifies the checkpoint
  once in the FastAPI lifespan and implements `GET /model/info`, `POST /predict`, and
  `POST /predict/batch`. Batch responses are compact unless full fields are requested
  for up to ten named scenarios.
- Three compact physical fixtures reproduce upstream input tensors within `1e-6`; the
  scheduled case-0016 24-step rollout reproduces the saved upstream output exactly.
- Five curated MRST cases (`0016`, `0115`, `0176`, `0197`, and `0209`) were evaluated
  at one-step, T+5, T+10, T+11, and their complete 3/4-cycle horizons.
- The complete repository suite contains 41 passing tests, including API lifecycle,
  validation error, compact 200-scenario request, provenance, deterministic batch,
  mass reconciliation, and saved/generated OpenAPI contract checks.

### Validation and promotion evidence

- Mechanical verdict: **PASS**.
- Scientific verdict: **CONDITIONAL**.
- Warm one-step p95: `0.0737 s` against the `<1 s` gate.
- 24-step single-rollout p95: `1.7610 s` against the `<3 s` gate.
- Compact `200 x 24` batch: `281.12 s` against the `<8 min` gate, with
  `806,875,136` bytes peak RSS against the `<4 GB` gate.
- Mean complete-horizon cumulative errors over the five local cases are `1.07%` for
  oil and `0.98%` for gas. Mean final inventory-approximation error is `6.48%`, with
  substantial case variation (`0.32%` to `14.95%`).
- Evidence is tracked in [`paper/validation/`](paper/validation/), while the compact
  upstream 36-case accuracy metadata is tracked in
  [`models/metadata/production_v2_accuracy.json`](models/metadata/production_v2_accuracy.json).

### Remaining dependency outside Feature 001

Feature 001 has no remaining implementation task in its approved standalone scope.
The full-paper workflow still needs Feature 005 to:

1. construct or register defensible eight-frame warm seeds for each screened geology;
2. replace `_evaluate_candidate()` with batched calls to the Feature 001 runner;
3. propagate production, inventory, plume, extrapolation, confidence, and provenance
   into Modules 1, 3, and 4; and
4. retain the scientific qualifications: the local validation set contains five
   curated cases, inventory is not a direct produced-CO2 prediction, and steps beyond
   the upstream 24-step validation horizon are explicitly low confidence.

## Detailed Gap: Feature 002 - Pipeline and Logistics

### What is implemented

- [`build_route_library()`](src/jatibarang_ccus/infrastructure/routing.py) rejects
  out-of-raster endpoints, performs distance/slope/buffer/intersection work in a local
  metric CRS, applies hard and penalty exclusions, and caches results by pinned input
  hashes.
- The complete Subang/20-well library contains 63 source/nearest-neighbour raw paths,
  54 deterministic free or hydraulic junctions, and 108 reusable candidate segments.
  Hard-zone crossings are absent and penalty crossings are audited.
- [`contracts.py`](src/jatibarang_ccus/contracts.py) separates annual tonnes, peak
  kg/s, source annual capacity, peak deliverability, pressure, temperature, purity,
  value, objective mode, solver evidence, raw costs, and display-only levelized costs.
- [`hydraulics.py`](src/jatibarang_ccus/infrastructure/hydraulics.py) builds signed
  local-state curves at zero/minimum-velocity/25/50/75/100% flow, including
  diameter MAOP and conservative inlet-pressure envelopes.
- [`solve_pipeline_design()`](src/jatibarang_ccus/infrastructure/pipeline.py) models
  selection, direction, diameter, annual and peak flows, pressure, discrete booster
  lift, power, source allocation, connectivity, velocity, MAOP, and mass balance.
  The general selectable network uses CBC-compatible DCC PWL constraints; the exact
  single-source mandatory-corridor presolve evaluates the same PWL at known flow.
- Solver solutions are loaded only for an optimal result or an accepted incumbent
  within the 2% gap. The result retains status, termination, bound, gap, and runtime.
- Every selected route is reintegrated at no more than 100 m steps with local CoolProp
  properties. Pressure, hydraulic head, velocity, MAOP, connectivity, boosters, and
  annual/peak mass balance are audited, with at most two constrained refinements.
- [`costs.py`](src/jatibarang_ccus/infrastructure/costs.py) and
  [`supply.py`](src/jatibarang_ccus/infrastructure/supply.py) separate raw CAPEX/OPEX,
  commodity cost, lifecycle PV, levelized display metrics, per-well shared-flow
  allocation, and a componentized trucking baseline.
- A temporary Phase 1 adapter preserves old proxy callers without changing Feature
  001 APIs. It annualizes campaign tonnes over project life and retains peak flow as a
  separate sizing quantity. Feature 005 now owns and implements the real production
  integration path.

### Validation evidence and verdict

- Mechanical Feature 002 tests: **PASS**.
- Artifact manifest verdict: **PASS**, with 20 candidates and no candidate
  prefiltering.
- Default proxy/net-value case: audited `no_viable_network`; this is the intended
  rational zero-selection result, not a physical infeasibility.
- Mandatory W01 minimum-cost validation case: `accepted`, 6 active segments, 2 sized
  boosters, optimal CBC solve in `1.044 s` cumulative solver time, and zero reported gap.
- Peak and annual mass-balance relative residuals are below `1e-9` against the `1e-6`
  gate. The worst continuous/PWL difference is `1.223 bar`, within its 5% tolerance.
- Low/base/high delivered costs are monotonic. For this deliberately low-throughput
  fixture, base pipeline cost is `3,475.15 USD/t` and trucking is `21.95 USD/t`, so
  trucking is cheaper in every tracked case. This is not a general crossover claim.
- Multi-source capacity behavior is proven with a deterministic synthetic fixture;
  no unsupported second Indonesian source is claimed.
- The complete hashed bundle is under
  [`paper/validation/feature002/`](paper/validation/feature002/).

### Remaining limitations outside Feature 002

1. Feature 005 now supplies real surrogate annual demand, peak deliverability, and
   pre-logistics value in code; the real demo/full preset evidence is still pending.
2. The pure-CO2 approximation is limited to streams with at least 95% purity; a full
   composition model is still required for lower-purity sources.
3. NETL/IEAGHG-derived costs are screening correlations, not Indonesian bids or FEED.
4. OSM/BIG-cross-checked exclusions are public screening proxies, not field surveys,
   permitting decisions, or constructability confirmation.
5. The tracked mandatory fixture validates mechanics and accounting, not final paper
   economics or an optimized deployment recommendation.

## Detailed Gap: Feature 003 - Surface Facility Model

### What is implemented

- `FacilityPortfolioRequest` accepts 1-8 unique selected wells and returns exact
  per-equipment, per-well, and portfolio allocations for dedicated well-pad skids.
- Standard-volume rates carry explicit reference conditions and are consistency
  checked against CoolProp mass flow. Dense delivery density is not used to convert
  standard volume.
- Only recovered produced CO2 is compressed. A final 27 C cooler preserves a dense
  pump-suction state, and the combined fresh/recycle stream crosses the remaining
  wellhead pressure rise once.
- Separator, dehydration, intercooler, rotating-equipment redundancy, CAPEX, annual
  energy/maintenance OPEX, and provenance are auditable equipment items.
- The loss ledger separates conditioning purge, recycle non-recovery, fugitives,
  atmospheric emissions, net-storage debit, and bulk produced-back CO2. Feature 004
  consumes the absolute fresh-stream debit and does not deduct produced-back CO2
  twice.
- The Phase 1 compatibility caller evaluates the selected portfolio once and passes
  each unique well allocation into economics.
- The tracked DWSIM 10.0.9650 flowsheet converged for all eight pinned cases. Saved
  compressor/pump/total-power MAPE is `0.0000165%`, `0.0000000074%`, and
  `0.0000147%`; maximum power error is `0.0000198%`; DWSIM mass-balance residual is
  zero.
- The evidence bundle contains the DWSIM source model, PFD, comparison and balance
  tables, cost sweep, plots, error summary, and verified SHA-256 manifest.

### Remaining integration and evidence limits

1. **Real preset evidence is still absent.** Feature 005 now supplies real typed
   surrogate loads in the production code path and synthetic integration tests, but
   the fixed MRST-derived demo/full banks have not completed their offline build.
2. **Costs remain screening correlations.** Low/base/high coefficients are
   literature-aligned project assumptions, not DWSIM native CAPEX, Indonesian vendor
   bids, or FEED.
3. **Liquid and water loads remain assumptions.** DWSIM validates the pure-CO2 gas
   path; it does not validate predictive oil/water separation or dehydration
   performance.
4. **The topology is fixed to dedicated skids.** A central facility or gathering
   system would require a new ownership and optimization feature.
5. **Validation is envelope-bounded.** Out-of-range delivery pressure, throughput,
   produced-gas rate, or composition is explicitly flagged and cannot inherit the
   saved error statement.

### Full-paper completion evidence

- [x] Auditable fixed flowsheet and dedicated-skid ownership basis.
- [x] Eight converged DWSIM operating points spanning the screening range.
- [x] CoolProp-versus-DWSIM error tables, balance table, plots, and hashes.
- [x] Versioned design and low/base/high cost files with units and source classes.
- [x] Monotonic power, CAPEX, OPEX, separator, and loss evidence.
- [x] Exact equipment-to-well-to-portfolio allocation without facility double charge.
- [x] Feature 005 code and integration fixtures consume real prediction contracts and
      preserve selected-well allocations.
- [ ] The real demo preset preserves those allocations in saved promotion evidence.

## Detailed Gap: Feature 004 - Economic Engine

### What is implemented

- [`evaluate_economic_batch()`](src/jatibarang_ccus/infrastructure/economics.py)
  evaluates typed portfolio x carbon-price x fiscal batches using year-0 CAPEX and
  end-year recurring cash flows. Physical activity stops when the supplied profile
  stops; no HnP campaign or production tail is repeated implicitly.
- Discriminated `flat_delivered`, `pipeline_raw`, and `trucking_raw` contracts reject
  mixed raw/levelized ownership. Pipeline CAPEX, booster CAPEX, annual maintenance,
  energy, commodity supply, and facility CAPEX/OPEX enter exactly once.
- Oil uses the fixed SI-to-bbl conversion. Hydrocarbon-gas revenue excludes produced
  CO2 and uses the versioned `0.0353 MMBtu/std m3` heating-value assumption.
- Primary storage is injection minus inventory-derived produced-back CO2 minus Feature
  003 surface loss. A standard-state CoolProp density supports the production-stream
  cross-check, and divergence, missing inventory, negative storage, or extended
  horizon confidence produces explicit flags.
- Pre-tax, simplified cost-recovery with ceiling/carryforward, and simplified
  gross-split modes are implemented. Carbon-revenue treatment and the switchable tax
  on explicitly supplied atmospheric emissions are separate parameters.
- NPV, unique bracketed IRR, fractional discounted payback, break-even carbon/oil
  solves, deterministic correlated low/base/high trajectories, and ranking stability
  are returned with explicit statuses.
- [`economic_adapters.py`](src/jatibarang_ccus/infrastructure/economic_adapters.py)
  annualizes Feature 001 intervals, consumes raw Feature 002 results, allocates Feature
  003 energy/maintenance/losses, and keeps the analytic Phase 1 caller runnable with a
  development-only qualification.
- The versioned basis, JSON Schema, 26 focused tests, validation CLI, and SHA-256
  evidence manifest are tracked. The 36-case reference batch reconciles to
  `1.1642e-10 USD`; the warmed 200 x 4 x 3 benchmark covers three active campaign
  years with distinct cash-flow vectors and records `0.8357 s` p95.

### What remains outside Feature 004

1. **Feature 005 real-preset promotion.** The production integration now annualizes
   Feature 001 predictions and sends final selected portfolios through Feature 004.
   The legacy compatibility caller remains labeled development-only, while the absent
   real demo payload prevents a saved promoted integration result.
2. **Exact statutory fiscal accounting.** The two post-fiscal modes intentionally
   remain parametric screening sensitivities rather than contract, tax-return,
   depreciation, financing, reserves, or exact PSC replicas.
3. **Final-paper economics.** The saved reference fixtures validate mechanics and
   ranking behavior. They are not the A/B/C experiment, a Jatibarang field forecast,
   or a replacement for top-K MRST/DWSIM confirmation.

### Full-paper completion evidence

- [x] Annual cash-flow tables and independent reconciliation tests.
- [x] Correct discounted CAPEX, recurring OPEX, revenues, taxes, and terminal terms.
- [x] One-and-only-one ownership allocation for pipeline and facility costs.
- [x] IRR, payback, break-even carbon, and break-even oil verification cases.
- [x] Four carbon-price cases with dated sources and labeled sensitivities.
- [x] Pre-tax and parametric post-fiscal cases.
- [x] Produced-back CO2 cross-check and low-confidence threshold.
- [x] Ranking-stability and uncertainty report across carbon prices.
- [x] Feature 005 consumes real surrogate profiles in its production code and
      integration fixtures.
- [ ] The real demo preset saves a final integration reconciliation bundle.
- [ ] Feature 007 executes the A/B/C study and promotes paper-facing economics.

## Detailed Gap: Feature 005 - Screening API and Orchestration

### What is implemented

- [`create_app()`](src/jatibarang_ccus/api/app.py) retains the Feature 001 routes and
  adds `/screen`, `/screen/stream`, cooperative cancellation, `/presets`, and `/health`.
- [`screening/orchestrator.py`](src/jatibarang_ccus/screening/orchestrator.py) is the
  single event-producing implementation used by both synchronous and SSE responses.
- Preset and inline schemas enforce exact schedule-fingerprint seed coverage, explicit
  produced-gas CO2 composition provenance, a 4,096 logical-scenario cap, and 256-item
  Feature 001/004 chunks.
- Request-local fingerprint caching deduplicates identical geology/seed/schedule
  inputs while retaining raw predictions for at most ten detailed responses.
- Preliminary Feature 004 economics use pinned flat supply and zero facility cost;
  the discounted supply component is added back before per-price Feature 002 selection.
- Feature 002 builds the route library once and runs a real `max_net_value` MILP per
  carbon price with no forced minimum-well fallback.
- Feature 003 is called once per accepted non-empty selected portfolio and receives
  predicted production increments, pipeline delivery pressure, and explicit gas
  composition. Unselected wells never receive facilities.
- Final Feature 004 portfolios use raw allocated pipeline components, dedicated
  facility costs/losses, inventory profiles, and surrogate uncertainty across every
  requested carbon price and fiscal case.
- Trucking is priced for the same selected set; it never becomes a second selector.
- Each accepted plan receives one non-convergent selected-set discrepancy audit,
  geodesic influence-radius interference checks, propagated flags, cross-price
  entry/exit comparison, deterministic shortlist, timings, and a provenance catalog.
- Focused and repository regression suites pass, including synthetic pivot, partial
  failure, deduplication, SSE, cancellation, ownership, and API parity.
- The normalized-maximin preset design/import tooling and upstream fixed-seed MRST
  exporter are implemented. A bounded one-seed exporter smoke is recorded separately
  from real preset promotion.

### What remains incomplete

1. **Derived preset payloads are not ready.** The deterministic demo/full designs exist,
   but all fixed MRST runs and the hashed NPZ imports have not completed. `/presets`
   therefore reports both banks as unavailable.
2. **Real promotion run is blocked.** The validation CLI writes a hash-verified
   dependency/schema report and records `BLOCKED` rather than substituting legacy or
   synthetic data. No real module-reconciliation, interference, trucking, or
   performance table can be claimed until the demo payload exists.
3. **Scientific promotion remains outside Feature 005.** A mechanically accepted demo
   does not establish the A/B/C comparison, top-K MRST/DWSIM confirmation, or final
   paper values. Feature 007 owns those decisions.
4. **The frontend is no longer the blocker.** Feature 006 consumes the screening and
   paper-result contracts. Its paper views remain qualified by the same missing
   scientific artifacts as the backend.

### Mechanical evidence status

- [x] Feature 005 OpenAPI schema and orchestration endpoint integration tests.
- [x] Integration fixtures proving prediction-demand adaptation, ownership, caching,
      pivot behavior, partial failures, and pass-1/pass-2 audit structure.
- [x] Interference, extrapolation/confidence, provenance, shortlist, cancellation, and
      streaming sequence tests.
- [x] Deterministic upstream design and derived-only importer/exporter workflow.
- [x] Hash-verified blocked-evidence bundle that does not fabricate a preset result.
- [ ] Complete/import `jatibarang_demo_v1` and save the real request/result, SSE,
      reconciliation, discrepancy, interference, trucking, performance, and hashes.
- [ ] Materialize and readiness-check `jatibarang_full_v1`; its long paper execution
      remains Feature 007 work.

## Detailed Gap: Feature 006 - Live Demo Frontend

Feature 006 is implemented as a Vite/React/TypeScript workbench and remains a pure
consumer of typed backend results. It includes the composer, preflight and SSE run
flow, ranking/economics/production/compare views, status and confidence chrome,
offline real-case result, 2D fallback, and client-side carbon-price pivot.

The spatial workspace now renders the physical 64 x 64 x 1, 900 x 600 x 6 m local
reservoir proxy rather than only a floating SECARB response board. Static
permeability, porosity, facies, barriers, fractures, wells/completions, dynamic
response, terrain, transport, and legacy SECARB columns are independently layered.
Unavailable fields are disabled and never relabeled or replaced by demo data. Left,
right, and bottom regions use constrained pointer/keyboard split panes.

The APECX Paper Results study consumes the immutable-bundle API and keeps bundle ID,
freeze basis, scenario count, source class, and pending/blocked states visible. The
remaining frontend gap is evidence availability, not missing UI architecture: no
interactive panel may present the absent Figures 4, 5, 7, or 8 data as real.

## Detailed Gap: Feature 007 - Full Paper Evidence Package

### What is implemented

- `paper/tables/abstract_numbers.csv`, `.json`, and `.md` provide a structured
  post-submission Phase 1 ledger.
- Surrogate metrics and the 177 accepted-case count are read from pinned artifacts.
- `paper/validation/feature001_validation.csv` and `.json` contain the reproducible
  five-case, five-horizon local evaluation; `feature001_benchmark.json` records
  hardware, software, configuration, latency, throughput, memory, and checkpoint hash.
- The terrain hash, checkpoint hash, assumption file, and saved screening summary
  improve reproducibility.
- Five full MRST validation files are available locally and have been used for the
  Feature 001 metric bundle.
- `src/jatibarang_ccus/paper/feature007.py` builds, verifies, and guards the freeze of
  deterministic result bundles without fabricating missing evidence.
- `paper/results/feature007/working/` verifies with no hash errors. It is explicitly
  partial and unfrozen: scenario count zero, mechanical `BLOCKED`, scientific
  `NOT_RUN`, and no fabricated result.
- Figures 1, 2, 3, and 6 are bundle-driven where data apply, rendered, and
  hash-registered. Figure 3 uses the declared median validation case `case_0016` with
  real MRST truth, frozen-surrogate output, residuals, and spatial provenance.
- Figure scripts 4, 5, 7, and 8 exist and stop with explicit blockers when their real
  inputs are absent.
- The exact 40-row Arm B primary design and 3,200-row deterministic same-geology
  replacement order are recorded in the working bundle. These are designs, not
  accepted MRST results.

### What remains missing

1. **The preset banks are absent.** Neither ready manifest/payload exists; the
   Feature 007 working bundle therefore reports `scenario_count=0`.
2. **The MRST export has not started.** RAM preflight yielded zero safe workers, so
   the required three-run benchmark and resumable 200/3,240 exports were not launched.
3. **No locked A/B/C results exist.** Arm A confirmations, 40 accepted Arm B runs,
   the Arm C screen, five Arm C MRST confirmations, and three DWSIM throughput checks
   have no accepted-result manifests.
4. **Figures 4, 5, 7, and 8 remain blocked.** There is no real learned screening
   surface, final Arm C network/crossover, carbon-price ranking/regret result, or A/B/C
   economics/coverage/confirmation result.
5. **No uncertainty-aware final economics table exists.** Module 004 reference tables
   remain mechanics evidence, not A/B/C paper values.
6. **No immutable paper bundle exists.** Neither `submitted` nor `full_3240` has been
   created; the partial working bundle cannot pass the freeze guard.

## Submitted Abstract Claims Versus Current Evidence

The submitted PDF and the current Phase 1 ledger are different result states. They
must not be merged silently.

| Claim class | Submitted abstract | Current repository evidence | Paper use now |
|---|---:|---|---|
| Accepted MRST proxy cases | 177 | Traceable to upstream manifest and promoted split | Usable if described as the complete proxy dataset, not 177 training-only cases |
| Porosity span | 0.17-0.22 | Traceable to accepted proxy cases | Usable as a proxy-dataset range |
| Matrix permeability | 10-114 mD | Case-study/literature assumption | Usable only as an input anchor, not a measured 177-case outcome |
| One-step pressure R2 | 0.9999 | Traceable to promoted metrics | Usable with explicit one-step scope |
| Gas plume IoU | 0.9756 | Traceable to promoted one-step metrics | Usable with explicit one-step scope |
| Cumulative production error | below 1.84% | Traceable specifically to cumulative raw-oil error | Must be labeled cumulative oil error and tied to its rollout definition |
| End-sequence CO2 mass error | 3.35% | Traceable to promoted rollout metrics | Usable with horizon and method stated |
| Scenarios | 3,240 | Arithmetic from 20 proxy wells x 162 schedules | Not evidence of 3,240 surrogate rollouts |
| Equivalent MRST time | 2.38 weeks | Extrapolated from mean manifest runtime | Must be labeled an equivalence estimate, not elapsed MRST execution |
| Screening runtime | 204 seconds | No current source artifact | Treat as unverified submission-time value |
| Current-price NPV | $20,705 | No current source artifact; later proxy run is about -$8.30 million | Do not use either as final paper NPV |
| JCM NPV | $2.03 million | No current source artifact; later proxy run is about -$2.62 million | Do not use either as final paper NPV |
| Priority changes | 20 of 20 | No current source artifact; later proxy ranking reports 18 of 20 | Recompute after full coupling |
| Break-even carbon price | $1.09/tCO2 | No current source artifact; later proxy run reports $54.52/tCO2 | Recompute after accounting corrections and full coupling |

The current `paper/tables/abstract_numbers.*` artifacts are useful provenance examples,
but their integrated-economic values are **development diagnostics**, not final-paper
results.

## Cross-Cutting Accounting and Scientific Risks

The unresolved items below still block paper-facing economics. Closed mechanical
controls must remain distinct from the pending real-preset and scientific verdicts:

1. **Real-preset execution:** the production path uses the surrogate, but no promoted
   200/3,240 result exists. The analytic Phase 1 result remains provenance-only.
2. **Network ownership control (closed standalone):** Feature 004 raw supply contracts
   exclude levelized display costs and book raw pipeline ownership once.
3. **Facility ownership control (closed standalone):** Feature 003 now owns one
   dedicated skid per selected well and reconciles the portfolio exactly once.
4. **Compression/pump pressure control (closed standalone):** only recovered produced
   CO2 is compressed; the combined dense stream crosses the wellhead pump rise once.
5. **Annual DCF control (closed standalone):** Feature 004 books year-0 and end-year
   cash flows, metrics, fiscal sensitivities, and uncertainty with saved reconciliation.
6. **Storage accounting integration (closed mechanically):** Features 001, 004, and
   005 carry inventory, stream cross-check, surface loss, confidence, and storage
   contracts; real-preset reconciliation evidence remains pending.
7. **Ranking circularity control (closed mechanically):** preliminary value selects
   before final infrastructure costs, and Feature 005 reports one non-convergent
   pass-1/pass-2 discrepancy audit rather than silently iterating the selection.
8. **Proxy candidate factors:** the 20 `oil_factor` and `storage_factor` values are
   planning assumptions, not surrogate or field outputs.
9. **Long-rollout risk:** local T+5/T+10/T+11/complete-horizon evidence now exists, but
   one-step accuracy still cannot be presented as full-cycle accuracy. Forecast steps
   beyond 24 remain explicitly extended-horizon and low confidence.
10. **Field-representation risk:** the dataset is a literature-informed Jatibarang
    proxy, not a proprietary geomodel or pilot-faithful reconstruction.

## What Can Be Reused Without Redesign

The following should be retained and extended rather than replaced:

- checkpoint hash verification and promoted-model configuration;
- the completed Feature 001 physical compiler, Model B architecture port, deterministic
  batch runner, post-processing, and FastAPI routes;
- compact surrogate regression fixtures;
- the Feature 001 Pydantic and OpenAPI contracts as stable inputs to Feature 005;
- terrain raster provenance and SRTM loader;
- A* implementation and route-segment representation;
- CoolProp property and Darcy-Weisbach helper functions;
- the Pyomo model structure for well, edge, diameter, flow, pressure, and booster
  decisions;
- the facility-result and economic-result component breakdowns;
- assumption-file approach and machine-readable result ledger;
- the five curated MRST validation cases.

## Required Closure Sequence

The dependency-safe path from the current state to the full paper is:

### Gate 0 - Freeze the scope and claim vocabulary

- Commit the intended constitution and Feature 001-007 specifications.
- Define approved source classes: field fact, literature proxy, MRST ground truth,
  surrogate prediction, engineering correlation, and economic assumption.
- Mark all current integrated-economic values as development-only.

### Gate 1 - Complete Feature 001 as a standalone screening engine - **COMPLETE**

- [x] Implement tensor preparation, schedule advancement, batch rollout, accumulation,
      inventory, influence zones, flags, and confidence metadata.
- [x] Validate against the five local MRST cases and pinned upstream metrics.
- [x] Establish CPU throughput for the planned screening batch.

The mechanical promotion gate passed. The scientific verdict remains conditional for
the documented inventory and extended-horizon limitations. Gate 2 is complete for
Features 002-004. Gate 3 code is complete, while its real preset execution remains
blocked on the derived seed banks.

### Gate 2 - Correct and validate Modules 1, 3, and 4 independently - **COMPLETE**

- [x] Remove the remaining network accounting double count; facility duplication is
      closed.
- [x] Define facility ownership and pressure-duty boundaries.
- [x] Implement continuous post-MILP hydraulic verification.
- [x] Complete the eight-case DWSIM validation bundle.
- [x] Replace lumped economics with reconciled, time-indexed DCF and fiscal
      sensitivities.

### Gate 3 - Build the typed Module 005 orchestration service - **CODE COMPLETE / REAL PRESET BLOCKED**

- [x] Implement FastAPI lifecycle, batch endpoints, streaming, caching, and health checks.
- [x] Feed real surrogate outputs into Pass 1, MILP selection, facility sizing, and Pass 2.
- [x] Emit discrepancy, extrapolation, confidence, interference, and shortlist metadata.
- [ ] Complete the derived demo bank and pass the real preset promotion command.

### Gate 4 - Execute the locked A/B/C study - **NOT RUN**

- Run A's fixed 9,000 m3/day, 45-day injection, 30-day soak, 190-day production,
  675 psi BHP, three-cycle schedule on 20 geologies and confirm the declared median-
  and low-permeability cases with MRST.
- Obtain exactly 40 accepted Arm B MRST runs: two seeded normalized-maximin schedules
  per geology, retaining failures and advancing through the deterministic replacement
  order.
- Run C on every scenario in the promoted 200- or 3,240-case freeze bank.
- Re-simulate five unique C plans in MRST and DWSIM-check the minimum, median, and
  maximum facility throughput among those five.
- Compute value, ranking movement, regret, and uncertainty exactly as observed. A
  missing pivot, no viable network, or negative C-B value remains the reported result.

### Gate 5 - Generate the final paper artifact bundle - **PARTIAL**

- [x] Add the deterministic builder, verifier, freeze guard, normalized tables,
      reservoir payload, and one script per figure.
- [x] Render and hash-register Figures 1, 2, 3, and 6 from the working bundle where
      numerical or spatial data apply.
- [ ] Unlock and render Figures 4, 5, 7, and 8 from real experiment tables.
- [ ] Save complete timings, hardware, source classes, validation verdicts, and
      captions for every promoted number.
- [ ] Regenerate all eight figures and freeze a scientifically ready 200- or
      3,240-scenario bundle.

### Gate 6 - Build and harden the live demo - **IMPLEMENTED / REHEARSAL PENDING**

- [x] Implement the Vite/React interface against the typed screening and paper APIs.
- [x] Add the real `case_0016` offline result without substituting unavailable fields.
- [x] Add physical reservoir geometry, independent layers, and accessible split panes.
- [ ] Load the immutable submitted bundle after the scientific freeze.
- [ ] Rehearse offline and failure-mode behavior on presentation hardware.

## Full-Paper Promotion Gate

The implementation should not be described as the full integrated paper framework
until all of the following are true:

Feature 001 already implements control-range flags, inventory reconciliation, and
plume-derived influence radius in its standalone response. The corresponding items
below remain unchecked until the integrated Feature 005 workflow consumes and
propagates them; these are end-to-end promotion conditions, not a second Feature 001
implementation checklist.

- [x] The production integrated screen uses batched surrogate outputs, not `_evaluate_candidate()`.
- [x] All controls are checked against and flagged relative to the training range.
- [x] CO2 inventory and produced-back mass balance are computed and cross-checked.
- [x] Influence radii and interference are derived from predicted spatial fields.
- [x] The MILP receives real surrogate demand and preliminary economic values.
- [ ] Every selected route passes a continuous dense-phase hydraulic check.
- [x] Pipeline and facility costs appear exactly once in portfolio economics by typed
      construction and integration tests; real-preset reconciliation remains pending.
- [x] Facility thermodynamic correlations are validated against the planned DWSIM
      cases; integrated top-K confirmation remains a later gate.
- [x] Standalone NPV, IRR, payback, break-even carbon, and break-even oil pass reconciliation
      tests.
- [x] Four carbon-price cases and the chosen fiscal sensitivities pass the standalone
      reference run; final A/B/C cases remain pending.
- [x] Pass 1/pass 2 selection discrepancy is reported without adopting or iterating it.
- [ ] A, B, and C are run on a consistent comparison basis.
- [ ] Top-K C scenarios are checked with MRST and DWSIM.
- [ ] All paper figures and tables regenerate from pinned inputs and seeds.
- [ ] Every paper-facing number has a provenance row and uncertainty/validation status.
- [ ] The FastAPI service and Vite/React demo run end-to-end with the immutable paper
      bundle on the presentation machine.

## Final Interpretation

The current repository is not a failed implementation of the original concept. It now
contains four completed standalone modules, a mechanically complete Feature 005
integration service, the Feature 006 workbench, and a deterministic partial Feature
007 result pipeline. Together they prove surrogate inference, terrain routing and
hydraulics, facility sizing and DWSIM calibration, annual economic accounting,
parametric fiscal sensitivity, typed ownership, streaming orchestration, physical
reservoir visualization, and machine-readable provenance.

The gap to the full paper is now primarily one of **Feature 005 derived-preset
materialization and Feature 007 experiment execution**, not missing frontend or
figure-factory architecture. Features 001-006 should be consumed as implemented
rather than redesigned. The current Phase 1 integrated values remain development
diagnostics; only the real surrogate-coupled A/B/C run can promote the carbon-price
response and final economics into paper-facing results.
