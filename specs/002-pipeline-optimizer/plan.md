# Implementation Plan: Feature 002 Pipeline and Logistics Optimizer

**Branch**: `002-pipeline-optimizer` | **Date**: 2026-07-15 | **Spec**: `spec.md`

## Summary

Complete the existing terrain-routing, CoolProp, and Pyomo scaffold as an independently
runnable CO2 logistics module. The finished feature builds exclusion-aware multi-source
route libraries with deterministic free junctions, co-optimizes well selection and
network design, verifies every selected route with continuous local-state hydraulics,
and compares the optimized pipeline with a trucking cost baseline.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: Pydantic v2, NumPy, rasterio, pyproj, Shapely, networkx,
CoolProp, Pyomo, CBC; matplotlib only for validation artifacts

**Storage**: tracked small JSON/GeoJSON/CSV evidence and configuration; ignored SRTM
raster and route caches

**Testing**: pytest, analytic hydraulic fixtures, synthetic MILP fixtures, and the
pinned 20-well Jatibarang case

**Target Platform**: Windows presentation laptop, CPU-only Python environment

**Project Type**: typed Python library and CLI; no Feature 002 HTTP endpoint

**Performance Goals**: CBC solve under 30 seconds at <=2% accepted gap for the full
20-well case; continuous verification error <=1 bar or 5%; no active pressure below
80 bar or above diameter MAOP

**Constraints**: offline runtime, pure-CO2 CoolProp model for >=95% purity, no Excel,
MRST, DWSIM, or surrogate integration; no candidate prefilter in the acceptance run

**Scale/Scope**: one or more sources, 20 candidate wells, six pipe diameters,
source/well/free-junction nodes, pipeline and trucking supply cases

## Constitution Check

- PASS: Python, Pydantic, CoolProp, Pyomo, and CBC match the mandated architecture.
- PASS: the module is independently runnable and has no Feature 005 orchestration logic.
- PASS: all runtime thermodynamics use CoolProp and the dense-phase floor is audited.
- PASS: public/cost inputs retain screening-proxy provenance and are not presented as
  proprietary field or FEED data.
- PASS: no raw MRST corpus, retraining, live process simulation, or spreadsheet runtime.

Re-check after design: PASS. There are no constitution exceptions.

## Project Structure

```text
src/jatibarang_ccus/
|-- contracts.py
`-- infrastructure/
    |-- routing.py
    |-- hydraulics.py
    |-- pipeline.py
    |-- supply.py
    `-- validation.py

tests/infrastructure/
|-- test_routing_exclusions.py
|-- test_hydraulic_verification.py
|-- test_pipeline_network.py
`-- test_supply_comparison.py

paper/validation/feature002/
`-- generated JSON, CSV, and PNG evidence
```

**Structure Decision**: extend the existing package and shared contracts. Feature 001
remains unchanged; the Phase 1 proxy orchestrator uses an adapter until Feature 005
supplies real surrogate/economic inputs.

## Delivery Gates

1. Typed route, demand, optimization, supply, and result contracts.
2. Exclusion-aware route graph and deterministic junction extraction.
3. Peak-flow MILP with piecewise pressure loss, multiple sources, and sized boosters.
4. Continuous hydraulic, connectivity, and accounting verification.
5. Pipeline/trucking comparison plus reproducible validation evidence.
