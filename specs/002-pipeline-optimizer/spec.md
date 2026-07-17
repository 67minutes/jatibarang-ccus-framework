# Feature 002: CO₂ Pipeline & Logistics Optimizer

## Purpose

**Implementation status (2026-07-15): COMPLETE at screening grade.** The standalone
route, design, verification, cost, and supply-comparison contracts are implemented.
The hashed validation bundle is under `paper/validation/feature002/`. Feature 005
still owns replacement of the temporary Phase 1 proxy demand/value adapter.

Given one or more CO₂ sources, a set of candidate HnP wells (screened by Module 2),
and a CO₂ budget, jointly design the pipeline network and select which wells to connect
— minimizing total delivered cost while keeping CO₂ in dense phase everywhere. This
module answers two coupled questions simultaneously: "which wells do we treat?" and
"what infrastructure do we build to supply them?"

Runs **after** Module 2, because the candidate well set with per-well CO₂ demand comes
from the screening results.

## User Stories

### User Story 1 - Build an auditable route library (P1)

An engineer supplies one or more sources, candidate wells, the pinned terrain raster,
and exclusion zones and receives reproducible source/well/junction route segments with
terrain, slope, exclusion, and provenance audits.

**Independent test**: build the Subang-to-20-well route library twice and obtain the
same fingerprint, with no hard-zone crossing and all penalty crossings reported.

### User Story 2 - Optimize and verify a feasible network (P1)

An engineer supplies annual demands, peak flows, pre-logistics values, sources, budget,
and the route library and receives the selected wells, pipe diameters, source flows,
boosters, pressure profiles, costs, solver evidence, and continuous physics audit.

**Independent test**: solve the synthetic single/multi-source cases and the full
Jatibarang case, then verify mass balance, capacity, velocity, dense phase, and MAOP.

### User Story 3 - Compare supply and cost cases (P2)

An economist compares the optimized pipeline with a trucking baseline under the same
low/base/high accounting basis without double-counting network cost.

**Independent test**: compare both modes for the pinned annual demand and confirm
monotonic cost cases, explicit provenance, and reconciled raw versus levelized costs.

## Why MILP, Not A*

A* finds a single path across terrain — adequate for one source to one sink. But
multi-well HnP deployment is a **network design** problem: should we build a trunk line
with laterals, or separate lines? What diameter for trunk versus laterals? If we treat
5 of 20 candidate wells this year, do we size the trunk for 5 or for the eventual 20?
Does a booster on the trunk serve downstream laterals?

These are coupled combinatorial decisions (which segments exist, which wells are
connected, what diameters, where boosters go) with continuous physics constraints
(pressure drop, flow balance, dense-phase floor). That is a Mixed Integer Linear
Program. A* handles only the terrain-routing sub-problem.

## Method: Two-Layer Hybrid

**Layer 1 — Route precomputation (A*, done once offline)**

Discretize the terrain corridor from SRTM into a grid. Run A* (or Dijkstra) between
every relevant node pair: source(s) to each candidate well, and between candidate wells
(for potential lateral connections). Store each route's geometry, length, and elevation
profile. This produces a library of **candidate pipe segments** — feasible routes that
the MILP can select from.

Edges in the terrain graph carry a traversal cost combining distance, slope penalty,
and exclusion-zone penalties (rivers, settlements, protected areas). Cells exceeding
maximum buildable slope are excluded.

**Layer 2 — Network design (MILP)**

Given the precomputed candidate segments, the MILP selects which to build, at what
diameter, with boosters where needed, connecting which wells — all in one optimization.

Sets:
- S: source nodes (Subang, potentially others).
- W: candidate well nodes (from Module 2 screening, each with a CO₂ demand and an
  expected NPV contribution from Module 4 preliminary scoring).
- N: all nodes (S ∪ W ∪ candidate junction points along trunk routes).
- E: candidate pipe segments (from Layer 1 precomputation).
- D: standard API pipe diameters (e.g. 6", 8", 10", 12", 14", 16").

Decision variables:
- x[e] ∈ {0,1} — build segment e?
- d[e] ∈ D — diameter of segment e (if built).
- b[n] ∈ {0,1} — install a booster at node n?
- f[e] ≥ 0 — mass flow rate through segment e (continuous).
- P[n] ≥ 0 — pressure at node n (continuous).
- w[j] ∈ {0,1} — treat well j? (connects well selection to network topology).

Objective:
  minimize total cost =
    Σ_e x[e] · pipe_capex(d[e], length[e])
  + Σ_n b[n] · booster_capex(power[n])
  + Σ (annual OPEX: booster electricity, maintenance) discounted over project life
  − Σ_j w[j] · expected_npv_contribution[j]  (optional: co-optimize value vs. cost)

Constraints:
- Mass balance at every node: flow in = flow out (± source supply, ± well demand).
- Pressure-drop along each segment: function of flow, diameter, length, and elevation
  profile. Nonlinear (flow² / diameter⁵ dependence) — handle via piecewise-linear
  approximation for each candidate diameter to keep the problem MILP-solvable.
- Dense-phase floor: P[n] ≥ P_min_dense (~80 bar) at every node.
- Pipe pressure ceiling: P[n] ≤ MAOP(d[e]) for segments connected to node n.
- Source capacity: total flow from source s ≤ source[s].capacity.
- CO₂ budget: Σ_j w[j] · demand[j] ≤ annual CO₂ budget.
- Connectivity: w[j] = 1 → node j reachable from at least one source via built
  segments (network connectivity constraint).
- Segment activation: f[e] > 0 → x[e] = 1 (no flow through unbuilt segments).
- Flow velocity bounds: 1–5 m/s in each active segment (derived from f, d, density).

## Physics

Same hydraulics as before, but now applied per-segment within the MILP:

> dP/dL = −(f · ρ · v² / 2D) − ρ · g · sin(θ)

CO₂ density and viscosity from CoolProp at local P, T. For the MILP, the pressure-drop
relationship is precomputed for each candidate segment at each candidate diameter as a
piecewise-linear curve (flow → pressure drop), evaluated at the ground temperature of
the segment. CoolProp is called during this precomputation step, not inside the solver.

Isothermal assumption at ground temperature (~25–28 °C for West Java) for v1.
Joule–Thomson and geothermal effects are a documented refinement, not a v1 requirement.

Pipe roughness: commercial steel (~45 µm).

## Inputs

- **Candidate wells** (from Module 2): location, annual CO₂ demand, peak mass flow, expected NPV
  contribution (from Module 4 preliminary scoring), influence radius (for interference
  checking).
- **Sources**: location, outlet pressure, outlet temperature, available capacity,
  CO₂ purity.
- **Terrain**: SRTM elevation raster (GeoTIFF) for the source–sink corridor.
- **Constraints**: CO₂ budget (tonnes/year), maximum buildable slope, exclusion zones
  (GeoJSON), dense-phase minimum pressure, velocity band.
- **Cost parameters**: pipe cost per metre per inch, booster cost per kW, electricity
  rate, project lifetime, discount rate.
- **Carbon price scenario** (optional, for co-optimization): if the objective includes
  NPV contribution, the carbon price affects which wells are worth connecting.

## Outputs

- **Network topology**: which segments are built, which wells are connected, junction
  locations.
- **Segment specs**: diameter, length, route geometry for each built segment.
- **Booster stations**: locations, power per station.
- **Pressure profile**: pressure at every node and along every segment, with
  dense-phase floor and MAOP compliance. Hydraulic head decreases between boosters;
  static pressure may recover on downhill sections.
- **Well selection**: which candidate wells are treated (binary), with the rationale
  implicit in the optimization (wells dropped because connecting them was too expensive
  relative to their NPV contribution or because they'd violate the CO₂ budget).
- **Costs**: pipeline CAPEX, booster CAPEX, annual OPEX, delivered cost per tonne at
  each connected well.
- **Supply-scenario label**: which source configuration this result corresponds to.

## Solver

Pyomo as the modeling framework, with CBC (open-source, adequate for the problem size)
or Gurobi/CPLEX (if available) as the backend solver. For the piecewise-linear pressure
approximation, use Pyomo's Piecewise component or SOS2 variables. The problem size
(tens of candidate segments × a handful of diameters × ~20 candidate wells) is small
enough that CBC solves in seconds.

Fallback if the MILP is too slow: fix diameters from a reduced candidate set, solve
the reduced MILP, then check the continuous pressure solution for feasibility. Iterate
if needed.

## Dependencies

- CoolProp (CO₂ thermodynamics for pressure-drop precomputation).
- Pyomo (MILP modeling).
- CBC or another MILP solver.
- networkx (A* terrain routing in Layer 1).
- rasterio (SRTM reading).
- shapely / geopandas (exclusion-zone handling).
- NumPy.

## Done Criteria

- [x] Layer 1 produces candidate routes on real SRTM data for the Subang → Jatibarang
      corridor (and between candidate well locations if multi-well).
- [x] MILP solves and returns a feasible network with all constraints satisfied:
      dense-phase floor held, mass balance at junctions, source capacity respected,
      CO₂ budget respected.
- [x] Well selection output is consistent with the network (every selected well is
      reachable; every unselected well is disconnected).
- [x] Pressure profile per segment is physically consistent (hydraulic head decreases
      between boosters, downhill static-pressure recovery remains below MAOP, boosters
      restore pressure, and no dense-phase violation occurs).
- [x] Delivered cost per tonne at each well is traceable to a screening cost basis.
- [x] Solving time is under 30 seconds for the case-study problem size.
- [x] Handles edge cases: single-well (degenerates to a point-to-point network),
      all wells selected, rational zero selection (`no_viable_network`), contradictory
      mandatory inputs (`infeasible`), and single vs.
      multiple sources.
- [x] At least two supply scenarios (trucking baseline plus
      optimized pipeline network) produce comparable outputs for Module 4.
