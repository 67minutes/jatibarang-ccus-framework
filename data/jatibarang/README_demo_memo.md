# Regenerating the reference study memo

`jatibarang.study.json` is an exported workbench artifact, not a baked frontend
fixture. Regenerate it only through the same import, placement, screening, and
save flow available to users.

## Required local artifacts

- Terrain: `data/terrain/12. DEM SRTM 30m Provinsi Jawa Barat/DEM SRTM 30M JAWA BARAT.tif`
- Reservoir model: `data/validation_cases/case_0016.mat`
- Wells CSV: `data/jatibarang/demo_wells.csv`
- Optional launch-pad bank: the Feature 005 bank for this exact model, when it
  exists. Confirm its model/hash match in the New Study preview; never substitute
  a bank from another realization.

The CSV is derived from `case_study_assumptions.json`. Its `W01` row is ignored
because the model-native well is always derived from the imported MRST cell.

## Workbench flow

1. Start the local workbench and choose **File → New Study**.
2. Use `Jatibarang reference study` as the field/reservoir name.
3. Import or select the terrain above.
4. Inspect `case_0016.mat`. Add the matching launch-pad bank only when it is
   available and hash-valid.
5. Set the field center to latitude `-6.53`, longitude `108.39`, and rotation
   `35°`.
6. Attach `demo_wells.csv`, choose the 3D start view, and create the study.
7. In the basin scene, add the source at `-6.571, 107.759` with:
   - name `Subang proxy source`;
   - annual capacity `500000 t/y`;
   - peak flow `600 kg/s`;
   - outlet pressure `120 bar`;
   - outlet temperature `27 °C`;
   - CO₂ purity `0.95`.
8. Review Compose coverage, then Screen. With only the current native model,
   the scientifically correct preview is `0 of 162` grid schedules plus one
   real, runnable off-grid native schedule. Do not relabel that as `1 of 162`.
9. Inspect the completed result, field scene, and warnings. Choose **File → Save
   Study As…** and save `data/jatibarang/jatibarang.study.json`.

## Verification before committing

- `field_setup.terrain.sha256` matches the registered terrain.
- `field_setup.reservoir.sha256` matches `case_0016.mat`.
- `field_setup.reservoir.bank_sha256` is null when no bank was used, otherwise
  it matches the imported bank.
- `field_setup` contains the placement, 20 wells, and Subang source.
- `request_payload_mode` is `artifact_referenced`; the required geology and
  launch-pad API catalogs are omitted, so the summary cannot be submitted as a
  screening request.
- `result_payload_mode` is `summary`; aggregate rankings, production,
  economics, warnings, and provenance remain available, while per-cell
  prediction fields and detailed reservoirs are omitted. The saved result is
  read-only; create a new study and re-import the matching artifacts to rerun
  or regenerate spatial fields.
- The memo fingerprint equals the completed screening result fingerprint.

Never hand-edit the memo or replace pending artifacts with synthetic data.
