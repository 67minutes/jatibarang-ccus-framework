# Logistics Mode-Choice (Pipeline vs Trucking) Design

**Date:** 2026-07-19
**Status:** approved for planning; execution starts on owner's go signal
**Plan:** `docs/superpowers/plans/2026-07-19-logistics-mode-choice.md`
**Paper plan of record:** Obsidian vault `jatibarangccus`, note `04 APECX Paper Structure and Main Figures`

## 1. Problem

The production screening returns `no_viable_network` at every carbon price, including a
$500/t QA case. Root cause (verified 2026-07-19 by single-variable MILP experiments;
recorded in project memory `no-viable-network-root-cause`):

1. Huff-n-puff wells inject ~17 t/day (9,000 m³/day at surface conditions); field total
   peak is 3.9 kg/s, annual ~30 kt/yr.
2. The MILP's minimum-velocity floor (`min_velocity_m_s: 1.0`, dense phase) makes the
   smallest catalog diameter (6″) require ≥ 15.95 kg/s on every active arc
   (`peak_activation_lower`, `pipeline.py:477`). Per-well laterals carry 0.195 kg/s.
   No topology or well count fixes the lateral; per-well rate is capped by the published
   2,075 psi fracture pressure. Pipelines-to-wellhead are physically inadmissible at
   pilot scale — this is correct engineering, not a bug.
3. The orchestrator treats pipeline-`accepted` as the only development path
   (`orchestrator.py:1039–1057`): on any other status it emits a route preview and a
   warning. Trucking can never constitute development, even though the submitted
   abstract's own economics assumed trucked supply.
4. The zero-selection reason string `all_wells_negative_after_logistics` mislabels a
   constraint-driven zero as an economic verdict.

Every well is worth +$15.6–17.2M pre-logistics; trucking PV cost is ~$0.3–0.5M/well.
A trucking-capable selection would develop all 20 wells and unlock Figures 4/5/7/8
inputs. Without it, Arm C re-solves produce degenerate zeros and the paper's headline
receipts (vault Moves 6–7) are unbuildable.

## 2. Decision

Extend Feature 002's MILP into a **mode-choice logistics optimizer**: for each candidate
well it decides selection *and* supply mode (pipeline network arc vs per-well trucking),
maximizing net value. This matches the abstract's own language ("MILP Logistics
Optimizer"; "jointly selects wells and designs transport infrastructure") — the pipeline
formulation, A* corridors, and CoolProp hydraulic admissibility all remain and are what
*prove* trucking dominance at pilot scale. Plus:

- honest zero-selection provenance (`below_minimum_hydraulic_flow` and per-well
  `hydraulically_unreachable` when the velocity floor, not economics, forces the zero);
- a throughput **crossover table generator** (trucking vs pipeline-direct vs hybrid
  trunk+truck) for Figure 5(c) and the paper's scaling story;
- orchestrator/schema/frontend plumbing so trucking-supplied development plans flow
  through facility sizing, economics, memo, and UI with per-well mode provenance.

Explicit non-goals (guard against tuning assumptions to force a headline):

- Do **not** change `min_velocity_m_s`, the diameter catalog, or any hydraulic
  assumption. The 1 m/s dense-phase floor stays.
- Do **not** regenerate MRST or retrain the surrogate. All schedules stay inside
  `TRAINED_RANGES`.
- Do **not** build a transload-hub node type in the MILP. The hybrid is evaluated in
  the crossover sweep only (cost-curve level); a hub node in the network model is
  future work.
- Do **not** stage `pipeline_cost_crossover.csv` into the Feature 007 bundle here;
  bundle staging happens during the paper execution run under its own gates.

## 3. MILP formulation change (Feature 002)

New per-well binaries alongside existing `z` (selected):

- `p[w]` — pipeline-served; `t[w]` — trucked; constraint `z[w] == p[w] + t[w]`
  (binary `z` makes the modes mutually exclusive).
- Peak/annual flow balances at demand nodes switch from `z[w]` to `p[w]` — only
  pipeline-served demand draws network flow.
- `t[w]` is fixed to 0 when the demand carries no trucking distance
  (back-compat: every existing caller and test is bit-identical).
- Mandatory wells fix `z=1` as today (either mode may satisfy them).
- Objective (max_net_value):
  `Σ value_w·z_w − network_lifecycle − commodity(z) − Σ trucking_cost_w·t_w`
  where `trucking_cost_w = (loading + liquefaction + reconditioning +
  usd_per_tonne_km · distance_w) · annual_tonnes_w · pv_factor`.
  The CO₂ commodity price stays in `commodity_expr` over `z` (no double count).
  `min_lifecycle_cost` mode adds the trucking term symmetrically.

Contract changes (all additive):

- `PipelineWellDemand.trucking_distance_km: float | None = None` (per-well one-way km,
  road-network or haversine×1.4 provenance decided upstream).
- `PipelineDesignResult.supply_mode_by_well: dict[str, "pipeline"|"trucking"]`,
  `PipelineDesignResult.trucking_lifecycle_cost_usd: float`.
- `WellSelectionDecision.supply_mode: "pipeline"|"trucking"|None`, and reason literal
  gains `"hydraulically_unreachable"`.
- `domain_status == "accepted"` whenever any well is selected — including all-trucked
  plans with zero built segments. Post-solve hydraulic verification passes vacuously
  when no segments are built. Allocations (`per_well_allocated_cost_usd`) include
  trucked wells at their trucking PV; `delivered_cost_usd_per_tonne` for a trucked well
  is commodity supply + per-tonne trucking logistics.

Honest zero-selection: when nothing is selected, the audit reason is
`below_minimum_hydraulic_flow` if **every** well's peak flow is below the minimum
admissible flow of every incident arc/diameter (computed from the hydraulic curves)
**and** that well had no trucking option; otherwise `all_wells_negative_after_logistics`
as today. Feature 002's tracked rational-zero validation case has no trucking distances
and keeps its `no_viable_network` outcome unchanged.

## 4. Orchestrator changes (Feature 005)

- After the route library is built, call `compute_trucking_legs` once and inject each
  candidate's `distance_km` into that candidate's `PipelineWellDemand`
  (`model_copy(update=...)`). Road-network distances when a road graph is linked;
  the existing haversine×1.4 fallback otherwise (provenance strings unchanged and
  verbatim: `osm_road_network:<id>` / `greatcircle_detour_estimate`).
- The accepted branch now runs for trucking-inclusive selections. Facility sizing uses
  the existing 80 bar delivery-pressure default for trucked wells. Economics consume
  the pipeline result's allocations, which now cover trucked wells.
- `CarbonPricePlan.logistics_mode: "pipeline"|"trucking"|"hybrid"|"none"` (additive):
  derived from the mode map ("hybrid" = both modes present in one plan; "none" = no
  selection).
- Trucking route legs are computed for the *selected trucked wells* on accepted plans
  (so the viewport draws road-following dashes for developments, not only previews).
  The non-accepted preview path stays as is.
- Flag policy: `no_viable_network` warning only when nothing is selected. A new
  info-severity flag `pipeline_hydraulically_inadmissible` is attached when trucked
  wells exist and the audit shows the velocity floor excluded pipelines.
- `STUDY_MEMO_VERSION` stays **4**; all memo/API fields are optional/additive.

## 5. Crossover sweep (Figure 5c input)

New pure module `infrastructure/crossover.py`: given a cost case, trunk length (km),
last-mile distance (km), per-well annual tonnes, and an annual-throughput grid, emit
rows `(annual_tonnes, mode, levelized_usd_per_tonne, hydraulically_admissible,
cheapest_admissible_diameter_in | None)` for three modes:

- `trucking` — per-tonne logistics at the full source→well road distance;
- `pipeline_direct` — trunk levelized `capex·(1 + maint·pv) / (tonnes·pv)` at the
  cheapest diameter whose `[minimum_flow, maximum_flow]` admits the
  continuous-equivalent flow (`annual_tonnes·1000 / (365·86400)` kg/s); when no
  diameter admits it, cost is reported at 6″ with `admissible=False`;
- `hybrid_trunk_truck` — trunk levelized + last-mile trucking logistics
  (loading + liquefaction + reconditioning + distance at `lastmile_km`).

Booster costs are deliberately excluded (documented screening lower bound that favors
pipelines — the trucking-wins-at-pilot-scale conclusion is then conservative).
Commodity supply is excluded from all three curves (pure transport comparison, same
basis as `levelized_transport_usd_per_tonne`). A `main()` CLI writes the table as CSV
to `output/crossover/pipeline_cost_crossover.csv` by default.

## 6. Frontend (minimal, additive)

- `api/types.ts`: `supply_mode_by_well`, `logistics_mode` on the plan; decision
  `supply_mode`.
- Inspector: when the selected result's plan has trucked development wells, the
  provenance line reads exactly: "Supplied by road transport from the source." —
  alongside the existing road-provenance copy rules (never say "graph", "PBF", or
  "OSM extract" in UI copy).
- Scene: selected wells whose mode is trucking render the dashed trucking route from
  the plan's trucking legs on **accepted** plans (today dashes only appear when the
  network is not accepted).

## 7. Verification

- Backend: `python -m pytest tests -q` green after every task; new unit tests pin
  (a) legacy bit-compatibility with no trucking distances, (b) trucked selection at
  pilot-scale numbers, (c) pipeline still wins at high flow / short distance,
  (d) honest reason strings, (e) crossover admissibility boundaries.
- Frontend: `npm test -- --run && npx tsc -b` green; scene/Inspector tests extended.
- End-to-end: re-run the 20-well workflow smoke after landing; expected outcome is an
  accepted trucking development at all four carbon prices with positive economics.
  Record whether the carbon-price pivot materializes (vault Move 6 risk flag) — the
  result is reported either way; assumptions are never tuned to force it.

## 8. Paper/vault alignment

The Obsidian paper plan (`04 APECX Paper Structure and Main Figures`) is edited in the
same pre-execution batch: Fig 5/7 panel reframes, the scaling/crossover co-headline,
the pivot-risk flag, Move 4 module wording, claim guards for the crossover, and a new
execution-map step 0 (this branch + 20-well re-run gate before any bank launch).

## Implementation record (2026-07-19)

Tasks 1-9 of this plan landed on branch `008-blank-slate-workbench` as nine commits,
HEAD at `f28f423`:

- **`f6ac27d`** feat(contracts): additive mode-choice fields for logistics MILP —
  Task 1. `PipelineWellDemand.trucking_distance_km`, `PipelineDesignResult
  .supply_mode_by_well` / `.trucking_lifecycle_cost_usd`, and
  `WellSelectionDecision.supply_mode` land as optional/additive contract fields, plus
  the `hydraulically_unreachable` reason literal.
- **`40dc814`** feat(costs): shared trucking logistics per-tonne helper — Task 2.
  `trucking_logistics_usd_per_tonne(case, distance_km)` factored out so the MILP
  objective and the crossover sweep (Task 8) share one costed formula.
- **`3eaf092`** feat(milp): joint pipeline-vs-trucking mode choice per well — Task 3.
  Adds the `p[w]`/`t[w]` binary pair (`z[w] == p[w] + t[w]`), switches peak/annual
  flow balances to `p[w]`, and adds the trucking cost term to the objective. `t[w]`
  is fixed to `0` when a well carries no trucking distance, keeping every
  pipeline-only caller and fixture bit-identical.
- **`ee24570`** feat(milp): distinguish hydraulic-floor zeros from economic zeros —
  Task 4. Adds `below_minimum_hydraulic_flow` / per-well `hydraulically_unreachable`
  zero-selection provenance, computed from the hydraulic curves' minimum admissible
  flow per incident arc/diameter, while leaving the tracked rational-zero validation
  case's `no_viable_network` outcome unchanged (it has no trucking distances).
- **`b07e2e5`** feat(milp): trucked wells carry allocations, delivered cost, and mode
  provenance — Task 5. Post-solve assembly extends `per_well_allocated_cost_usd` and
  `delivered_cost_usd_per_tonne` to trucked wells, and sets `domain_status ==
  "accepted"` whenever any well is selected, including all-trucked plans with zero
  built segments (post-solve hydraulic verification passes vacuously when no
  segments are built).
- **`ba8756a`** feat(screening): trucking-supplied selections are development plans —
  Task 6. Orchestrator injects per-candidate road (or haversine-fallback) trucking
  distances into each `PipelineWellDemand`, runs the accepted branch for
  trucking-inclusive selections, and adds `CarbonPricePlan.logistics_mode` plus the
  info-severity `pipeline_hydraulically_inadmissible` flag.
- **`3af8bfa`** feat(api): expose logistics mode in screening contract — Task 7. Adds
  `logistics_mode`, `supply_mode_by_well`, and `trucking_lifecycle_cost_usd` to the
  OpenAPI contract and pins a serialization regression test.
- **`2a952d2`** feat(crossover): trucking/pipeline/hybrid throughput sweep for fig 5c
  — Task 8. New pure module `infrastructure/crossover.py` emitting the three-mode
  levelized-cost sweep described in §5, with a CLI writing
  `output/crossover/pipeline_cost_crossover.csv`.
- **`f28f423`** feat(frontend): trucked development routes and supply-mode
  provenance — Task 9. `api/types.ts` gains optional `supply_mode_by_well` /
  `logistics_mode`; `scene.ts` draws road-following dashes for selected trucking
  wells on **accepted** plans (previously dashes only appeared on non-accepted
  previews); `Inspector.tsx` renders the verbatim line "Supplied by road transport
  from the source." for trucking-mode development.

### Verification (this task, Task 10 Steps 1/3/4)

- Backend: `python -m pytest tests -q` — full results recorded in the Task 10 report
  (`.superpowers/sdd/task-10-report.md`).
- Frontend: `npm test -- --run`, `npx tsc -b`, `npm run build` — full results recorded
  in the same report.
- Step 2 (starting the app, opening the saved 20-well study, and confirming the
  carbon-price pivot observation for vault Move 6) is **pending** — it is being run
  separately by the controller and is out of scope for this task.

### Accepted deviations from the plan

1. **Task 3 populated `supply_mode_by_well` and `trucking_lifecycle_cost_usd` earlier
   than the plan assumed.** §3/§4 of this design and the plan's Task 5 framing expect
   per-well mode provenance and the trucking lifecycle cost to be finalized during the
   post-solve assembly step (Task 5, `b07e2e5`). In practice, commit `3eaf092` (Task 3)
   already computes and returns both fields directly from the MILP solution ( `
   supply_mode_by_well = {well: ("trucking" if well in trucked else "pipeline") ...}`,
   `trucking_lifecycle_cost_usd = sum(trucking_cost_by_well[well] for well in
   trucked)`), because the mode assignment is already fully known once the binaries
   are solved. Task 5 then extends the *other* post-solve fields
   (`per_well_allocated_cost_usd`, `delivered_cost_usd_per_tonne`) to trucked wells.
   This is a sequencing difference only; the final field set and semantics match the
   design unchanged.
2. **Tasks 6, 7, and 9 bundle pre-existing prior-session Codex work.** Commits
   `ba8756a`, `3af8bfa`, and `f28f423` each disclose in their own commit messages that
   they carry substantial uncommitted prior-session (earth-view/OSM routing)
   scaffolding that shared the same files as this plan's changes: the
   prediction-cache path and `TruckingRoutePreview` class (`ba8756a`), a pre-existing
   uncommitted preset-design test and import (`3af8bfa`), and a large
   Inspector.tsx reservoir-assignment/SHA-display rework plus schedule/
   `TruckingRoutePreview` additions in `types.ts`/`scene.ts` (`f28f423`). None of that
   bundled content is this plan's work; each commit message identifies exactly which
   hunks are Task 6/7/9 versus carried-over WIP, and reconciliation with the broader
   Codex working tree remains open (see `git status` on this branch, which still shows
   a large set of unrelated modified/untracked files as of 2026-07-19).
