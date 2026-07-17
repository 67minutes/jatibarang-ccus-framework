# Arm B MRST runs

Arm B is the locked limited-simulation optimization arm. It is generated separately
from the original 177-case training corpus; raw training files must not be copied into
this repository.

## Locked design

- Exactly 40 accepted MRST results are required.
- Each of the 20 candidate geologies contributes two primary schedules.
- Primaries are selected with seed `20260717` by global normalized maximin sampling
  across injection rate, soak duration, production duration, production BHP, and
  cycles.
- Permanently failed attempts remain in the audit. The next pre-ranked schedule for
  the same geology is run until 40 accepted results exist.

The canonical working bundle contains `arm_b_design.csv` with 40 primary rows and
`arm_b_replacement_order.csv` with 3,200 deterministic replacements. These files are
experiment definitions, not MRST results.

## Current state

Accepted runs: **0**. No result manifest exists. The July 17, 2026 MRST preflight
yielded zero safe workers under the locked RAM-reserve formula, so no bank run was
launched. A partial run count cannot be promoted as the locked Arm B comparison.

Local payloads remain ignored. The result manifest must record each attempt and
acceptance outcome, case/geology identity, schedule fingerprint and parameters,
source path/hash, runtime and hardware, objective and constraints, failure/replacement
linkage, software version, and generation date.
