# Blank-Slate Field Workflow — Design

**Date:** 2026-07-17
**Status:** approved-pending-user-review
**Owner flow:** New Study → import terrain + reservoir model + launch pads → place field → add wells/sources → enter field → screen

## 1. Purpose

Turn the workbench from a Jatibarang-preloaded demo into a general engineering
tool. The app opens empty; a study is created by importing data; "Jatibarang"
becomes just a study you open, not a product identity. This also replaces the
per-well geology-realization assignment with the methodologically defensible
one-model-per-study pattern.

## 2. Decisions already made (with the user)

| Decision | Choice |
|---|---|
| Field georeference (MRST has none) | **Both**: dialog seeds center lat/lon + rotation; outline stays draggable/rotatable in the basin view |
| SRTM import | **Whole raster, auto-crop**: register a GeoTIFF, basin view shows a downsampled overview of all of it; field view auto-fetches a ~30 m window around the placed field |
| Demo content | **Pure blank slate**: no bundled sample, no demo template; the Jatibarang demo is regenerated through this flow into an ordinary `.study.json` kept in the repo |
| Geology unit | **One reservoir model per study** (one realization). All candidate wells share it — the perfectly-correlated spatial limit, stated in the well inspector. The paper's experiment samples the independent limit (per-sector draws, Monte-Carlo assignments) and brackets both; the tool and paper are the two ends of the same declared spectrum |
| Launch pads | **Imported together with the model**: the engineer imports the reservoir model and its associated launch-pad bank; the operating grid enables only covered schedules |
| Uncertainty pattern | Swap the reservoir model (study settings → "Change reservoir model…") and re-run; the run ledger provides comparison. No per-well realization assignment |

## 3. Vocabulary (UI copy)

- **Reservoir model** — one MRST `.mat` realization: geology grids + native
  simulation frames. UI never says "case" or "realization ensemble".
- **Launch pads** — the schedule-fingerprinted 8-frame warm-start histories the
  surrogate needs ("seed" appears nowhere in UI copy). One `.mat` carries one
  launch pad (its native schedule); a **launch-pad bank** (the Feature 005
  NPZ seed-bank format, unchanged) covers many schedules.
- **Field** — the named, placed boundary on the terrain that owns wells,
  sources, and the reservoir model.

## 4. Boot state (blank slate)

- No terrain, no study, no demo auto-load. Neutral ground plane + subtle
  graticule + one hint card: "New Study (Ctrl+N) · Open Study (Ctrl+O)".
- Removed: `/assets/terrain.json` fetch, `demo-request.json` /
  `canned-demo.json` wiring in `useWorkbench`, the "Jatibarang demo base"
  template option, `DEFAULT_STUDY_NAME` → "Untitled study", "Jatibarang" in
  About text. The asset files themselves are deleted once the regenerated demo
  memo exists (§12).

## 5. New Study dialog

Fields, in order:

1. **Field / reservoir name** (required; becomes the outline label and memo name stem)
2. Analyst (optional)
3. **Terrain** — dropdown of registered rasters + "Import GeoTIFF…" (path
   input; backend does the reading). Required.
4. **Reservoir model** — one `.mat` file. Required.
5. **Launch pads** — bank file for the model (optional; without it the study
   covers only the model's native schedule). Shown with a coverage preview
   ("covers 162 of 162 grid schedules" / "native schedule only").
6. **Initial placement** — center lat/lon + rotation, prefilled with the
   terrain-raster center; helper text says it can be dragged later.
7. Initial viewport (3D/2D) and terrain exaggeration (existing prefs).

Create → draft study opens in the basin view with the outline at the seeded
placement. Wells CSV import (`id,lat,lon`) is a small optional input in the
dialog for batch well placement.

## 6. Backend endpoints (new)

The browser parses neither GeoTIFF nor MAT nor NPZ; the backend already has
rasterio/h5py/numpy.

- `POST /terrain/import` `{path}` → `{terrain_id, sha256, extent_lon_lat,
  cell_size_m, overview: heightmap ≤ ~512²}`. Registers into a terrain
  registry (existing `data/terrain` + cache conventions). Idempotent by hash.
- `GET /terrain/{terrain_id}/window?bounds=…&max_px=…` → high-res heightmap
  window for the field view (auto-requested around field bounds + padding;
  re-fetched when the field moves).
- `POST /reservoir/import` (multipart: model `.mat`, optional launch-pad bank)
  → `{model_id, sha256, geology payload, native_schedule, native launch pad,
  bank_coverage: [schedule fingerprints]}`. Parsing reuses the existing
  `load_validation_case` logic, refactored into a shared loader module used by
  both this endpoint and `surrogate/validation.py`. Bank parsing reuses the
  Feature 005 preset seed-bank import unchanged.
- Imported artifacts are stored backend-side under `data/imports/<sha256>/`
  and referenced from the study memo by id + hash (memos stay small; a memo
  opened without its artifacts shows a "missing import" state with re-link,
  like linked assets in any engineering tool). Geology payloads are small
  enough to embed, but banks are tens of MB — one rule for both: reference,
  don't embed.

No changes to `/screen`: the inline request already supports one shared
`geology_id` for all candidates and fingerprint-keyed seed banks.

## 7. Basin view

- Hillshaded overview of the whole registered raster (muted palette, existing
  terrain color system).
- **Field outline**: rotated rectangle sized from the model grid
  (`length_x_m × length_y_m`), named label, draggable body + rotate handle.
  Position/rotation live in the study store and memo.
- **Wells**: two kinds, one shared reservoir model.
  - **The model's native well is imported, not placed.** The `.mat` carries
    `well_ij` + completion cells; its map position is derived from the field
    anchor + rotation and appears automatically when the field is placed
    (moves/rotates with the outline; renamable; not independently draggable).
    A single-well study therefore requires zero manual well placement.
  - **Additional candidate wells are placed by the engineer** (right-click
    inside outline → "Add candidate well", name auto-suggested; or the dialog's
    CSV import). The file cannot supply these — each MRST export simulates
    exactly one well. Placed wells are draggable; right-click → rename /
    remove. The shared-model assumption is shown once in the well inspector.
  - **Placement semantics (training-distribution constraint).** A placed
    candidate reuses the model's native in-grid well configuration unchanged;
    the tool never relocates the well within the 64×64 grid. Verified basis:
    the training corpus (212 exports, 177 accepted) contains zero
    same-geology/different-placement pairs, and well position varies only as
    ±2/±4-cell jitter around center — within-geology placement response is
    untrained and must not be requested. Map position therefore affects
    logistics only; in a one-model study all candidates share identical
    reservoir response per schedule (the orchestrator's fingerprint cache
    dedupes these rollouts, so N wells cost one well's compute). The well
    inspector states this in one line: "Reservoir response assumes the local
    geology at this site matches the study's reservoir model."
- **Sources**: right-click anywhere on terrain → "Add CO₂ source here" →
  dialog: name + annual capacity (t/y) required; Advanced (collapsed): outlet
  pressure, temperature, purity, peak flow with current screening defaults.
  Draggable; right-click → edit / remove.
- **Enter field**: double-click the outline, or right-click → "Enter field".
- Esc clears transient states (drag, context menu) as today.

## 8. Field view

- Existing warped reservoir grid visualization (unchanged renderer) +
  the high-res terrain window, at the field's placed position/rotation.
- Wells render at their map positions; the reservoir grid draws at the field
  anchor. Breadcrumb "◂ Basin" + Esc exits; short camera transition both ways.
- All existing layer/exaggeration/opacity/threshold controls unchanged.
- **Influence-zone layer (post-run)**: after a screening run, each selected
  well shows its predicted influence radius (from the result's plume-derived
  interference audit) as a translucent disc in basin and field views; wells
  with interference flags get a warning badge and the flag text in the
  inspector. This makes the single-well-independence assumption and its audit
  visible instead of implicit. The surrogate is single-well-trained; the tool
  never composes multi-well grids — candidates are independent rollouts and
  interference is audited, not simulated.

## 9. Schedule coverage in Compose

- The operating-grid editor shows per-combination coverage from the imported
  launch pads: covered schedules enabled; uncovered ones disabled with one
  shared explanation line ("no launch pad for this schedule — import a bank
  or run MRST offline"). No silent invention of starting frames, ever.
- A screen request only includes covered schedules; the request builder
  refuses to submit an empty coverage set with a clear message.

## 10. Study memo v2

Additions (schema version bump; v1 memos still open read-only with a notice):

```
terrain:   { terrain_id, sha256, source_path }
field:     { name, center_lat, center_lon, rotation_deg }
reservoir: { model_id, sha256, source_file, native_schedule_fingerprint }
launchpads:{ bank_id | null, sha256 | null, coverage_count }
wells:     [ { id, kind: "native" | "placed", lat, lon } ]
           # native well lat/lon is derived (recomputed on field move);
           # stored for display/export, never hand-edited
sources:   [ { id, name, lat, lon, annual_capacity_t, pressure_bar,
               temperature_c, purity, peak_kg_s } ]
```

Compose/screening reads candidates and sources from the study, ending the
`case_study_assumptions.json` candidate/source constants' role in the app
(the file remains paper/preset input).

## 11. Out of scope (recorded follow-ups)

- Exclusion-zone import (routing keeps the repo GeoJSON).
- Multi-field studies; per-well geology overrides (the escape hatch that
  restores per-site reservoir-response differentiation when site-specific
  models exist); realization sets for uncertainty bands in one run.
- Within-geology well-placement sensitivity — requires a paired-placement
  training dataset (same realization, multiple well positions) or per-site
  models; recorded as future work, also a §3.6 limitation line in the paper.
- "Generate launch pads" (queued offline MRST) — the future third path.
- Memo/artifact packaging into a single archive.

## 12. Demo regeneration

After implementation, rebuild the Jatibarang study through the real flow
(register the Jawa Barat raster, import `case_0016.mat` + its bank when the
G3 bank lands, place the field, add W01–W20 via CSV, add the Subang source)
and save `data/jatibarang/jatibarang.study.json`. That memo is the conference
demo; the app itself ships nothing Jatibarang.

## 13. Verification

- Backend: terrain import (extent/hash/overview shape, idempotency), window
  crops, `.mat` import (fixture case parses; malformed rejected), bank
  coverage report, artifact-reference round-trip.
- Frontend: scene-state machine (blank → basin → field and back), outline
  drag/rotate updates memo state, right-click add/edit/remove for wells and
  sources, coverage-driven grid enablement, memo v2 round-trip, v1-memo
  open-with-notice.
- Manual QA: full flow at 1920×1080 with the real Jawa Barat raster and
  `case_0016.mat`; no console errors; blank slate renders without any
  network fetch of removed assets.
