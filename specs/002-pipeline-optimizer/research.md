# Feature 002 Research Decisions

## Flow units

**Decision**: carry annual demand in tonnes/year and peak hydraulic flow in kg/s as
separate required fields.

**Rationale**: source budgets and lifecycle cost use annual mass, while diameter,
velocity, pressure loss, and booster power must use peak flow.

**Alternatives considered**: reuse injected tonnes for both. Rejected because the
current prototype silently treats cycle mass as an annual hydraulic rate.

## Route representation

**Decision**: rasterize hard and penalty exclusions, union the A* cell paths, and turn
endpoints plus union-graph cells of degree other than two into nodes. Compress the
degree-two chains into candidate pipe segments.

**Rationale**: this creates deterministic shared trunks and free junctions without a
continuous Steiner optimization or unsupported field data.

## Piecewise hydraulics

**Decision**: precompute a conservative pressure-loss envelope at zero, minimum
velocity, and 25/50/75/100% of maximum-velocity capacity. Encode equality with Pyomo
DCC variables and verify the result with continuous local-state integration.

**Rationale**: DCC is CBC-compatible and avoids assuming that the one-chord loss used
by the prototype is accurate across the operating range.

## Pressure interpretation

**Decision**: require hydraulic head to decrease without a booster; allow static
pressure to recover downhill while enforcing the dense-phase floor and MAOP everywhere.

**Rationale**: a monotone static-pressure rule conflicts with signed elevation head.

## Optimization and empty portfolios

**Decision**: support `max_net_value` and `min_lifecycle_cost`. The preset uses net
value. A rational empty portfolio returns `no_viable_network`; contradictory mandatory
demands return `infeasible`.

**Rationale**: solver feasibility and economic viability are different states.

For minimum-cost mode with mandatory wells and no delivery target, optional wells are
provably inactive because every network and commodity coefficient is non-negative.
The implementation therefore applies an exact presolve: retain audited shortest
source-to-mandatory corridors, orient a single-source corridor away from the source,
and evaluate the same PWL loss at the known downstream mandatory flow. General
selectable, delivery-target, and multi-source cases retain bidirectional DCC PWL flow
decisions.

## Cost accounting

**Decision**: return raw CAPEX, annual OPEX, commodity cost, present-value lifecycle
cost, and levelized delivered cost separately. The levelized figure is display and
comparison data, not an additional DCF debit.

**Rationale**: the Phase 1 prototype currently counts network cost through both
delivered cost and an allocated capital charge.

## Evidence basis

**Decision**: use pinned public exclusion data with ODbL attribution, NETL-derived
pipeline/booster low-base-high correlations, and IEAGHG trucking cost cases. Record
source year, URL, hash, and screening-proxy status.

**Rationale**: this is reproducible and defensible for screening while remaining honest
that it is not an Indonesian vendor quotation or FEED estimate.
