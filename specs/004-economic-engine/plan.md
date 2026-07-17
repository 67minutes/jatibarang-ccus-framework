# Implementation Plan: Feature 004 Economic Engine

**Branch**: `004-economic-engine` (planning context; implementation preserves the current dirty `002-pipeline-optimizer` worktree) | **Date**: 2026-07-16 | **Spec**: `spec.md`

## Summary

Replace the transitional per-well lump-sum calculation with an independently runnable,
portfolio-safe economic engine. The finished module annualizes physical profiles,
books raw supply and facility cash flows exactly once, reconciles two produced-back CO2
estimates, evaluates four carbon-price cases and three fiscal sensitivities, propagates
deterministic uncertainty bounds, and returns NPV, IRR, discounted payback, break-even
prices, component tables, and ranking stability.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: NumPy and Pydantic v2; no spreadsheet or process-simulator runtime

**Storage**: Versioned JSON basis plus tracked CSV/JSON validation evidence

**Testing**: pytest contract, DCF, storage, fiscal, metric, adapter, batch, schema, and artifact tests

**Target Platform**: CPU-only Windows presentation laptop

**Project Type**: Typed Python library and validation CLI; no Feature 004 HTTP endpoint

**Performance Goals**: warmed 200 portfolios x 4 carbon prices x 3 fiscal cases in <=1 second p95

**Constraints**: raw cash-flow accounting only; no levelized/raw double charge; no implicit campaign repeat; fiscal outputs are screening sensitivities, not exact PSC replicas

**Scale/Scope**: 1-256 portfolios, 1-50 annual periods, >=4 carbon prices, and 1-3 fiscal cases

## Constitution Check

- PASS: NumPy runtime and typed Pydantic boundaries match the architecture.
- PASS: the engine is independently runnable and testable.
- PASS: uncertainty and extrapolation qualifications are preserved.
- PASS: raw pipeline/facility costs are consumed once; display-only levelized costs are excluded.
- PASS: no surrogate retraining, live MRST/DWSIM, spreadsheet, Feature 005 API, or frontend work is introduced.

Post-design re-check: PASS. There are no constitution exceptions.

## Structure Decision

Extend the shared contracts and infrastructure package with `economics.py`,
`economic_adapters.py`, and `economic_validation.py`. Keep the current Phase 1 runner
through a clearly labeled development-only adapter. Save the validation bundle under
`paper/validation/feature004/` and keep final A/B/C economics in Feature 007.

## Implementation Sequence

1. Freeze the batch contracts, annual time basis, supply discriminators, fiscal
   equations, metric statuses, uncertainty semantics, and provenance.
2. Implement annualization, storage reconciliation, raw cost ownership, DCF, fiscal
   cash flows, root metrics, deterministic bounds, and ranking stability.
3. Add Feature 001-003 adapters without changing their public contracts and migrate
   the Phase 1 compatibility caller away from the legacy economic models.
4. Generate closed-form and synthetic validation evidence, benchmark the full batch,
   hash every artifact, and separate accounting PASS from screening-grade qualification.
5. Synchronize the complete repository status surface only after evidence exists.

## Explicit Non-Goals

- No Feature 005 `/screen` orchestration or real surrogate coupling.
- No implicit repetition or production-tail forecast beyond supplied physical data.
- No statutory PSC, tax-return, reserves, financing, depreciation, or FEED model.
- No update of submitted-abstract economics as final-paper results.

