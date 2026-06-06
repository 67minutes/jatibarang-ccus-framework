# Feature 006: Frontend (Demo Interface)

## Purpose

The presentation centerpiece. A Next.js + TypeScript interface that runs the framework
end-to-end interactively: input a geology and operational ranges, watch scenarios get
screened, see the CO₂ plume evolve, see the pipeline route draw itself across the
terrain, and watch the economics — and the scenario ranking — respond live as the
carbon price is dragged. Must look clean and not crash on a presentation laptop.

## Demo moments to engineer for

These are the reactions the UI must reliably produce on stage:

1. **Speed** — "screening 200 scenarios" → progress bar fills → "done, ~45 s," with
   the wall-clock time shown against an annotation of what full simulation would cost.
2. **The plume** — animated CO₂ plume spreading through the geology across
   inject → soak → produce, rendered in seconds.
3. **The pipeline** — the optimal route drawing itself across real terrain with booster
   icons appearing, and a pressure profile showing the dense-phase floor being held.
4. **The slider** — dragging carbon price from ~$2 to ~$30/tonne reshuffles the
   scenario ranking and updates NPV in real time.
5. **The comparison** — naive vs. limited-simulation vs. surrogate-enabled, same
   Jatibarang case, with the time and NPV deltas.

## Panels

- **Input (sidebar).** Geology preset selector (Jatibarang case study) or parameter
  controls (porosity range, permeability range). Operational controls (injection rate,
  soak duration, production duration, BHP, cycle count) as ranges to sweep. CO₂ source
  selector with source properties. Supply-scenario toggle. A prominent "Screen" button.
  Out-of-range inputs are visibly flagged.
- **Plume viewer (center, primary).** The 64×64 grid as a heatmap with a timeline
  scrubber across inject → soak → produce over the cycles. Toggle between pressure,
  gas saturation, z_co2, and oil saturation. A canvas/WebGL renderer is preferred over
  a geographic map library since the grid is not geographic; a custom colormap per
  field.
- **Terrain & pipeline map.** Real SRTM terrain between source and Jatibarang as a
  topographic heatmap. Source(s) and sink as markers. The optimized route animates in;
  booster stations appear as icons. A pressure-along-route chart with the dense-phase
  floor as a red line and booster rescue points marked. Supply-scenario toggle updates
  route + economics.
- **Production & storage (right, upper).** Line charts: cumulative oil, cumulative gas,
  net CO₂ stored over time. In screening mode, multiple scenarios as faint lines with
  the selected/best one highlighted.
- **Economics (right, lower).** The carbon-price slider lives here. NPV updates live as
  it moves. Break-even carbon and oil prices. Cost/revenue breakdown (CO₂ supply,
  facility, OPEX vs. oil revenue, carbon revenue). A scenario ranking table that
  reshuffles with the slider. Uncertainty band shown on NPV.

## DWSIM in the UI

Do **not** run DWSIM live. Show the facility as a static process-flow-diagram panel
whose key numbers (compression power, separator capacity, facility CAPEX/OPEX) update
from Module 3's correlations for the selected scenario. It should read as "facility
integrated" without the on-stage risk of running DWSIM.

## Behavior rules

- All data comes from the Module 005 API. No physics or economics in the frontend.
- No browser storage APIs. Hold session state in React state only.
- Resilient to slow/failed calls: show loading states, never a blank crash. Have a
  cached canned result for the Jatibarang preset so the demo works even with flaky
  conference wifi.
- Branding consistent with Intelligent Geologics (Swiss industrial / retro-tech;
  Formation Red accent; Helvetica Neue Black headings). Consider positioning the tool
  as a Fieldman CCUS-planning module rather than a standalone prototype.

## Dependencies

- Next.js 14+, TypeScript.
- A charting library (Recharts or D3) for production/economics charts.
- A canvas/WebGL grid renderer for the plume; a lightweight map renderer for terrain.
- No backend logic — API client only.

## Done Criteria

- [ ] Full flow works against the live Module 005 API on the Jatibarang preset.
- [ ] Plume animation is smooth across the full inject→soak→produce timeline.
- [ ] Pipeline route renders on real terrain with boosters and a held dense-phase floor.
- [ ] Carbon-price slider updates NPV and reshuffles the ranking in real time.
- [ ] Screening progress bar reflects real backend progress and shows wall-clock time.
- [ ] A/B/C comparison view present with time and NPV deltas.
- [ ] Out-of-range inputs and low-confidence scenarios are visibly flagged.
- [ ] A cached Jatibarang result lets the core demo run without a live backend.
- [ ] No browser-storage usage; no blank-screen failure modes.
