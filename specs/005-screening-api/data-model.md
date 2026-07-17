# Feature 005 Data Model

## ScreenRequest

- discriminated `preset` or `inline` mode and optional caller run ID
- carbon-price/fiscal selection, supply modes, cost case, budget, top-K controls
- inline mode carries geologies, seeds, candidates, sources, and an operational grid
- all IDs unique; generated scenarios <=4096; every candidate/schedule fingerprint has a seed

## ScreeningCandidate

- candidate ID, surface coordinate, geology ID, schedule-fingerprint-to-seed mapping
- produced-gas CO2 fraction plus explicit source class, source ID, and notes

## OperationalGrid

- injection rate, injection duration, soak duration, production duration, BHP, cycles
- deterministic lexicographic Cartesian expansion to typed Feature 001 schedules

## CarbonPricePlan

- carbon-price identity and domain status
- best preliminary strategy per candidate
- Feature 002 pipeline result, selected-well Feature 003 portfolio, final Feature 004 batch
- same-plan trucking economics, interference report, flags, and discrepancy audit

## ScreenResult

- run/request identity and completed/completed-with-failures status
- logical/unique inference counts and cache hits
- per-price plans, cross-price comparison, validation shortlist, detailed predictions
- timings, warnings, module/basis hashes, and provenance catalog

## ProgressEvent

- monotonic sequence, run ID, UTC timestamp, event type, stage, completed/total units
- optional message and JSON payload
- terminal type is exactly one of `result`, `error`, or `cancelled`

State transition:

`registered -> validating -> predicting -> preliminary -> routing -> per-price integration -> comparison -> completed`

Cancellation may move any active state to `cancelled`; unexpected failures move it to
`failed`. The registry entry is removed after a terminal event.

## CompactPresetBank

- hash-verified NPZ metadata plus 20 deduplicated geology arrays
- float32 seed tensor indexed by candidate and schedule, with separate oil/gas deltas
- materializes typed `GeologyInput`, `SeedHistory`, and `PredictRequest` objects one
  surrogate chunk at a time instead of expanding all 3,240 seeds into Python lists
- spills retained spatial predictions to a transient disk store so selected detailed
  fields can be assembled without repeat inference or breaching the 4 GiB RSS target
