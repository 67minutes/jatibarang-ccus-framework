# Feature 007 validation staging

This directory is reserved for normalized real experiment outputs consumed by the
Feature 007 canonical bundle builder. It is not itself a result bundle.

## Current state: NOT RUN

No Feature 007 experiment result table or accepted A/B/C manifest exists here. The
current `paper/results/feature007/working` bundle verifies the hashes of its present
module evidence but remains partial and unfrozen: `scenario_count=0`, mechanical
`BLOCKED`, scientific `NOT_RUN`, and `fabricated_result=false`.

Figures 1, 2, 3, and 6 are ready from canonical methodology/module/validation inputs.
Figures 4, 5, 7, and 8 remain blocked. The real `case_0016` MRST/surrogate reservoir
comparison is registered in the working bundle; it does not constitute the A/B/C
experiment.

The earlier RAM preflight blocked the launch at that snapshot. A later bounded
three-run MRST timing benchmark completed, but no 200/3,240 paper bank export has
been launched or imported. A separate 20-well, one-common-schedule MRST workflow
smoke is non-paper UI evidence and does not change the paper gate. There is no
immutable `submitted` or `full_3240` bundle.

Arm C orchestration is now implemented mechanically: 20 independent-limit plus 20
correlated-limit assignments, one cache-only downstream run per assignment, and
assignment x carbon-price result projection with zero surrogate calls. The working
bundle contains the 800-row assignment table. `arm_c_screening.json` is still absent,
so this implementation PASS is not a scientific result.

The measured CPU, core count, memory snapshot, concurrency gates, and no-launch
decision are recorded in `execution_preflight.json`; the Feature 007 bundle hashes
that file as an input. Its additive post-preflight section records the later 3/3
timing benchmark and 20/20 workflow smoke with their manifest hashes while retaining
`NOT_LAUNCHED` for both paper banks.

## Expected real outputs

The builder unlocks paper figures only after the required hashed inputs exist:

- `screening_surface.csv`;
- `pipeline_route.csv`;
- `pipeline_pressure_profile.csv`;
- `pipeline_cost_crossover.csv`;
- `carbon_price_rankings.csv`;
- `carbon_price_regret.csv`;
- `npv_vs_carbon_price.csv`;
- `abc_economics.csv`;
- `abc_runtime.csv`;
- `topk_confirmation.csv`; and
- `arm_c_screening.json`.

Arm A also requires its two accepted MRST confirmations, Arm B exactly 40 accepted
MRST runs with failures retained in the audit, and Arm C five unique MRST-confirmed
plans plus minimum/median/maximum-throughput DWSIM spot-checks. Missing data remains
blocked; no proxy or synthetic substitution is permitted.
