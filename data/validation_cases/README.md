# Validation Cases

Selected full-field MRST cases for plume-gallery and paper-figure validation go
here. Payload files are intentionally ignored because they can be large.

The current curated subset contains five cases:

- `case_0016` - four cycles;
- `case_0115` - four cycles;
- `case_0176` - four cycles;
- `case_0197` - three cycles;
- `case_0209` - four cycles.

They were exported from:

`C:\Users\mauli\Documents\boreyes2026\exports_hnp_expressive\final`

Do not copy the full 177-case training corpus into this repo.

For each imported case, add or keep a manifest containing:

- Source case id and original path
- Export date
- Fields included
- Why the case was selected for the paper/demo

The tracked [`manifest.json`](manifest.json) records the derived case identities while
the `.mat` payloads remain ignored. Refresh the local Feature 001 evidence with:

```powershell
python -m jatibarang_ccus.surrogate.validation --skip-benchmark
```

The reports are written to `paper/validation/`. These five cases provide a curated
local scientific check; they do not replace the pinned upstream 36-case held-out
evaluation.
