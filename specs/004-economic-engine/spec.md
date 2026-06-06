# Feature 004: Economic Engine

## Purpose

Combine the physical outputs of Modules 1–3 into a full economic evaluation of a CO₂
HnP-CCUS scenario: oil and gas revenue, carbon-credit revenue, CO₂ supply cost,
facility cost, operating cost, and the Indonesian fiscal regime — producing NPV, IRR,
break-even carbon price, and break-even oil price. This is the terminal module; all
data flows converge here. The headline output is how NPV and scenario ranking shift
across carbon-price scenarios.

## Inputs

- **Production profiles** (from Module 2): per-timestep and cumulative oil and gas.
- **CO₂ inventory** (from Module 2): total CO₂ in reservoir per timestep; produced-back
  CO₂ derived from this and the produced-gas stream.
- **CO₂ surface losses** (from Module 3): fraction lost in surface handling.
- **Delivered CO₂ cost** (from Module 1): $/tonne at wellhead for the chosen supply
  scenario.
- **Facility CAPEX / OPEX** (from Module 3).
- **Operating parameters**: lifting cost per barrel, workover cost per cycle, MRV cost
  per tonne of claimed storage, discount rate, project lifetime.
- **Price scenarios**: oil price (ICP-linked, several levels), gas price, and a set of
  carbon-price scenarios (see below).
- **Fiscal parameters**: PSC structure (cost-recovery vs. gross-split), government take
  %, tax treatment of carbon revenue, certification haircut on claimed storage.

## Net CO₂ stored — handling and known limitation

Net CO₂ stored = CO₂ injected − CO₂ produced back − CO₂ surface losses.

Two ways to obtain "produced back," used together as a cross-check:

1. **Inventory mass balance**: from the surrogate's `z_co2` × `gas_sat` × pore-volume
   integral, track reservoir CO₂ over time; produced-back follows from the balance.
2. **Production-stream estimate**: partition the surrogate's `delta_gas` into
   hydrocarbon gas and CO₂ using produced-stream composition.

The surrogate currently predicts `delta_gas` but does **not** output a dedicated
produced-CO₂ rate. This is a known gap. v1 uses the inventory mass balance as primary,
the production-stream split as a cross-check, and reports the divergence. The
surrogate's documented `z_co2` mass error at end-of-sequence bounds this calculation —
that bound must be carried into the NPV as an uncertainty band, not hidden. If the two
estimates diverge beyond a set threshold, flag the scenario as low-confidence and
recommend full-simulation validation.

## Carbon-price scenarios (Indonesia-specific)

Evaluate every scenario under, at minimum:

- **Current IDX Carbon** (~$2–4/tonne) — effectively negligible credit revenue.
- **Maturing domestic market** (~$15–20/tonne).
- **JCM / Article-6 bilateral** (~$30–50/tonne) — Japan bilateral pricing.
- **Aspirational policy target** ($50+/tonne).

Carbon-credit revenue = net CO₂ stored × carbon price × certification haircut. The
haircut (e.g. 0.8–0.9) reflects that not all claimed storage is certifiable under
MEMR Reg. 2/2023 and SKK Migas PTK-070/2024 MRV requirements. The carbon tax itself
is legislated but not yet implemented in Indonesia — model it as a parameter that can
be switched on, defaulting off, with a note in the documentation.

## Fiscal regime

Model at two levels:

- **Pre-tax NPV** for the clean A/B/C comparison.
- **Post-fiscal sensitivity**: government take as an adjustable parameter. Under
  cost-recovery PSC, CO₂ procurement and injection costs are recoverable (reducing
  government take and effectively subsidising EOR); under gross-split there is no cost
  recovery but split adjustments for enhanced recovery / carbon reduction may apply.
  Keep this parametric (a take % slider), not a replica of exact PSC terms.

## Outputs

- **NPV** per scenario per carbon-price scenario.
- **IRR**, payback period.
- **Break-even carbon price**: the price at which the project NPV reaches zero given
  oil revenue — "at what carbon price is HnP-CCUS self-funding."
- **Break-even oil price**: the oil price at which the project pays for itself given a
  fixed carbon price — "at what oil price does HnP pay for itself without credits."
- **Cost/revenue breakdown**: oil revenue, gas revenue, carbon revenue, CO₂ supply
  cost, facility CAPEX/OPEX, lifting, MRV — for the UI breakdown chart.
- **Uncertainty band** on NPV reflecting surrogate mass-error and cumulative-production
  error propagation.

## Method

- All calculations vectorized in NumPy so an entire batch of screened scenarios × all
  carbon-price scenarios is evaluated at once.
- Discounted cash flow over the project lifetime; cycle-level cash flows aggregated to
  field level.
- Incremental framing where a baseline is available; otherwise compare strategies on
  the same geology (see Module 7 / paper specs for the A/B/C comparison framing — the
  economics engine itself just scores whatever scenarios it is given).

## Dependencies

- NumPy.
- Pydantic (typed inputs/outputs).

## Done Criteria

- [ ] NPV, IRR, payback, break-even carbon price, break-even oil price all computed.
- [ ] Net CO₂ stored computed via mass balance with the production-stream cross-check
      and divergence reported.
- [ ] Surrogate uncertainty propagated into an NPV band (not a bare point estimate).
- [ ] All four carbon-price scenarios evaluated; ranking can differ across them.
- [ ] Fiscal regime adjustable (take %, PSC mode); pre-tax and post-fiscal both
      available.
- [ ] Cost/revenue breakdown matches the sum of components (internal consistency test).
- [ ] Batch evaluation of ≥200 scenarios × 4 carbon scenarios is effectively instant.
