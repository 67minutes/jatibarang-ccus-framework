# Implementation Plan: Feature 001 Subsurface Surrogate Inference Service

**Branch**: `main` | **Date**: 2026-07-15 | **Spec**: `spec.md`

## Summary

Complete the frozen `production_v2` surrogate as a self-contained, typed FastAPI
inference service. The implementation compiles physical geology, schedule, and an
explicit eight-frame warm start into the exact checkpoint tensor contract, runs
deterministic CPU microbatched rollouts, derives qualified production/inventory/plume
outputs, and publishes compact and detailed response modes.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: PyTorch CPU, NumPy, Pydantic v2, FastAPI, CoolProp

**Storage**: Local ignored checkpoint and MRST validation files; tracked small JSON/CSV evidence

**Testing**: pytest and FastAPI TestClient

**Target Platform**: Windows presentation laptop and portable CPU Python environment

**Project Type**: Python package and web service

**Performance Goals**: warm one-step p95 <1 s; 24-step rollout p95 <3 s; compact 200x24 batch <8 min and <4 GB peak memory on the current machine

**Constraints**: frozen checkpoint/architecture, CPU only, no runtime upstream import, no runtime MRST, deterministic output, no silent extrapolation

**Scale/Scope**: 64x64x1 geologies, Tin=8, 3-4 cycles, up to 256 scenarios per request, full fields for at most 10 batch scenarios

## Constitution Check

- PASS: uses Python/FastAPI, PyTorch CPU, CoolProp, and typed Pydantic boundaries.
- PASS: checkpoint is loaded once and every module remains independently testable.
- PASS: out-of-range requests run with explicit flags.
- PASS: produced-back CO2 remains an inventory-based approximation with uncertainty.
- PASS: no retraining, live MRST, DWSIM, MATLAB, or upstream runtime dependency.

## Project Structure

```text
src/jatibarang_ccus/
|-- api/
|   `-- app.py
`-- surrogate/
    |-- schemas.py
    |-- preprocessing.py
    |-- postprocessing.py
    |-- metadata.py
    `-- runner.py

tests/surrogate/
|-- test_preprocessing.py
|-- test_postprocessing.py
|-- test_batch_rollout.py
`-- test_api.py

paper/validation/
|-- feature001_validation.json
|-- feature001_validation.csv
`-- feature001_benchmark.json
```

**Structure Decision**: extend the existing single Python package. Feature 001 routes
live in the shared application factory so Feature 005 can add orchestration routes
without a second service.

## Delivery Gates

1. [x] Tensor/schedule parity.
2. [x] Deterministic batch rollout and physical production units.
3. [x] Inventory/plume/confidence post-processing.
4. [x] FastAPI contract and lifecycle.
5. [x] Five-case validation and benchmark evidence.

There are no constitution violations requiring complexity exceptions.

## Completion Record

Implementation completed on 2026-07-15 without changing the promoted architecture or
weights. Mechanical promotion is **PASS**: 41 repository tests pass, the five-case
validator completes, and every performance threshold passes. Scientific promotion is
**CONDITIONAL** because the five local cases do not replace the upstream 36-case
evaluation, inventory is an engineering approximation, and 3/4-cycle runs extend past
the pinned 24-step rollout horizon.

The benchmark recorded warm one-step p95 `0.0737 s`, 24-step rollout p95 `1.7610 s`,
and `281.12 s` for a compact `200 x 24` batch with `806,875,136` bytes peak RSS.
Implementation tasks and caveats are recorded in [`tasks.md`](tasks.md); machine-readable
evidence is under [`../../paper/validation/`](../../paper/validation/).
