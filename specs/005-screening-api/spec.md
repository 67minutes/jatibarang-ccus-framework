# Feature 005: Screening API (Orchestrator)

## Purpose

Tie the four modules into one workflow. Accept a screening request (geology +
operational parameter grid + CO₂ source/sink + carbon-price scenarios), run the modules
in the correct order, and return ranked, fully-costed integrated scenarios. This is the
backend the frontend talks to and the engine the paper's case study runs through.

## Orchestration order

Runtime data flow is **2 → 1 → 3 → 4** (not the build/numbering order):

1. **Module 2 (surrogate)** screens every scenario in the operational grid →
   production profiles, plume frames, CO₂ inventory, and the aggregate CO₂ **demand
   profile**.
2. **Module 5 post-processing** derives per-scenario influence zones from the
   surrogate frames before economics: maximum CO₂ plume extent and pressure
   perturbation extent in physical units, plus multi-well interference checks when
   multiple injectors/producers are evaluated together.
3. **Module 1 (pipeline)** takes the demand profile (at a few representative throughput
   levels) → delivered CO₂ cost per tonne for each supply scenario. Modules 1 and 3 are
   independent of each other and may run concurrently.
4. **Module 3 (facility)** takes injection rate / produced-gas info per scenario →
   facility CAPEX/OPEX and CO₂ surface losses.
5. **Module 4 (economics)** combines everything → NPV, break-evens, ranking, across all
   carbon-price scenarios.

## Inputs

- **Geology**: either a named preset (e.g. the Jatibarang case-study geology with
  uncertainty) or explicit static maps.
- **Operational grid**: ranges/levels for injection rate, soak duration, production
  duration, BHP, cycle count to sweep (within trained ranges; out-of-range combinations
  flagged).
- **CO₂ source(s)** and **sink** (Jatibarang) for the pipeline module.
- **Supply scenarios** to evaluate (trucking baseline, pipeline, multi-source hub).
- **Carbon-price scenarios** and economic parameters for Module 4.
- **CO₂ budget constraint** (optional): max tonnes/year, for any portfolio/shortlist
  logic.
- **Multi-well configuration** (optional): well coordinates, spacing, timing groups,
  and non-interference policy for configurations that screen more than one well at a
  time.

## Outputs

- **Ranked scenario list**: each entry carries its operational parameters, production
  and storage outcomes, pipeline design + delivered cost, facility costs, and NPV under
  each carbon-price scenario, plus confidence/extrapolation flags.
- **Influence-zone metrics per scenario**: maximum CO₂ plume extent and maximum
  pressure-perturbation extent reported in physical units, derived from surrogate
  spatial outputs before economics.
- **Multi-well interference report**: for multi-well configurations, an `N x N`
  boolean matrix where entry `(i, j)` indicates whether well `i`'s influence zone
  overlaps well `j`'s influence zone; any pair that fails the non-interference check is
  flagged with a recommendation for that pair: increase spacing, stagger timing, or
  validate with full simulation.
- **Best-by-carbon-price**: the top scenario(s) for each carbon-price scenario,
  highlighting where the ranking changes.
- **Shortlist for full validation**: top-K scenarios recommended for MRST + detailed
  DWSIM validation.
- **Run metadata**: number of scenarios screened, wall-clock time (for the
  speed-comparison story).

## Behavior rules

- Stateless request/response; long screening runs may stream progress (for the UI
  progress bar) but must also work as a single synchronous call for scripted/paper use.
- Every scenario carries its provenance: which module produced which number, and all
  flags. Nothing is silently dropped or smoothed.
- Influence-radius and interference outputs are first-class scenario metadata. They
  must propagate into rankings, shortlist decisions, and validation recommendations;
  non-interference failures are never hidden behind favorable NPV.
- Caching: identical surrogate inputs should not be re-run within a request (the grid
  may repeat geology across operational variations).
- The orchestrator does not contain physics or economics logic itself — it only
  sequences the modules and assembles results. All domain logic lives in 1–4.

## Endpoints

- `POST /screen` — full screening run → ranked scenarios + best-by-carbon-price +
  shortlist + metadata.
- `POST /screen/stream` — same, with progress events for the UI.
- `GET /presets` — available geology presets and supply scenarios.
- `GET /health` — service + surrogate checkpoint status.

## Dependencies

- FastAPI.
- Modules 001–004 as importable packages.
- Pydantic (shared interface models — define these first, before implementing 1–4).

## Done Criteria

- [ ] `POST /screen` runs the full 2→1→3→4 chain on the Jatibarang preset and returns
      ranked scenarios with NPV under all carbon-price scenarios.
- [ ] Ordering enforced: Module 1 receives a real demand profile from Module 2, not a
      placeholder.
- [ ] Best-by-carbon-price correctly surfaces ranking changes across carbon prices.
- [ ] Shortlist (top-K) is produced for downstream validation.
- [ ] Each scenario includes physical-unit plume and pressure influence radii derived
      from surrogate output frames.
- [ ] Multi-well screens return an `N x N` interference matrix, pair-level
      non-interference failure flags, and pair-level recommendations to increase
      spacing, stagger timing, or validate with full simulation.
- [ ] A few-hundred-scenario screen completes in minutes; metadata reports the count
      and wall-clock time.
- [ ] Extrapolation and low-confidence flags propagate from modules to the final
      response.
- [ ] Streaming endpoint emits progress suitable for a UI progress bar.
