# Demo assets

These are **generated** fixtures that let the workbench run its demo and offline
path without a live backend. They are committed (they compress to tens of KB in
git despite their raw size) so the app works on a fresh checkout, and are
regenerable from the scripts below.

| Asset | What it is | Regenerate with |
|-------|-----------|-----------------|
| `demo-request.json` | A valid inline screening request (3 wells, 4 carbon prices, 2 injection-rate schedules) over uniform demo geology at real Jatibarang-area coordinates. Seeds the composer and pairs with the cached result. | `python frontend/scripts/gen_demo_request.py` |
| `canned-demo.json` | A real `/screen` result captured from the backend for `demo-request.json`. Loaded into the ledger on startup so results show offline. | `curl -X POST :8000/screen --data-binary @demo-request.json -o canned-demo.json` |
| `demo-plume.json` | A compact 10-frame CO₂ plume animation (z_CO₂ + gas saturation) captured from `/predict` for the demo well. Feeds the 3D extruded reservoir grid. | See `gen_demo_request.py` header + a `/predict` capture |
| `terrain.json` | A 120×120 SRTM heightmap clipped to the Jatibarang extent, baked from the province GeoTIFF. | `node frontend/scripts/bake-terrain.mjs` |

## Honest note on the demo result

The demo uses **uniform** geology (the real MRST-derived fields are not
materialized locally — Feature 007 owns that). At Huff-and-Puff CO₂ volumes a
dedicated pipeline is not economic, so the screening result is honestly
`no_viable_network` with an empty development shortlist — the same outcome the
repository documents for the default proxy. The workbench surfaces this
transparently (pre-logistics well ranking, trucking as the indicated supply,
full confidence flags). Viable-network economics and a differentiated ranking
appear when real MRST geology is supplied.
