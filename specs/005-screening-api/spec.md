# Feature 005: Screening API and Orchestrator

## Status

Production code and synthetic/mechanical integration are implemented as of
2026-07-16. Twenty-three focused tests and the 140-test repository suite pass. Real preset
promotion is **BLOCKED** because the fixed MRST-derived demo/full banks have not yet
been fully generated and imported. No proxy result is substituted. Feature 007 owns
the A/B/C runs and scientific or paper-number promotion.

## Purpose

Provide the production FastAPI integration layer for Features 001-004. A request
supplies preset or inline geology, exact schedule-compatible warm seeds, candidates,
sources, operational schedules, economic dimensions, and server-known basis IDs. The
response reports a development plan for every carbon price plus cross-price,
validation, qualification, timing, and provenance data.

The legacy Phase 1 `_evaluate_candidate()` workflow remains available only for the
historical abstract-number ledger. It is not used by `/screen`.

## Runtime Flow

1. Resolve the request, preset hashes, exact seed coverage, terrain, bases, checkpoint,
   and CBC readiness.
2. Expand and canonicalize logical scenarios, deduplicate identical physical inputs,
   and call Feature 001 in chunks of at most 256.
3. Annualize predictions through Feature 004. Preliminary economics use pinned flat
   delivered supply and zero facility cost; discounted flat supply is added back to
   form the Feature 002 pre-logistics value.
4. Choose each candidate's best schedule separately for every carbon price. Build the
   route library once and run the real Feature 002 `max_net_value` MILP once per price,
   with no forced minimum selection.
5. For accepted non-empty portfolios, call Feature 003 once for selected wells only,
   using predicted production increments, pipeline delivery pressure, and explicit
   provenance-tagged produced-gas CO2 composition.
6. Evaluate selected per-well and aggregate Feature 004 portfolios across every
   requested carbon price and fiscal case using raw pipeline allocations, facility
   costs/losses, real inventory profiles, and surrogate uncertainty.
7. Price trucking for the same selected set and rerun economics. Trucking is never a
   separate well selector.
8. Run one non-convergent audit MILP. Selected wells receive refined values with
   actual pipeline costs added back; unselected wells retain preliminary values. The
   audit selection is reported but never adopted or iterated.
9. Assemble geodesic influence-radius interference, flags, cross-price entry/exit,
   deterministic top-K validation shortlist, up to ten detailed predictions, timings,
   and provenance.

## Requests

`ScreenRequest` is discriminated by `mode`:

- `preset`: `jatibarang_demo_v1` or `jatibarang_full_v1` plus optional carbon/fiscal
  filters and result-detail controls.
- `inline`: typed geologies, seeds, candidates, sources, schedules or operational
  grid, annual budget, at least four carbon prices, fiscal cases, economic assumptions,
  and server-known terrain/routing/pipeline basis IDs.

Each operational schedule includes injection rate, injection duration, soak duration,
production duration, production BHP, and cycles. Every candidate/schedule fingerprint
must map to a seed carrying that exact fingerprint. Missing coverage is `422`; the
service never rewrites a fingerprint or invents a cold start.

Logical scenarios are capped at 4,096. Feature 001 and preliminary Feature 004 calls
are internally chunked at 256. Identical Feature 001 physical inputs run once per
request.

Every candidate carries an explicit produced-gas CO2 mole fraction and provenance.
This value is not inferred from inventory, preserving an independent storage
cross-check.

## Results

`ScreenResult` contains:

- one `CarbonPricePlan` per requested carbon price;
- best per-candidate strategy, selected wells, Feature 002 result, selected-well
  Feature 003 portfolio, and Feature 004 batches;
- same-selected-set trucking economics;
- explicit empty, infeasible, no-network, hydraulic, and solver outcomes;
- selection-discrepancy audit, interference matrix and flagged pairs;
- cross-price entrants/exits and pivot flag;
- deterministic validation shortlist and at most ten detailed predictions;
- logical/unique/cache counts, timings, warnings, flags, and provenance catalog.

If only some prices fail, the overall status is `completed_with_failures`. Dependency
unavailability is `503`; a concurrent second full run is `429`.

## Endpoints

- `POST /screen`: synchronous integrated result.
- `POST /screen/stream`: equivalent execution as typed SSE events.
- `DELETE /screen/runs/{run_id}`: cooperative cancellation.
- `GET /presets`: dimensions, manifest/hash, and readiness.
- `GET /health`: checkpoint, CBC, terrain, facility/economic bases, presets, and active
  run readiness.

SSE emits monotonic `run_started`, `stage_started`, `progress`, `stage_completed`,
`warning`, and exactly one terminal `result`, `error`, or `cancelled` event.

## Derived Presets

- `jatibarang_demo_v1`: 20 normalized-maximin proxy geologies by 10 schedules = 200.
- `jatibarang_full_v1`: the same 20 geologies by all 162 schedules = 3,240.

The tracked design rules select accepted upstream parameter sets deterministically and
map stable case-ID order to W01-W20. The demo selects five normalized-maximin
rate/soak/production/BHP combinations, fixes injection duration at 45 days, and pairs
each with three and four cycles.

MRST runs offline in `boreyes2026`. Only static maps, eight-frame histories, seed
production increments, provenance, and hashes may be imported. Raw 177-case training
data is forbidden in this repository. Large payloads are ignored and hash-manifested.

## Boundaries

No live MRST/DWSIM, surrogate retraining, frontend, durable job store, arbitrary client
filesystem paths, raw-corpus copy, synthetic minimum-well forcing, separate trucking
selector, iterative audit convergence, or paper-number promotion.

## Acceptance

- [x] Real Feature 001 predictions feed Feature 002 demand/value adapters in production
      code and integration fixtures.
- [x] Candidate-specific schedule choice runs independently per carbon price.
- [x] Facilities run only for selected wells.
- [x] Duplicate physical inputs invoke the surrogate once per request.
- [x] Synthetic fixtures prove price pivot, pass-1/pass-2 discrepancy, and partial
      failures.
- [x] Sync and streaming use one event-producing pipeline.
- [x] Pipeline/facility costs have exactly-once typed ownership.
- [x] Interference, provenance, shortlist, readiness, SSE, cancellation, and OpenAPI
      contracts are tested.
- [x] Focused and complete Python regression suites pass.
- [ ] The real 200-scenario demo payload is complete and passes the under-10-minute,
      under-4-GiB promotion run.
- [ ] The full 3,240 bank is materialized and passes load/hash/chunk/stream readiness;
      its long paper run remains Feature 007 work.
