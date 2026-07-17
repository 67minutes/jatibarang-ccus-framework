# Feature 003 Research Decisions

## Module boundary and ownership

**Decision**: Feature 003 owns one dedicated injection/production skid per selected
well. Feature 002 ends at the dense-phase delivery pressure at that well and retains
source conditioning, trunk compression, boosters, and network costs.

**Rationale**: the current caller evaluates a facility per well while multiplying its
separator by the total portfolio well count. A dedicated-skid contract removes that
contradiction and makes portfolio totals the exact sum of unique per-well equipment.

**Alternatives considered**: one central field facility; a mixed central/dedicated
topology selected per run. Both require a produced-fluid gathering network and a new
optimization decision that are outside Feature 003 and absent from Feature 002.

## Volumetric and mass-flow basis

**Decision**: retain the surrogate's injection rate as standard m3/day with explicit
1.01325 bar and 15 C reference conditions, but make peak kg/s the sizing quantity at
the facility boundary.

**Rationale**: the current code converts standard-equivalent injection volume using
dense-phase delivery density. At 8,000-10,000 standard m3/day the local CoolProp
conversion is approximately 0.173-0.217 kg/s; using 80-120 bar density would silently
inflate the equipment load. Annual tonnes and peak kg/s also serve different sizing
and accounting purposes.

**Alternatives considered**: infer mass flow from delivery conditions; reuse injected
campaign tonnes as a peak rate. Both are rejected unit errors.

## Pressure-duty split

**Decision**: fresh dense CO2 is pumped from the Feature 002 delivery pressure to the
required wellhead injection pressure. Only separated, recovered production CO2 is
compressed in stages to pump-suction pressure before being mixed with the fresh
stream. The combined dense stream then crosses the pump pressure rise once.

**Rationale**: this preserves the fixed receive/dehydrate/compress/pump/separate/recycle
topology without applying the same delivery-to-injection pressure rise to both a
compressor and a pump.

**Alternatives considered**: compress and pump the complete fresh stream over the same
pressure interval; assign all well-pad pressure rise to Feature 002. The first double
counts duty and the second removes the facility injection-pump responsibility.

## HnP operating modes

**Decision**: calculate rated injection-pump duty and production/recycle-compressor
duty as separate operating modes and apply separate annual hours from the HnP
schedule. They are not assumed to run simultaneously at one well.

**Rationale**: HnP alternates injection, soak, and production. A single annual-hours
multiplier overstates or obscures energy use.

## Separator and produced-water basis

**Decision**: size a three-phase separator from peak standard gas, produced CO2 mole
fraction, peak liquid rate, water cut, separator pressure/temperature, Souders-Brown
gas capacity, liquid residence time, and an L:D limit. Oil comes from the surrogate;
water remains a versioned, provenance-labeled case-study assumption until an upstream
water prediction exists.

**Rationale**: gas rate alone cannot audit a three-phase vessel size. The proxy water
input is more honest than an implicit zero-water separator.

## CO2 loss ledger

**Decision**: return tonnes and fractions for conditioning purge, recycle
non-recovery, and fugitives, with the source stream for every term. Return bulk
produced-back CO2 separately and forbid it from also appearing as a surface loss.

**Rationale**: Feature 004 already deducts produced-back CO2 in its storage balance.
A scalar stage-count loss can double count that mass and has no auditable basis.

## DWSIM validation mechanism

**Decision**: use a small tracked `.dwxmz` flowsheet and a .NET Framework 4.7.2
automation helper that references a user-installed DWSIM through `DWSIM_HOME`. This
target follows the actual DWSIM 10 automation assembly ABI and is built with Visual
Studio 2022 MSBuild. DWSIM remains absent from Python runtime dependencies. The
flowsheet uses DWSIM's CoolProp property package, and the comparison is described as
an independent flowsheet/unit-operation benchmark, not an independent equation-of-
state validation.

**Rationale**: DWSIM officially exposes COM/.NET automation, recommends .NET for
automation, exposes a CoolProp property package, and exposes compressor outlet,
efficiency, and power calculations. DWSIM 10.0.9650 was found under the user's local
application-data installation and all eight cases were executed through its real
automation assemblies.

**References**:

- https://dwsim.org/wiki/index.php?title=Automation
- https://dwsim.org/api_help/html/T_DWSIM_Thermodynamics_PropertyPackages_CoolPropPropertyPackage.htm
- https://dwsim.org/api_help/html/Properties_T_DWSIM_UnitOperations_UnitOperations_Compressor.htm

## Eight-case design

**Decision**: pin a two-level, four-factor, eight-run resolution-IV design covering
fresh injection rate (8,000/10,000 standard m3/day), delivery pressure (80/120 bar),
peak produced gas (4,500/7,300 standard m3/day), and produced CO2 mole fraction
(0.525/0.795). The case file also fixes injection pressure, separator conditions,
efficiencies, standard conditions, and recycle recovery.

**Rationale**: the matrix spans the documented screening envelope with eight runs
while separating the main effects needed for duty and loss calibration. The current
analytic Phase 1 proxy was inspected only to bound the gas/composition factors; final
Feature 005 inputs must still be checked against this envelope.

## Calibration and promotion thresholds

**Decision**: require mean absolute percentage error <=5% and pointwise error <=10%
for compressor, pump, and total power; DWSIM mass-balance residual <=0.1%; monotonic
power/CAPEX/OPEX with relevant throughput; exact cost allocation; and an explicit
`outside_calibration_envelope` status for unsupported inputs.

**Rationale**: the thresholds are tight enough to catch topology, unit, and
near-critical property mistakes while allowing small implementation and embedded
CoolProp-version differences.

The first DWSIM comparison did catch a near-critical pump-suction issue at 80 bar and
high recycle loading. The retained design therefore cools the final recycle stream to
the 27 C delivery temperature before mixing. The refreshed eight-case bundle passes
with maximum power error below `0.00002%`.

## Cost-correlation evidence

**Decision**: DWSIM supplies duties, stream balances, temperatures, and equipment
loads. Runtime equipment costs use a separate versioned low/base/high JSON source
ledger based on the standard references named in the feature spec and any approved
public source. DWSIM's optional paid cost-estimator plugin is not a project dependency.
Costs calculated from DWSIM duties are labeled `correlation_applied_to_dwsim_duty`,
not native DWSIM CAPEX.

**Rationale**: this keeps the workflow reproducible without purchasing a plugin and
prevents a process simulator duty from being misrepresented as an Indonesian quote.

## CoolProp implementation rule

**Decision**: use pressure/temperature for state points, enthalpy differences for
compression and cooling, and explicit phase checks at dense-pump states. Never compare
or cost absolute enthalpy values.

**Rationale**: CoolProp documents `PropsSI` state inputs, phase identification, and
that enthalpy/entropy are relative properties. Differences are the correct duty basis.

**Reference**: https://coolprop.org/coolprop/HighLevelAPI.html
