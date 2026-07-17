# Implementation Plan: Feature 005 Screening Orchestrator

**Branch**: `005-screening-api` (planning context; implementation preserves the dirty
`002-pipeline-optimizer` worktree) | **Date**: 2026-07-16 | **Spec**: `spec.md`

## Summary

Add a typed in-process FastAPI orchestration layer that runs the frozen surrogate,
pipeline MILP, selected-well facilities, and annual economic engine in the required
2 -> 1 -> 3 -> 4 order. The same event-producing workflow serves synchronous and SSE
clients, carries every qualification and source reference, compares pipeline with a
same-portfolio trucking counterfactual, and reports one non-convergent selection audit.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: FastAPI, Pydantic v2, PyTorch CPU, NumPy, Pyomo/CBC,
CoolProp, PyProj; no new runtime dependency

**Storage**: tracked JSON manifests and compact evidence; ignored derived NPZ preset
payloads; transient in-memory cancellation state only

**Testing**: pytest unit, contract, integration, SSE, artifact, and real-preset checks

**Target Platform**: CPU-only Windows presentation laptop

**Project Type**: typed Python service and validation CLI

**Performance Goals**: 200 logical scenarios in <=10 minutes and <4 GB peak RSS;
each CBC solve retains its <=30 second limit

**Constraints**: exact warm-start coverage; request-local inference deduplication;
Features 001-004 remain independently runnable; no live MRST/DWSIM or paper promotion

**Scale/Scope**: 1-20 candidates, 1-4096 logical scenarios, chunks of <=256,
at least four carbon prices, up to eight selected wells, and up to ten detailed fields

## Constitution Check

- PASS: the existing Python/FastAPI/Pydantic and CPU-only runtime is preserved.
- PASS: the checkpoint remains startup-loaded once and the four modules stay separate.
- PASS: CoolProp, Pyomo/CBC, raw-cost accounting, and trained-range flags are reused.
- PASS: MRST is limited to an offline derived-seed export; DWSIM remains offline.
- PASS: no raw 177-case corpus, proprietary field claim, frontend, or paper result is added.

Post-design re-check: PASS. The transient run registry is process-local coordination,
not durable job state or a new persistence subsystem.

## Structure Decision

Create `src/jatibarang_ccus/screening/` for Feature 005 schemas, presets, adapters,
progress/cancellation, orchestration, and validation. Extend the shared application
factory in `src/jatibarang_ccus/api/app.py`; do not alter Feature 001 routes. Store
tests under `tests/screening/`, ignored payloads under `data/screening_presets/`, and
promotion evidence under `paper/validation/feature005/`.

## Implementation Sequence

1. Freeze request/result, SSE, failure, seed-bank, provenance, and preset contracts.
2. Add test-first grid expansion, seed coverage, adapter, interference, and run-state behavior.
3. Implement deduplicated surrogate inference and preliminary Feature 004 scoring.
4. Add per-price Feature 002 selection, selected-only Feature 003 sizing, final Feature
   004 economics, trucking counterfactual, and the single audit re-solve.
5. Expose synchronous, streaming, cancellation, preset, and health routes from the
   shared FastAPI app.
6. Add offline upstream seed export and local import/verification tooling.
7. Generate mechanical evidence, run the complete regression, and synchronize docs.

## Explicit Non-Goals

- No surrogate retraining, cold-start fabrication, live MRST/DWSIM, or raw corpus copy.
- No separate trucking portfolio optimizer or iterative selection convergence.
- No Feature 006 UI, Feature 007 A/B/C execution, or paper-number promotion.
- No forced minimum selection when the rational MILP result is an empty portfolio.

## Implementation and Promotion Record

The sequence is complete through code, focused/complete regression, OpenAPI parity,
upstream fixed-seed export tooling, importer, and hash verifier. The real demo
promotion command currently exits with a dependency-blocked verdict because its
ignored MRST-derived manifest/payload is absent. The evidence explicitly records
`fabricated_result=false`; this is not a mechanical or scientific PASS. A bounded
one-seed upstream smoke validates the exporter mode, while completing the 200/3,240
banks remains offline data-production work.
