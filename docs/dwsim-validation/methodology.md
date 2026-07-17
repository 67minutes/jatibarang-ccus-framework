# Feature 003 Validation Methodology

## Boundary and ownership

Feature 002 delivers fresh dense CO2 to each selected well. Feature 003 owns one
dedicated well-pad skid per selected well. Recovered production CO2 is separated,
conditioned, compressed back to delivery pressure, cooled to a dense state, mixed
with fresh CO2, and pumped once across the remaining wellhead pressure rise.

The DWSIM flowsheet uses these named unit operations:

| ID | Function |
|---|---|
| `SEP-01` | Three-outlet separator representation at 10 bar and 35 C |
| `DEHY-01` | Pure-CO2 dehydration/conditioning boundary |
| `COMP-01` to `COMP-03` | Three equal-ratio recycle-compression stages, 75% isentropic efficiency |
| `COOL-01`, `COOL-02` | 35 C intercoolers with 0.25 bar pressure drop |
| `COOL-03` | Final 27 C dense-phase recycle cooler with no modeled pressure drop |
| `MIX-01` | Fresh and recovered dense-CO2 mixer |
| `PUMP-01` | 78% efficiency pump to 137.895146 bar wellhead pressure |

Important material streams are `PROD-FEED`, `SEP-GAS`, `DEHY-OUT`, `C1-OUT`,
`IC1-OUT`, `C2-OUT`, `IC2-OUT`, `C3-OUT`, `RECYCLE-DENSE`, `FRESH-DENSE`,
`PUMP-SUCTION`, and `INJECTION-OUT`. The property package is DWSIM CoolProp.

## Process representation

The production-side DWSIM feed is the recovered pure-CO2 equivalent, not a predictive
oil/water composition model. `SEP-01` therefore validates the gas-path mass balance;
its oil and water outlets are zero in this benchmark. Python sizes the three-phase
vessel using the pinned gas rate, 75 m3/day liquid assumption, 0.35 water cut,
Souders-Brown factor, residence times, and L:D target.

`DEHY-01` is a labeled conditioning boundary because the benchmark feed contains no
water component. Python still reports and costs a dehydration package from recovered
CO2 throughput and a 50 ppmv outlet-water target. This avoids claiming that the
pure-CO2 DWSIM cases validate water-removal performance.

## Case design

`data/jatibarang/facility_validation_cases.json` is a resolution-IV, two-level,
four-factor design with `D = A*B*C`:

- fresh injection: 8,000 or 10,000 standard m3/day;
- Feature 002 delivery pressure: 80 or 120 bar;
- peak produced gas: 4,500 or 7,300 standard m3/day;
- produced CO2 mole fraction: 0.525 or 0.795.

Standard conditions are 1.01325 bar and 15 C. All standard-volume conversions use
CoolProp density; dense-phase delivery density is never applied to standard volume.
The recovered recycle fraction is 0.95.

## Automation and extracted results

`tools/dwsim/FacilityValidationRunner` loads the tracked flowsheet, applies each case,
solves it with `Automation3.CalculateFlowsheet4`, rejects solver exceptions, and
exports:

- convergence status and software/model/case hashes;
- summed compressor and cooler duties;
- injection-pump and total power;
- separator gas load;
- inlet/outlet mass and normalized residual.

The runner is a .NET Framework 4.7.2 console application because that is the ABI of
the installed DWSIM 10 automation assemblies. It is built with Visual Studio 2022
MSBuild and is completely outside the Python runtime dependency set.

## Comparison and promotion gates

For each positive reference value, absolute percentage error is
`abs(runtime - DWSIM) / abs(DWSIM) * 100`. Promotion requires:

- eight unique, converged case IDs with matching case-file hash;
- compressor, pump, and total-power MAPE no greater than 5%;
- no individual power error above 10%;
- maximum DWSIM mass-balance residual no greater than 0.001;
- monotonic power, CAPEX, OPEX, separator capacity, and loss behavior on the pinned
  seven-point screening sweep;
- exact equipment-to-well and well-to-portfolio reconciliation;
- a manifest whose hashes verify.

The saved run passed every gate. The final 27 C cooler was retained after the first
real DWSIM run exposed a gas-like near-critical pump-suction state for the 80 bar,
high-recycle case. Cooling the recycle stream back to the Feature 002 delivery
temperature makes the pumping boundary physically consistent throughout the declared
envelope.

## Evidence semantics and limitations

`dwsim_reference.csv` is native DWSIM duty and balance output. CAPEX/OPEX in
`equipment_cost_curve.csv` are screening correlations applied in Python; they are not
DWSIM cost-estimator output. The literature-aligned coefficients are low/base/high
project proxies and are not proprietary Jatibarang data, Indonesian quotations, or
FEED.

The validation statement applies only inside the four-factor envelope and to the
fixed topology. Inputs outside it are evaluated with an
`outside_calibration_envelope` status. The evidence does not validate wellbore
hydraulics, transient HnP operation, lower-purity mixed-gas thermodynamics, water
removal, oil/water separation performance, or field constructability.
