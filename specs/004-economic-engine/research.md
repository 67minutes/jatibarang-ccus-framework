# Feature 004 Research Decisions

## Time and currency basis

**Decision**: use year 0 for CAPEX and end-of-year discounting for recurring cash
flows. Annualize supplied physical steps by overlap with calendar-year boundaries. Do
not repeat a campaign or invent a production tail. All values use an explicitly named
constant-dollar basis; a mismatched source cost year requires a documented factor.

## Supply and facility ownership

**Decision**: use discriminated flat-delivered, raw-pipeline, and raw-trucking inputs.
Final pipeline economics consume raw CAPEX, maintenance, booster energy, and commodity
supply. Levelized cost and lifecycle allocations are display-only. Facility CAPEX is
booked once; equipment energy is allocated by modeled stage hours and maintenance by
active asset year.

## Storage and produced gas

**Decision**: inventory-derived produced-back CO2 is primary. A production-stream
cross-check uses gross standard gas, CO2 fraction, and an explicit real-fluid standard
density. Net storage also subtracts Feature 003 surface loss. A divergence above 15%
of cumulative injection is low confidence.

Hydrocarbon gas revenue excludes the CO2 fraction and uses a provenance-carrying
heating value. The default 0.0353 MMBtu/std m3 is a screening assumption, not a
surrogate output.

## Uncertainty

**Decision**: return correlated deterministic low/base/high trajectories. Apply one
direction consistently across the full time series and widen storage by both the
inventory error bound and the production-stream cross-check. Do not assign
probabilities because the saved surrogate evidence does not establish a distribution.

## Fiscal sensitivity

**Decision**: implement pre-tax, simplified cost-recovery, and simplified gross-split
cash flows. Cost recovery uses a configurable ceiling and carryforward pool; gross
split applies government take to gross hydrocarbon revenue. Carbon-revenue treatment
and a switchable emissions tax are separate. Every post-fiscal output is labeled
parametric screening sensitivity, not exact Indonesian PSC accounting.

## Market scenarios

**Decision**: derive the current case from the latest complete IDXCarbon monthly
all-market value/volume and a pinned Bank Indonesia JISDOR observation. Keep 20, 40,
and 50 USD/tCO2e as explicit domestic-maturing, Article-6/JCM, and aspirational
sensitivities rather than observed prices.

