# Implementation Plan: Feature 003 Surface Facility Cost Model

**Branch**: `003-facility-model` (planning context; the current dirty Git worktree remains on `002-pipeline-optimizer`) | **Date**: 2026-07-15 | **Spec**: `spec.md`

## Summary

Replace the partial scalar facility calculation with an independently runnable,
portfolio-safe surface-facility module. The finished feature sizes one dedicated
well-pad skid per selected well, keeps the Feature 002 dense-phase delivery boundary
explicit, compresses only recovered production CO2, pumps fresh and recycled dense
CO2 only across the remaining wellhead pressure rise, sizes the separator and
conditioning equipment, and returns one-and-only-one CAPEX/OPEX/loss allocation.
Runtime calculations use typed Pydantic contracts, NumPy, and CoolProp. A pinned
eight-case DWSIM flowsheet is run offline to validate duties, stream balances, and the
runtime correlation envelope and to generate the paper-facing evidence bundle.

## Technical Context

**Language/Version**: Python 3.11+ at runtime; a .NET Framework 4.7.2 console helper
for the installed DWSIM 10 automation ABI, built with Visual Studio 2022 MSBuild

**Primary Dependencies**: Pydantic v2, NumPy, CoolProp; matplotlib for evidence plots; DWSIM automation assemblies only in the offline validation workflow

**Storage**: tracked JSON design/cost/calibration inputs, a small tracked DWSIM source flowsheet and PFD, and tracked CSV/JSON/PNG validation evidence

**Testing**: pytest unit, contract, accounting, integration-adapter, analytic-physics, and artifact-manifest tests plus the eight-point DWSIM comparison

**Target Platform**: Windows presentation laptop, CPU-only Python runtime; DWSIM is required only on the engineering workstation that refreshes validation evidence

**Project Type**: typed Python library and CLI; no Feature 003 HTTP endpoint

**Performance Goals**: a warmed eight-well portfolio evaluates in no more than 0.5 seconds p95; no DWSIM process is launched at runtime

**Validation Goals**: across eight pinned calibration cases, compressor, pump, and total power have mean absolute percentage error no greater than 5% and no point greater than 10%; stream mass-balance residual is no greater than 0.1%; all monotonicity and ownership reconciliations pass

**Constraints**: CoolProp real-fluid properties only at runtime; no ideal-gas calculations; no source compression, pipeline booster cost, wellbore model, economics, live DWSIM, Excel, MRST, or surrogate logic; screening correlations must not be described as FEED or vendor quotations

**Scale/Scope**: 1-8 selected wells, 8,000-10,000 standard m3/day injection per active well, 80-120 bar calibration delivery pressure, approximately 4,500-7,300 standard m3/day peak produced gas, and 0.525-0.795 produced CO2 mole fraction

## Constitution Check

- PASS: Python, Pydantic, NumPy, and CoolProp match the runtime architecture.
- PASS: the module is independently runnable and independently testable.
- PASS: the Feature 002/003 pressure and cost boundary is explicit and prevents
  source/pipeline duties from being charged again.
- PASS: DWSIM is offline validation only and is absent from runtime imports and the
  presentation-laptop execution path.
- PASS: every cost, loss, and design coefficient carries units, source class, version,
  and screening-proxy status.
- PASS: no raw MRST corpus, retraining, spreadsheet runtime, or Feature 004/005 domain
  logic is introduced.

Post-design re-check: PASS. There are no constitution exceptions.

## Project Structure

### Documentation and design artifacts

```text
specs/003-facility-model/
|-- plan.md
|-- research.md
|-- data-model.md
|-- quickstart.md
`-- contracts/
    `-- facility-model.schema.json

docs/dwsim-validation/
|-- methodology.md
|-- jatibarang_facility.dwxmz
|-- process_flow_diagram.png
`-- README.md
```

### Source, inputs, tests, and evidence

```text
src/jatibarang_ccus/
|-- contracts.py
`-- infrastructure/
    |-- thermo.py
    |-- facility.py
    |-- facility_costs.py
    `-- facility_validation.py

data/jatibarang/
|-- facility_design_basis.json
|-- facility_cost_basis.json
`-- facility_validation_cases.json

tools/dwsim/FacilityValidationRunner/
|-- FacilityValidationRunner.csproj
`-- Program.cs

tests/facility/
|-- test_contracts.py
|-- test_pressure_duty.py
|-- test_equipment_sizing.py
|-- test_costs_ownership_and_losses.py
|-- test_phase1_adapter.py
`-- test_validation_artifacts.py

paper/validation/feature003/
|-- artifact_manifest.json
|-- dwsim_reference.csv
|-- runtime_comparison.csv
|-- correlation_error_summary.json
|-- equipment_cost_curve.csv
|-- facility_validation.png
|-- facility_cost_curve.png
`-- process_mass_balance.csv
```

**Structure Decision**: extend the existing Python package and shared contracts. The
runtime module owns well-pad equipment only. The offline .NET helper loads and solves
the pinned DWSIM model but is neither installed nor imported by the Python package.
The temporary Phase 1 caller is updated only as an adapter: it evaluates the selected
portfolio once and consumes per-well allocations until Feature 005 replaces that
orchestrator.

## Implementation Sequence

### Gate 1 - Freeze units, ownership, and contracts

1. Replace `FacilityInput`/`FacilityResult` with the portfolio request/result models
   defined in `contracts/facility-model.schema.json` and Pydantic equivalents.
2. Carry injection volume with its 1.01325 bar/15 C reference and use an explicit
   `fresh_co2_peak_mass_flow_kg_s`; never convert standard volume using dense-phase
   delivery density.
3. Remove the ambiguous individual `well_count` multiplier. Validate unique well IDs
   and return exact per-well and portfolio reconciliation fields.
4. Pin `dedicated_well_pad_skids` as the v1 ownership basis. Source conditioning,
   trunk compression, and pipeline boosters remain Feature 002 costs.

### Gate 2 - Correct the fixed flowsheet and physical duties

1. Model fresh dense CO2 as pipeline delivery -> well-pad pump -> injection header.
2. Model produced CO2 as three-phase separation -> dehydration -> staged recycle
   compression/intercooling -> final 27 C dense-phase cooling -> pump suction. A
   bypass handles recycle-disabled cases.
3. Pump the combined fresh-plus-recycled dense flow only across
   `max(0, wellhead_pressure - delivery_pressure)`; compressor duty never includes
   that same pressure interval for fresh CO2.
4. Size separators from gas and liquid peak loads with explicit pressure,
   temperature, Souders-Brown, residence-time, and L:D assumptions. Water rate remains
   a labeled case-study assumption until a predictive water stream exists.
5. Calculate injection, production/recycle, and standby energy using separate annual
   operating hours derived from the HnP schedule.

### Gate 3 - Cost, loss, redundancy, and accounting

1. Move coefficients into versioned low/base/high cost and design-basis JSON files;
   record equation, units, reference year, escalation, location treatment, URL or
   bibliographic locator, and source class for every value.
2. Cost each compressor, pump, cooler, dehydration package, separator, and
   balance-of-plant item once. Represent installed/duty/spare train counts explicitly.
3. Return raw CAPEX and annual OPEX components. Levelized or discounted values remain
   Feature 004 responsibilities.
4. Replace the stage-count loss heuristic with a mass ledger for conditioning purge,
   unrecovered recycle, and fugitives. Bulk produced-back CO2 is labeled separately
   and is not deducted again as a surface loss.
5. Enforce exact reconciliation: equipment components sum to each well result and
   well results sum to the portfolio once.

### Gate 4 - Offline DWSIM calibration and evidence

1. Build the fixed DWSIM flowsheet with the CoolProp property package, named streams
   and unit operations, explicit efficiencies, intercooler outlet temperature,
   separator conditions, recycle recovery, and energy streams.
2. Pin an eight-run, resolution-IV two-level design spanning injection rate, delivery
   pressure, peak produced gas, and produced CO2 fraction. Keep injection pressure,
   separator conditions, efficiencies, and reference conditions explicit in the case
   JSON rather than hidden in the flowsheet.
3. Use the offline .NET automation runner to load the model, set each case, solve it,
   and export stream mass balances, stage powers, pump power, cooler duties, separator
   loads, and convergence status.
4. Fit only documented scalar correction factors or power-law coefficients with
   NumPy. Reject a fit that violates the error gates or monotonic behavior; never
   silently widen the calibration envelope.
5. Generate the hashed manifest, CSV/JSON tables, two paper-ready plots, and PFD. The
   report distinguishes native DWSIM duties from costs derived by applying the tracked
   screening correlations to DWSIM-sized duties.

### Gate 5 - Integration safety and promotion

1. Update the Phase 1 compatibility caller to build one portfolio request after well
   selection and consume the returned per-well allocations. Do not alter its analytic
   subsurface proxy or claim end-to-end completion.
2. Keep Feature 001 API/OpenAPI and Feature 002 contracts unchanged; add regression
   tests around the adapter boundary.
3. Run focused tests, the eight-case evidence workflow, the complete repository
   regression, JSON-schema validation, manifest hash verification, and
   `git diff --check`.
4. Synchronize `README.md`, `specs/README.md`, the gap audit, the Feature 003 spec and
   quickstart, `data/README.md`, and the Feature 003 artifact README only after saved
   evidence exists. Report mechanical promotion separately from the engineering
   validation verdict.

## Delivery Gates

1. Typed portfolio, well-load, equipment, loss-ledger, allocation, and validation
   contracts with explicit units and provenance.
2. Correct fresh-pump/recycle-compressor pressure ownership and standard-volume mass
   conversion.
3. Auditable separator, dehydration, intercooling, redundancy, CAPEX, OPEX, and loss
   components with no double charging.
4. Eight converged DWSIM cases and a hashed comparison bundle satisfying the stated
   error and mass-balance thresholds.
5. Monotonicity, runtime, adapter, schema, artifact, and full-regression tests pass.

## Implemented Result

All five gates are implemented. The saved DWSIM 10.0.9650 run converged for all eight
cases. Compressor, pump, and total-power MAPE are `0.0000165%`, `0.0000000074%`, and
`0.0000147%`; maximum pointwise power error is `0.0000198%`; maximum DWSIM mass-balance
residual is zero. The manifest records separate mechanical and engineering `PASS`
verdicts. The first live comparison also identified and closed a near-critical
pump-suction risk by adding the final 27 C recycle cooler.

## Explicit Non-Goals

- No live DWSIM or process simulator call during screening.
- No dynamic multiphase transient facility simulation or wellbore hydraulics.
- No proprietary Jatibarang facility design, Indonesian vendor quote, or FEED claim.
- No source capture/compression or pipeline-booster redesign owned by Feature 002.
- No economic discounting, fiscal treatment, well selection, API orchestration, or UI.
- No surrogate retraining, MRST runtime coupling, or raw 177-case corpus import.
