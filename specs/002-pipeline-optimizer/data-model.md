# Feature 002 Data Model

## PipelineSource

- unique id, name, coordinate
- annual capacity in tonnes/year and peak deliverability in kg/s
- outlet pressure/temperature and CO2 purity >=0.95

## PipelineWellDemand

- unique well id and coordinate
- annual demand in tonnes/year and peak flow in kg/s
- pre-logistics project value in USD
- influence radius and optional mandatory-selection flag

## ExclusionZone

- id, class, `hard` or `penalty` mode
- WGS84 geometry, metric buffer, and penalty multiplier
- source, extraction time, and license/provenance

## RouteNode and RouteSegment

- node kind: source, well, or junction
- segment endpoints, WGS84 geometry, elevation samples, metric length and slopes
- hard/penalty intersection audit and terrain/exclusion hashes
- route library fingerprint derived from every input and routing option

## HydraulicCurve

- segment, diameter, MAOP, pressure anchors
- peak-flow breakpoints with pressure-loss, velocity, and density samples
- conservative-envelope and CoolProp provenance

## PipelineDesignRequest

- objective mode, supply scenario, sources, well demands, route library
- annual CO2 budget, lifecycle/cost case, solver limits, and physical assumptions
- minimum-cost mode additionally requires mandatory wells or a delivery target

## PipelineDesignResult

- domain/solver status, objective, bound, gap, and runtime
- selected/rejected wells and reasons
- built segments, boosters, source allocation, node states, and continuous profiles
- constraint/hydraulic audit
- raw, present-value, levelized, and per-well allocated costs
- terrain, exclusions, costs, assumptions, solver, and route provenance

State transitions: `validated_request -> solved -> continuously_verified -> accepted`.
Economic empty selection ends as `no_viable_network`; contradictory inputs end as
`infeasible`; a post-solve physics failure ends as `hydraulic_verification_failed`.

## SupplyComparisonResult

- common accounting basis and cost case
- optimized pipeline result
- trucking result with annual mass, route distance, loading/conditioning and transport
  costs
- difference in delivered and lifecycle cost plus provenance

