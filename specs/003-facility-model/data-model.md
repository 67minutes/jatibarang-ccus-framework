# Feature 003 Data Model

## FacilityPortfolioRequest

- `contract_type`: fixed `facility_portfolio_request`
- `portfolio_id`: non-empty run-local identifier
- `ownership_basis`: fixed `dedicated_well_pad_skids` for v1
- `cost_case`: `low`, `base`, or `high`
- `design_basis_version` and `cost_basis_version`: required pinned identifiers
- `wells`: 1-8 unique `FacilityWellLoad` records
- `provenance`: upstream module, scenario, assumptions, and source classifications

Validation rejects duplicate wells, unsupported ownership modes, inconsistent totals,
non-finite values, missing unit references, delivery below the declared dense-phase
boundary, and a wellhead pressure above the configured screening pressure cap.

## FacilityWellLoad

- well/scenario identity
- standard injection rate plus reference pressure and temperature
- fresh CO2 peak kg/s and annual injected tonnes
- Feature 002 delivery pressure and temperature at the well
- required wellhead injection pressure
- peak produced gas at explicit standard conditions and CO2 mole fraction
- peak liquid rate, water cut, separator pressure and temperature
- injection and production/recycle operating hours per year
- recycle enabled flag and recovery fraction
- provenance for predicted, pipeline-derived, and assumed values

The standard-volume-to-mass consistency check must pass within a configured tolerance;
peak kg/s, not dense-phase volume inferred from standard m3/day, sizes equipment.

## FacilityDesignBasis

- compressor stages and isentropic efficiency
- interstage cooler outlet temperature, final dense-phase recycle-cooler temperature,
  and pressure-drop allowance
- dense-pump efficiency and phase margin
- dehydration outlet-water target and package sizing coefficient
- separator Souders-Brown factor, residence times, L:D range, and design margin
- recycle recovery and purge basis
- critical-equipment train capacity and installed/duty/spare policy
- annual availability and maintenance basis
- units, source class, source locator, version, and checksum

## FacilityCostBasis

- low/base/high cases in constant-year USD
- per-equipment reference duty/size, reference cost, exponent, installation factor,
  escalation, location treatment, maintenance, and electricity price
- equation and unit string for every coefficient
- bibliography/URL, source year, access date, and screening-proxy status
- file version and checksum

## EquipmentItemResult

- equipment ID, well owner, type, and ownership scope
- inlet/outlet state and rated duty/capacity
- duty, installed, and spare train counts
- power/heat duty and operating hours
- purchased, installed, and annual energy/maintenance costs
- calculation method, coefficient version, calibration status, and provenance

Equipment types include injection pump, recycle compressor stage, intercooler,
dehydration package, three-phase separator, and balance of plant.

## SurfaceLossLedger

- fresh/recycle mass handled
- conditioning purge tonnes and fraction
- recycle non-recovery tonnes and fraction
- fugitive tonnes and fraction
- total facility surface loss tonnes and fraction
- bulk produced-back CO2 reported separately
- source-stream IDs and a reconciliation residual

The total surface loss excludes bulk produced-back CO2 so Feature 004 cannot deduct
the same mass twice.

## FacilityWellResult

- well ID and input fingerprint
- rated pump, recycle-compressor, cooler, dehydration, and separator specifications
- equipment item list
- CAPEX, annual OPEX, energy, and loss totals
- calibration-envelope flags and provenance
- reconciliation proving equipment components sum once

## FacilityPortfolioResult

- `contract_type`: fixed `facility_portfolio_result`
- portfolio, design-basis, cost-basis, and calibration versions
- ordered per-well results
- total installed CAPEX, annual OPEX, energy, and surface loss
- per-well allocations consumed by Feature 004
- exact ownership and loss reconciliations
- validation status: `validated`, `outside_calibration_envelope`, or `unvalidated`
- DWSIM evidence manifest reference and complete provenance

State transitions:

`validated_request -> physical_duties -> equipment_sized -> costs_and_losses -> reconciled -> accepted`

A property failure ends as `thermodynamic_state_invalid`; a phase-boundary violation as
`dense_phase_boundary_failed`; an accounting failure as `reconciliation_failed`.
Inputs outside the eight-case envelope may still evaluate, but end as
`outside_calibration_envelope` and cannot inherit the validated error statement.

## FacilityValidationCase and Record

- case ID and four-factor design levels
- all fixed pressure, temperature, efficiency, and recovery assumptions
- DWSIM model/version/hash and CoolProp package/version
- convergence status and stream mass-balance residual
- DWSIM compressor/pump/cooler/separator outputs
- runtime outputs, absolute/relative errors, and gate verdicts
- cost values derived from each duty source, labeled by method
- artifact hashes and generation timestamp
