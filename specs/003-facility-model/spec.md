# Feature 003: Surface Facility Cost Model

## Purpose

Convert a scenario's operational requirements (injection rate, injection pressure,
produced gas rate and CO₂ fraction) into surface facility CAPEX, annual OPEX, and CO₂
surface losses. The facility topology is fixed across scenarios — only equipment
**sizing** changes — so this is a thermodynamics + cost-correlation model, not a
process simulator. DWSIM is used **offline** to validate the correlations; it does not
run at screening time.

## Why a lightweight model is sufficient

Every scenario uses the same flowsheet: CO₂ receiving → dehydration → multi-stage
compression with intercooling → supercritical injection pump → production three-phase
separator → optional CO₂ recycle. Nothing in the operational range switches the unit
operations; it only resizes them. Equipment cost scales with duty by well-established
power-law (six-tenths-rule-style) correlations, and the duties themselves come from
CO₂ thermodynamics at known pressures, temperatures, and flow rates.

## Inputs

- **Injection rate** and **injection pressure** (from Module 2 / the scenario), with
  CO₂ storage-side pressure and temperature (from Module 1 source / delivery
  conditions).
- **Peak produced gas rate** and **produced CO₂ fraction** (from Module 2 production
  output and the z_co2 inventory).
- **Number of wells treated simultaneously** (scales the whole facility).
- **Cost/efficiency parameters**: compressor isentropic efficiency, number of
  compression stages, pump efficiency, electricity rate, operating hours/year,
  cost-correlation pre-factors and exponents (calibrated from DWSIM, see below).

## Outputs

- **Facility CAPEX**: compression train + injection pump + separator + balance-of-plant.
- **Facility OPEX (annual)**: dominated by compressor/pump electricity; plus
  maintenance.
- **CO₂ surface losses**: fraction of handled CO₂ lost to venting/flaring during
  conditioning and separation, as a function of handling steps and pressure stages.
  Feeds the net-storage calculation in Module 4.
- **Derived facility specs** (for display): total compression power, separator
  capacity, number of compression stages.

## Method

- **Compression duty**: stage-by-stage real-gas compression from storage to injection
  pressure, with intercooling between stages. Work per stage from CoolProp enthalpy
  differences using isentropic efficiency; sum across stages. CO₂ near its critical
  point makes real-gas treatment mandatory.
- **Injection pump**: for supercritical injection (Jatibarang injects supercritical at
  ~2,000 psi, ~91 °C reservoir), pump work ≈ volumetric flow × ΔP ÷ efficiency, with
  density from CoolProp.
- **Separator sizing**: vessel sized to peak gas rate via standard gas-velocity /
  L:D-ratio correlations.
- **Cost correlations**: each equipment item's CAPEX follows a power-law in its duty
  (e.g. CAPEX ∝ duty^~0.6). Pre-factors and exponents are calibrated against the DWSIM
  reference runs and standard cost references (Turton; Towler & Sinnott; Peters &
  Timmerhaus), adjusted toward Indonesian equipment costs where data allows.

## DWSIM offline validation (paper material, not runtime)

- Build a detailed DWSIM process model of the Jatibarang HnP surface facility
  (multi-stage compression + intercooling, supercritical injection pump, three-phase
  production separator, CO₂ recycle). Acquisition/automation may use the DWSIM MCP.
- Run the DWSIM model at ~8 throughput levels spanning the operational range; record
  compression duty, equipment sizing, heat duties, and CO₂ losses.
- Fit the runtime correlations to these results; report the fit error (e.g. % error on
  compression duty and total facility CAPEX) in `docs/dwsim-validation/`.
- The paper states: detailed process engineering done in DWSIM; the framework carries
  validated correlations for fast screening.

## Dependencies

- CoolProp (CO₂ thermodynamics, runtime).
- NumPy.
- DWSIM (offline only, for correlation calibration; not a runtime dependency).

## Done Criteria

- [ ] Compression duty from the Python/CoolProp model matches the DWSIM reference
      within a documented tolerance across the 8 calibration points.
- [ ] Facility CAPEX and OPEX scale sensibly and monotonically with throughput.
- [ ] CO₂ surface-loss fraction is produced and flows into Module 4's net-storage calc.
- [ ] All CO₂ property calls use CoolProp real-gas; no ideal-gas assumption anywhere.
- [ ] Correlation coefficients and DWSIM validation results are documented in
      `docs/dwsim-validation/` with the process flow diagram.
- [ ] Module evaluates effectively instantly (pure arithmetic + a few CoolProp calls).
