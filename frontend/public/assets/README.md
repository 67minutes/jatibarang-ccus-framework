# Demo assets

These are **generated** fixtures that let the workbench run its demo and offline
path without a live backend. They are committed (they compress to tens of KB in
git despite their raw size) so the app works on a fresh checkout, and are
regenerable from the scripts below.

| Asset | What it is | Regenerate with |
|-------|-----------|-----------------|
| `demo-request.json` | Inline preview of Figure 3's declared median-error validation case (`case_0016`): real MRST-derived static geology, the eight-frame MRST warm start, exact schedule, and one local-proxy W01 location. | `python frontend/scripts/gen_demo_request.py` |
| `canned-demo.json` | A real `/screen` result for that request, including aligned `detailed_predictions` and `detailed_reservoirs`. Loaded into the ledger on startup so the simulator-style reservoir works offline. | Start the backend, then run `npm run capture:canned` |
| `terrain.json` | A 120×120 SRTM heightmap clipped to the Jatibarang extent, baked from the province GeoTIFF. | `node frontend/scripts/bake-terrain.mjs` |

## Honest note on the demo result

The preview uses the real local validation artifact, but its W01 placement is a
**local proxy**, not surveyed orientation or subsea depth. At Huff-and-Puff CO₂
volumes the screened dedicated pipeline is still not economic, so the cached
result honestly remains `no_viable_network`; the reservoir evidence is retained
from the pre-logistics ranking for inspection instead of substituting a uniform
plume. MRST truth/surrogate/residual comparison fields live in the hash-verified
Feature 007 `case_0016` reservoir payload.
