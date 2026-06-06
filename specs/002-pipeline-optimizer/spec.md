# Feature 002: CO₂ Pipeline & Logistics Optimizer

## Purpose

Given one or more CO₂ sources and the injection sink (Jatibarang), plus the CO₂ demand
profile produced by Module 2 screening, find the pipeline route, diameter, and booster
station placement that delivers the required CO₂ at minimum total cost while keeping
the CO₂ in dense phase along the entire route. Output a delivered cost in $/tonne that
feeds the economics.

Runs **after** Module 2, because the demand profile (how much CO₂, how fast) is an
input. For the feedback between delivered cost and which scenarios are economic, run
this module at 3–4 representative throughput levels and interpolate; do not iterate to
convergence.

## Inputs

- **Sources** (one or more): location (lat, lon), outlet pressure, outlet temperature,
  available capacity (tonnes/year), CO₂ purity, initial flow velocity.
- **Sink**: Jatibarang location (lat, lon), required delivery pressure at the field.
- **Demand**: total tonnes/year and peak mass-flow rate, from Module 2.
- **Terrain**: SRTM elevation raster (GeoTIFF) covering the source–sink corridor in
  West Java (acquired once, stored in `data/terrain/`).
- **Constraints**: maximum buildable slope, exclusion zones (rivers, settlements,
  protected areas as GeoJSON), dense-phase minimum pressure (~80 bar), pipe maximum
  allowable operating pressure (from diameter/wall/grade), acceptable velocity band
  (~1–5 m/s).
- **Cost parameters**: pipe cost per metre per inch of diameter, booster cost per kW,
  electricity rate, project lifetime (years).

## Outputs

- **Route**: ordered list of points (lat, lon, elevation, cumulative distance) tracing
  the optimal path.
- **Design**: selected diameter (from standard API sizes), number of boosters, booster
  locations along the route, booster power per station.
- **Pressure profile**: pressure, density, and velocity along the route, with the
  dense-phase floor marked and booster "rescue" points visible.
- **Costs**: pipeline CAPEX, booster CAPEX, annual OPEX, and the headline
  **delivered cost per tonne** at the wellhead.
- **Supply-scenario label**: which source configuration this result corresponds to
  (single-source trucking baseline, single pipeline, multi-source hub).

## Method

Two layers.

**Layer 1 — Route optimization (graph search).** Discretize the terrain corridor into
a grid from the SRTM raster. Each cell carries an elevation and a traversal cost that
combines distance, a slope penalty, and exclusion-zone penalties (infeasible cells are
removed). Edges connect neighbouring cells (8-connectivity). Solve for the
minimum-cost path from source to sink with A* or Dijkstra. Cells exceeding the maximum
buildable slope are excluded.

**Layer 2 — Diameter + booster sizing (given the route).** With the route geometry and
its elevation profile fixed, the remaining decisions are diameter and booster
placement. For each candidate diameter (standard API sizes, ~6–8 options), integrate
the steady-state pressure profile along the route, place a booster wherever pressure
would fall below the dense-phase floor (restoring pressure to near inlet), and compute
total cost over the project lifetime. Select the diameter with minimum total cost.
Enumeration suffices — the candidate set is tiny and booster placement is deterministic
given a pressure profile.

## Physics

Steady-state pipe flow with elevation, integrated along the route:

> dP/dL = −(f · ρ · v² / 2D) − ρ · g · sin(θ)

where f is the Darcy friction factor (Colebrook–White), ρ is CO₂ density from CoolProp
at local pressure and temperature, v is velocity (mass flow ÷ ρ ÷ cross-sectional
area), D is diameter, θ is local terrain slope.

- CO₂ properties (density, viscosity) from CoolProp real-gas EOS at every integration
  step — never ideal gas.
- First pass may assume isothermal flow at ground temperature (West Java ground temp
  ~25–28 °C keeps CO₂ supercritical above ~80 bar). Joule–Thomson cooling and
  geothermal exchange can be a documented later refinement, not a v1 requirement.
- Pipe roughness: commercial steel (~45 µm).
- Booster power per station ≈ mass flow × pressure deficit ÷ density ÷ pump efficiency.

## Dependencies

- CoolProp (CO₂ thermodynamics).
- networkx (graph routing) or an equivalent A*/Dijkstra implementation.
- rasterio (reading SRTM GeoTIFF).
- shapely / geopandas (exclusion-zone handling).
- NumPy.

## Done Criteria

- [ ] Optimal route found on real SRTM data for the Subang → Jatibarang corridor.
- [ ] Pressure profile is physically consistent: monotone decrease between boosters,
      boosters restore pressure to near inlet, dense-phase floor never violated in the
      final design.
- [ ] Delivered cost per tonne lands in a defensible literature range for the scenario
      (order-of-magnitude sanity, documented against references).
- [ ] Exclusion zones are respected (route never crosses a flagged cell).
- [ ] Endpoint returns a result in a few seconds for the case-study corridor.
- [ ] Handles edge cases: flat terrain (zero or few boosters), steep terrain (route
      detours around max-slope cells), very low and very high demand.
- [ ] At least two supply scenarios (trucking baseline as a cost-only stub, plus
      optimized pipeline) produce comparable delivered-cost outputs for the economics.
