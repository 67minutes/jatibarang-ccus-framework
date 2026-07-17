# Feature 005 Screening Presets

This directory contains tracked manifests for derived Feature 005 preset banks. Large
NPZ payloads are ignored. They contain only the static maps and schedule-matched
eight-frame warm starts needed at runtime; the raw 177-case MRST corpus remains in
`boreyes2026`.

Expected preset IDs:

- `jatibarang_demo_v1`: 20 candidate geologies x 10 schedules = 200 scenarios;
- `jatibarang_full_v1`: the same geologies x 162 schedules = 3240 scenarios.

Each manifest records the design checksum, upstream case/parameter identity, payload
SHA-256, schedule fingerprints, source classes, units, and whether the local payload
is ready. Feature 005 rejects missing or mismatched data and never substitutes a cold
start or synthetic seed.

Current local state: both deterministic preset designs have been generated, but
neither imported payload/manifest is complete. `GET /presets` therefore reports
`ready=false`; no proxy result is substituted.

The July 17, 2026 execution preflight yielded zero safe workers under the locked
concurrency formula because available RAM was below the 3 GiB reserve. Consequently,
the required three-run benchmark and both the 200- and 3,240-scenario exports were not
launched. This is a resumable execution gate, not evidence that either bank exists.

The upstream exporter is invoked from MATLAB after generating `upstream_design.json`:

```matlab
generate_hnp_dataset('mode', 'feature005', ...
    'feature005_design', 'C:/Users/mauli/Documents/jatibarang-ccus-framework/data/screening_presets/jatibarang_demo_v1/upstream_design.json', ...
    'feature005_output', 'C:/Users/mauli/Documents/boreyes2026/exports_feature005_demo');
```

Use `feature005_max_runs` only for a bounded exporter smoke. A partial directory is not
a ready preset and cannot receive a local manifest/payload until every designed run is
present and hash-verified by the importer.

The exporter also supports disjoint, resumable workers through
`feature005_shard_index` and `feature005_shard_count`. After every shard is complete,
run once with `feature005_merge_shards=true`; only that verified merge writes the
downstream-compatible `manifest.json`. Exact benchmark, shard, resume, and merge
commands are documented in
`C:/Users/mauli/Documents/boreyes2026/data/FEATURE005_SHARDED_EXPORT.md`.

The submitted Feature 007 bundle may use 3,240 scenarios only when the full bank is
complete and hash-verified. Otherwise it must use the complete promoted 200-scenario
bank and report that actual count. No current submitted or `full_3240` bundle exists.
