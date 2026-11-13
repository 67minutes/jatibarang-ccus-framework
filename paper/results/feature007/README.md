# Feature 007 canonical paper bundles

This directory is the shared numerical source for publication figures and the
interactive paper-results frontend.

- `working/` is reproducible and may be rebuilt as real evidence arrives.
- `submitted/` is created only by the freeze command after all eight figure
  gates, the 200- or 3,240-scenario preset gate, and the A/B/C confirmation
  gates pass. An existing immutable target is never overwritten.

## Current state: 2026-07-18

`working` passes its deterministic hash verifier but remains **partial and
unfrozen**. Its manifest reports `scenario_count=0`, mechanical status `BLOCKED`,
scientific status `NOT_RUN`, and `fabricated_result=false`. Hash verification means
that the artifacts which are present agree with the manifest; it is not a scientific
or paper-promotion PASS.

Figures 1, 2, 3, and 6 are bundle-driven where numerical or spatial data apply,
rendered, and hash-registered. Figures 4, 5, 7, and 8 are explicitly blocked on the
promoted Feature 005 bank and/or locked A/B/C evidence. The declared Figure 3 median
case (`case_0016`) is included as real MRST truth plus frozen-checkpoint rollout data;
its current linked dynamic comparison field is gas saturation. No paper result is
synthesized to fill a missing dependency.

The deterministic Arm B design exists with 40 primary rows over 20 geologies and a
3,200-row replacement order. Arm C now also carries 20 independent-limit and 20
correlated-limit field assignments (800 auditable well-level rows), plus a cache-only
Feature 005 adapter that performs zero surrogate calls during downstream re-solves.
The design groups work by assignment x carbon price and never promotes one named-well
assignment as a paper claim.

Accepted Arm A/B/C result counts remain zero. The three-run MRST timing benchmark is
now complete, but neither the 200- nor 3,240-scenario paper bank has been launched or
imported. The separate one-schedule, 20-well workflow smoke is explicitly non-paper
evidence. There is no `submitted/` or `full_3240/` bundle.

The exact CPU, physical-core count, total/available RAM snapshot, concurrency gates,
and no-launch decision are hash-referenced from
`paper/validation/feature007/execution_preflight.json` into each rebuilt bundle. The
same input now also hash-records the later bounded 3/3 timing benchmark and 20/20
one-schedule workflow smoke; neither is treated as a paper-bank launch.

## Build and verify

```powershell
python -m jatibarang_ccus.paper.feature007 build --bundle-id working
python -m jatibarang_ccus.paper.feature007 verify --bundle-id working
python paper/figures/fig01_framework.py --bundle paper/results/feature007/working
python paper/figures/fig02_atlas.py --bundle paper/results/feature007/working
python paper/figures/fig03_surrogate.py --bundle paper/results/feature007/working
python paper/figures/fig06_facility.py --bundle paper/results/feature007/working
```

Blocked figure scripts exit non-zero and print the missing real artifacts.
After generating a figure, rebuild once so its artifact hash is registered.

## Freeze

At the agreed paper cutoff, and only after `working` is scientifically ready:

```powershell
python -m jatibarang_ccus.paper.feature007 freeze `
  --source working `
  --target submitted `
  --frozen-at 2026-07-21T18:00:00+07:00
```

If all 3,240 cases are not complete, the ready 200-scenario bundle is frozen and
that actual count remains visible in its manifest and frontend provenance. A later
complete bank is frozen separately with `--target full_3240`; it never overwrites
the submitted bundle.

## Expected normalized Feature 007 inputs

Real experiment outputs are staged under `paper/validation/feature007/`. The
builder recognizes these tables and only unlocks their figures when every
required table and upstream gate exists:

- `screening_surface.csv`;
- `pipeline_route.csv`, `pipeline_pressure_profile.csv`,
  `pipeline_cost_crossover.csv`;
- `carbon_price_rankings.csv`, `carbon_price_regret.csv`,
  `npv_vs_carbon_price.csv`;
- `abc_economics.csv`, `abc_runtime.csv`, `topk_confirmation.csv`;
- `arm_c_screening.json`.

Every copied table records its source path, source hash, bundle hash, row count,
and source class in `manifest.json`.
