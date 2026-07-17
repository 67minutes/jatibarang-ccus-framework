# Feature 001 Research Decisions

## Warm-start contract

**Decision**: require a pre-operation state and eight physical seed frames, including
seed-period production increments and provenance.

**Rationale**: the checkpoint was trained and evaluated as a Tin=8 forecaster from
MRST-manifold histories. Repeated-state cold starts are unvalidated, and runtime MRST
violates the constitution.

**Alternatives considered**: repeated initial states; runtime MRST warm start. Both
were rejected.

## Tensor and schedule contract

**Decision**: retain the upstream 20-channel stored tensor while forwarding channels
0-12 for the promoted checkpoint. Generate 4/2/6 inject/soak/produce frames per cycle
and use midpoint stage-progress features.

**Rationale**: this reproduces `boreyes2026/ml/dataset_hnp.py` and preserves fixture
parity. Permeability enters the exported data as log10(mD).

## Batch responses

**Decision**: accept up to 256 scenarios, microbatch at 16 by default, return compact
results by default, and allow full fields for at most ten named scenarios.

**Rationale**: full JSON fields for 200 scenarios are hundreds of megabytes before
JSON expansion. Compact summaries are sufficient for screening.

## CO2 inventory

**Decision**: calculate tonnes using pore volume, predicted gas saturation and
`z_co2`, and pressure/temperature-dependent pure-CO2 density from a CoolProp lookup
table. Return approximation provenance and reconciliation residuals.

**Rationale**: the checkpoint has no produced-CO2 head. This is the explicit
Feature-004-compatible approximation, not compositional ground truth.

## Confidence

**Decision**: pin a small derived metadata table from the promoted upstream metrics
and choose the nearest conservative horizon bucket. Forecasts beyond 24 steps are
flagged as extended-horizon low confidence.

**Rationale**: this prevents a long rollout from inheriting a one-step accuracy claim.
