# Feature 007: Paper Figures & Jatibarang Case Study

## Purpose

Run the actual APECX 2026 case study through the framework and generate every figure
and table the paper needs. This feature is scripted and reproducible — it is not part
of the live demo, but it consumes the same modules. Output is a set of publication
figures plus the underlying result tables.

## The case study

"An engineering team plans a CO₂ HnP-CCUS project at Jatibarang." The framework runs
the full chain on the Jatibarang-anchored geology (with uncertainty) and a defined
operational grid, across the Indonesian carbon-price scenarios, under a chosen supply
configuration (Subang as the primary CO₂ source).

## The comparison (A / B / C)

All three operate on the same geology; they differ in how the operational strategy is
chosen:

- **A — Naive / one-size-fits-all.** A single reasonable strategy (e.g. the pilot-like
  parameters) applied without screening; 1–2 confirmatory full simulations. Represents
  current Indonesian practice.
- **B — Limited-simulation optimization.** ~30–50 full MRST runs varying operational
  parameters; pick the best. Carbon economics typically not co-optimized because each
  run is expensive.
- **C — Surrogate-enabled integrated screening.** Hundreds of surrogate scenarios,
  economically scored across carbon-price scenarios, pipeline and facility coupled,
  top-K shortlisted for full validation.

The headline numbers: NPV uplift of C over B; the value of the surrogate-enabled search
(C − B in dollars); and how the optimal strategy / ranking shifts across carbon prices.

## Figures and tables to produce

1. **Surrogate validation** (brief, credibility): one-step and rollout metrics; the
   teacher-forced vs. free-rollout transition diagnostic. One table, one or two figures.
   Honest about T+10+ degradation and CO₂ mass error.
2. **Plume gallery**: representative CO₂ plume evolution (inject → soak → produce) on
   the case-study geology, surrogate vs. MRST ground truth side-by-side for a validation
   case.
3. **Screening surface**: HnP response across the operational/geology grid — e.g.
   incremental oil and CO₂ retention against key geology statistics — revealing the
   nonlinear response the surrogate has learned.
4. **Pipeline result**: the optimized Subang → Jatibarang route on terrain, the pressure
   profile with dense-phase floor and boosters, and the delivered-cost result; compared
   across supply scenarios.
5. **Facility validation**: DWSIM vs. correlation agreement across the 8 calibration
   points; the facility cost curve.
6. **Carbon-price pivot** (headline): how the top scenarios change across carbon-price
   scenarios; the cost of using the low-carbon-optimal plan when the realized price is
   high.
7. **A/B/C economics**: NPV under each carbon-price scenario for A, B, C; break-even
   carbon price and break-even oil price; the C−B value of optimization; NPV uncertainty
   bands from surrogate error propagation.
8. **Speed/feasibility**: scenarios screened and wall-clock time for B vs. C, with the
   implied full-simulation cost of matching C's coverage.

## Method

- A reproducible script/notebook that calls the Module 005 API (or the modules
  directly) on the Jatibarang preset, runs A/B/C, and writes figures to
  `paper/figures/` and tables to `paper/tables/`.
- Fixed seeds and pinned inputs so figures regenerate identically.
- For B, use real MRST runs (offline) as the limited-simulation arm; for the validation
  cases, use MRST ground truth.
- Every figure caption states honestly what is surrogate-predicted, what is MRST
  ground truth, and what is a proxy/literature-aligned assumption.

## Dependencies

- Modules 001–005.
- MRST (offline, for B and validation ground truth).
- A plotting library (matplotlib or equivalent) for publication figures.
- The DWSIM validation results from Feature 003.

## Done Criteria

- [ ] The full Jatibarang case runs reproducibly end-to-end and writes all figures and
      tables.
- [ ] A/B/C comparison produces the NPV uplift and the C−B value-of-optimization number.
- [ ] The carbon-price pivot figure clearly shows ranking changes across carbon prices.
- [ ] Surrogate limitations appear honestly in the validation figure and as NPV
      uncertainty bands in the economics figure.
- [ ] Facility correlation vs. DWSIM agreement is shown.
- [ ] Pipeline route, pressure profile, and delivered cost reproduced for the corridor.
- [ ] Every figure caption distinguishes surrogate prediction, MRST ground truth, and
      proxy/literature assumptions.
- [ ] Figures regenerate identically from pinned inputs and seeds.
