# Data Layout

This repo stores only the data needed to run, validate, or document the
Jatibarang CCUS framework. It does not store the raw 177-case MRST training
corpus from `boreyes2026`.

- `terrain/`: SRTM or other terrain rasters for route/elevation work, ignored.
- `jatibarang/`: small case-study parameters and committable inputs.
  Feature 002 uses `pipeline_exclusions.geojson` (public OSM screening proxy with
  ODbL attribution) and `pipeline_cost_basis.json` (tracked NETL/IEAGHG-derived
  low/base/high screening coefficients). Feature 003 uses
  `facility_design_basis.json`, `facility_cost_basis.json`, and
  `facility_validation_cases.json` for the dedicated-skid design, low/base/high
  screening costs, and pinned eight-case DWSIM envelope. Feature 004 uses
  `economic_basis.json` for the constant-dollar basis, four dated carbon-price cases,
  CoolProp standard-state CO2 density, gas heating value, fiscal sensitivities,
  uncertainty thresholds, and root-solver bounds. These are small derived or assumed
  inputs; none contains the raw MRST corpus or proprietary facility data.
- `validation_cases/`: five selected MRST full-field cases used by the Feature 001
  validator; binary payloads are ignored while the manifest and README are tracked.
- `scenario_b_runs/`: limited-simulation optimization arm outputs, ignored.
- `imports/`: machine-local, content-addressed terrain/reservoir/spatial-result and
  OSM graph/layer caches. The official Java PBF download and derived caches are
  ignored; the tracked README records hashes, attribution, and relink behavior.
- `screening_presets/`: ignored Feature 005 derived payload banks plus tracked policy
  documentation. `feature005_seed_design.json` freezes the normalized-maximin geology
  and schedule selection rules. The upstream exporter writes only fixed-run derived
  static maps, eight-frame histories, production increments, provenance, and hashes;
  the raw 177-case corpus is never copied here.

Derived, reviewable validation summaries are stored under `paper/validation/`, not in
this data directory. Model accuracy metadata that contains no weights or raw fields is
stored under `models/metadata/`.
