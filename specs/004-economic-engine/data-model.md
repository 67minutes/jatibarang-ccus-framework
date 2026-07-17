# Feature 004 Data Model

## EconomicBatchRequest

- Versioned economic assumptions and provenance
- 1-256 unique portfolio inputs
- At least four unique carbon-price scenarios
- One or more unique fiscal cases, including pre-tax for the default basis

## PortfolioEconomicInput

- Portfolio ID, project life, and unique annual physical periods
- Raw facility allocation and one discriminated supply-cost basis
- Annual uncertainty bounds and confidence reasons
- Optional terminal cash flow; no implicit campaign repeat

## AnnualEconomicPeriod

- Year, injection and production operating hours
- Oil and gross gas production at standard conditions
- Produced-gas CO2 fraction and explicit standard CO2 density
- Injected CO2, primary inventory-derived produced-back CO2, surface loss
- Workover count and explicitly taxable atmospheric emissions

## SupplyCostBasis

- `flat_delivered`: one all-inclusive variable USD/tonne value for preliminary scoring
- `pipeline_raw`: pipeline/booster CAPEX, annual maintenance/energy vectors, commodity USD/tonne
- `trucking_raw`: loading, liquefaction, reconditioning, distance, and commodity USD/tonne

These variants are mutually exclusive. No variant accepts levelized fields.

## EconomicScenarioResult

- Portfolio, carbon-price, and fiscal-case identity
- Annual component and discounted-cash-flow rows
- Primary/cross-check storage totals and divergence status
- Pre-tax and post-fiscal NPV; deterministic NPV low/base/high
- IRR, discounted payback, break-even carbon, and break-even oil values with statuses
- Cost/revenue reconciliation, qualification flags, and provenance

## EconomicBatchResult

- All scenario results in deterministic portfolio/price/fiscal order
- Base, downside, and upside rankings with stability flag
- Runtime, accounting verdict, basis version, and provenance

