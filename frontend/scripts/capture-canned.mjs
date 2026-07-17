/** Capture the offline workbench result from the real local screening API.
 *
 * Start the backend on 127.0.0.1:8000, then run `npm run capture:canned`.
 * The script refuses a response that omits the detailed case-0016 reservoir;
 * that prevents the old uniform/edge-plume fixture from silently returning.
 */
import { readFile, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..");
const requestPath = resolve(REPO_ROOT, "frontend/public/assets/demo-request.json");
const outputPath = resolve(REPO_ROOT, "frontend/public/assets/canned-demo.json");
const endpoint = process.env.JATIBARANG_API_URL ?? "http://127.0.0.1:8000/screen";

const request = JSON.parse(await readFile(requestPath, "utf8"));
const response = await fetch(endpoint, {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify(request),
});

if (!response.ok) {
  throw new Error(`screening capture failed: HTTP ${response.status} ${await response.text()}`);
}

const result = await response.json();
const reservoirIds = Object.keys(result.detailed_reservoirs ?? {});
const predictionIds = Object.keys(result.detailed_predictions ?? {});
if (reservoirIds.length === 0 || reservoirIds.join("|") !== predictionIds.join("|")) {
  throw new Error("refusing canned result without aligned detailed reservoir evidence");
}
const reservoir = result.detailed_reservoirs[reservoirIds[0]];
if (reservoir.geology_id !== "case_0016" || reservoir.provenance?.baseline_source_id !== "case_0016") {
  throw new Error("refusing canned result that is not the declared case_0016 validation preview");
}

await writeFile(outputPath, `${JSON.stringify(result)}\n`, "utf8");
console.log(`wrote ${outputPath} (${reservoirIds[0]}, ${predictionIds.length} detailed prediction)`);
