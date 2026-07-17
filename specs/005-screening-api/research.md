# Feature 005 Research Decisions

## Warm starts and presets

**Decision**: every materialized schedule resolves to an exact schedule-fingerprint
seed. Large derived static/seed payloads stay ignored; tracked manifests record source
case, schedule, hashes, units, and generation method. Runtime never calls MRST.

**Rationale**: Feature 001 rejects cold starts and the accepted upstream corpus does
not contain repeated-geology operational sweeps.

## Request surface

**Decision**: support discriminated `preset` and `inline` requests. Inline clients use
server-known terrain and basis IDs instead of arbitrary filesystem paths. Cap logical
scenarios at 4096 and chunk module batches at 256.

## Preliminary value and accounting

**Decision**: run Feature 004 with flat delivered supply and zero facility, then add
back its discounted flat-supply cash flow before sending pre-logistics value to the
MILP. Final economics consume raw pipeline and facility cash flows once.

## Facilities and produced gas

**Decision**: run Feature 003 only for the selected set. Peak produced gas comes from
the real surrogate increments; CO2 fraction is an explicit provenance-tagged input so
the production-stream storage check remains independent of inventory.

## Supply and refinement

**Decision**: trucking is a same-selected-portfolio counterfactual. After final costs,
one audit MILP uses refined selected-well values and preliminary unselected-well values;
its selection is reported but never adopted or iterated.

## Streaming and cancellation

**Decision**: both endpoints consume the same synchronous event iterator. SSE adds
typed events and heartbeats. A thread-safe process-local token allows cancellation at
batch/stage boundaries and an active-run guard rejects concurrent full screens.

## Scientific promotion

**Decision**: a synthetic fixture proves pivot behavior. The real preset reports its
observed selection honestly; absence of a real pivot is a scientific result, not a
reason to tune assumptions.
