# Feature 003: Surface Facility Cost Model

## Purpose

Convert selected-well operational loads into surface-facility equipment, CAPEX,
annual OPEX, and auditable CO2 loss ledgers. The topology is fixed and only equipment
sizing changes, so the runtime remains a thermodynamics and cost-correlation model.
DWSIM validates the thermodynamic duties and mass balance offline and is never
launched during screening.

Feature 003 owns one dedicated injection/production skid per selected well. Feature
002 ends at the dense-phase delivery node and retains source conditioning, trunk
compression, pipeline boosters, and network costs. Portfolio totals are the exact sum
of unique well skids; no scalar well-count multiplier is permitted.

## Why a lightweight runtime is sufficient

Every scenario uses the same flowsheet: production separation -> dehydration ->
recycle-only multistage compression/intercooling -> final dense-phase cooling ->
fresh/recycle mixing -> wellhead injection pump. Nothing in the declared operational
range switches unit operations. Equipment cost scales with duty using tracked
screening power-law correlations, while duties come from CoolProp real-fluid CO2
properties at explicit pressure, temperature, and mass-flow states.

## Inputs

- One to eight unique `FacilityWellLoad` records.
- Fresh injection rate at explicit 1.01325 bar and 15 C standard conditions, plus a
  consistency-checked peak mass flow and annual injected tonnes.
- Feature 002 delivery pressure/temperature and required wellhead injection pressure.
- Peak produced gas at explicit standard conditions, produced CO2 mole fraction,
  assumed peak liquid rate, water cut, and separator conditions.
- Separate injection and production/recycle operating hours.
- Low/base/high cost case and versioned design/cost-basis identifiers.

## Outputs

- Per-equipment results for the pump, recycle compressor, intercoolers, dehydration,
  three-phase separator, and balance of plant.
- Explicit duty and installed train counts, including N+1 rotating-equipment policy.
- Reconciled per-well and portfolio CAPEX and annual OPEX.
- A mass ledger for fresh conditioning purge, recycle non-recovery, fugitives,
  atmospheric emissions, and the additional net-storage debit.
- Bulk produced-back CO2 as a separate ledger term that is not deducted again.
- Calibration status, envelope flags, input fingerprints, basis versions, and
  provenance.

## Method

- **Standard flow**: standard m3/day is converted with CoolProp density at its stated
  reference conditions. Dense delivery density is never used for this conversion.
- **Recycle compression**: only recovered produced CO2 is compressed from 10 bar to
  Feature 002 delivery pressure in three equal-ratio stages at 75% isentropic
  efficiency. Interstage cooling is to 35 C with 0.25 bar pressure drop.
- **Dense pump suction**: a final cooler returns recycle CO2 to the 27 C delivery
  temperature. Fresh and recovered streams are enthalpy-mixed, phase checked, and
  pumped once across `max(0, wellhead pressure - delivery pressure)` at 78%
  efficiency.
- **Separator**: vessel diameter/length/volume use peak gas and liquid loads,
  Souders-Brown capacity, residence times, design margins, and a target L:D ratio.
- **Costs**: each equipment CAPEX follows a versioned low/base/high power law in duty.
  Energy and maintenance are reported separately. These values are project screening
  proxies, not Indonesian vendor quotes or FEED.
- **Losses**: only fresh-stream conditioning purge and fresh fugitives are an
  additional storage debit. Recycle non-recovery and recycle fugitives remain visible
  atmospheric terms, while reservoir produced-back CO2 remains separate.

## DWSIM offline validation

The tracked DWSIM 10.0.9650 flowsheet uses the CoolProp property package, named
streams, separator and conditioning boundaries, three compressor/cooler stages, a
fresh/recycle mixer, and a wellhead pump. The eight-case resolution-IV design spans:

- 8,000-10,000 standard m3/day fresh injection;
- 80-120 bar Feature 002 delivery pressure;
- 4,500-7,300 standard m3/day peak produced gas;
- 0.525-0.795 produced CO2 mole fraction.

The saved evidence reports 8/8 convergence, compressor/pump/total-power MAPE of
`0.0000165%`, `0.0000000074%`, and `0.0000147%`, maximum individual power error of
`0.0000198%`, and zero reported DWSIM mass-balance residual.

DWSIM validates thermodynamic duties and the pure-CO2 gas-path balance. Python retains
analytic three-phase separator sizing and literature-aligned screening costs. Neither
is represented as a proprietary facility design or native DWSIM cost estimate.

## Dependencies

- Runtime: Python, Pydantic, NumPy, and CoolProp.
- Evidence generation: matplotlib.
- Offline reference refresh only: DWSIM automation assemblies and the .NET Framework
  4.7.2-compatible runner under `tools/dwsim/`.

## Done Criteria

- [x] Runtime compressor, pump, and total power match all eight converged DWSIM cases
      within the 5% MAPE and 10% pointwise gates.
- [x] Facility power, CAPEX, OPEX, separator capacity, and loss behavior pass the
      pinned monotonic sweep.
- [x] Equipment sums reconcile to wells and wells reconcile to the portfolio exactly.
- [x] Surface losses flow into Module 4 without deducting produced-back CO2 twice.
- [x] All CO2 property calculations use CoolProp real-fluid states.
- [x] Coefficients, DWSIM method, process-flow diagram, comparisons, plots, and hashes
      are tracked under `data/jatibarang/`, `docs/dwsim-validation/`, and
      `paper/validation/feature003/`.
- [x] A warmed eight-well portfolio evaluates within the 0.5-second p95 budget.
