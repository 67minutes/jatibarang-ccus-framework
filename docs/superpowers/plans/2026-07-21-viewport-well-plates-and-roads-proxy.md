# Viewport Well Plates + Roads Proxy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every well with a relinked reservoir artifact shows its own geology plate in the 3D basin view, plume playback runs simultaneously on every well with retained detailed predictions, field view frames the selected well instead of always the placement, and the road/coastline/place-label layers work on the Vite dev server (:5173).

**Architecture:** A new pure module `wellPlates.ts` computes per-well plate descriptors (coordinate, geology source, retained prediction) from store state. `ReservoirGrid` is refactored to take explicit `reservoir`/`prediction` props instead of reading ledger/selection internally, and its global-timeline driving is hoisted into a single `TimelineDriver` mounted once (N plate instances must not each advance the shared step). The Vite dev proxy gains `/roads`, which is the verified root cause of the "road network could not be found" banner on :5173.

**Tech Stack:** React + react-three-fiber + three.js, Zustand stores, Vitest (jsdom), Vite dev proxy → FastAPI backend on :8000.

## Global Constraints

- Frontend-only change set. **No backend/API changes** — the backend on :8000 is current and serves `/roads/{id}/layers` correctly (verified 200 with 1.5 MB payload).
- `STUDY_MEMO_VERSION` stays 4; no memo schema changes.
- Provenance honesty: plates render only hash-verified relinked runtimes (`reservoirRuntimes`) or run-retained detailed fields (`result.detailed_reservoirs`). Wells with neither get **no plate** — never fabricate geology.
- Editing `vite.config.ts` requires **restarting the Vite dev server**. `start_workbench.bat` reuses a running instance, so the "Fieldman Frontend :5173" window must be closed first.
- Existing three.js-heavy components are not unit-rendered in this codebase; new logic must live in pure, tested functions. Component wiring is gated by `npx tsc -b`, the full Vitest suite, and `npm run build`.
- Verification commands (run from `frontend/`): `npm test -- --run` (currently 40 files / 177 passing), `npx tsc -b`, `npm run build`.
- Known accepted limitation: wells closer than ~900 m will have visually overlapping plates; do not add declutter logic (YAGNI).

## File Structure

- `frontend/vite.config.ts` — add `/roads` to the proxied API paths (Task 1).
- `frontend/src/viewport/wellPlates.ts` — NEW. Pure helpers: `scenarioIdForWell`, `cachedVisualizationFromImport`, `collectWellPlates`, `fieldFocusCoordinate`, `maxFrameCount` (Task 2).
- `frontend/src/viewport/wellPlates.test.ts` — NEW. Unit tests for all helpers (Task 2).
- `frontend/src/viewport/ReservoirGrid.tsx` — props become explicit `reservoir`/`prediction`; ledger/selection lookups removed (Task 3); timeline driving removed (Task 4).
- `frontend/src/viewport/TimelineDriver.tsx` — NEW. The single component that sets the global frame count and advances the step while playing (Task 4).
- `frontend/src/viewport/Viewport3D.tsx` — SceneContent renders one plate per descriptor in basin view, mounts TimelineDriver (Tasks 3–5); field-window effect, `fieldSpot`, and CameraRig `fieldTarget` follow the selected well (Task 6).

---

### Task 1: Proxy `/roads` through the Vite dev server

The dev server only proxies a fixed path list to FastAPI. `/roads` is missing, so `fetch("/roads/<id>/layers")` on :5173 receives Vite's HTML fallback, `response.json()` throws, and `hydrateMemoFieldSetup` shows "The road network for this study could not be found" on every open. Roads, coastline, and place labels all come from that one fetch ([MapContextLayers.tsx:157](../../frontend/src/viewport/MapContextLayers.tsx) renders nothing when `roadLayers` is null).

**Files:**
- Modify: `frontend/vite.config.ts` (the `API_PATHS` array)

**Interfaces:**
- Consumes: existing backend route `GET /roads`, `GET /roads/{id}/layers`, `POST /roads/import`.
- Produces: working `getRoadLayers`/`listRoadNetworks`/`importRoads` on :5173 — no code interface changes.

- [ ] **Step 1: Add the path**

In `frontend/vite.config.ts`, change:

```ts
const API_PATHS = [
  "/screen",
  "/presets",
  "/health",
  "/model",
  "/predict",
  "/paper",
  "/terrain",
  "/reservoir",
  "/docs",
  "/openapi.json",
];
```

to:

```ts
const API_PATHS = [
  "/screen",
  "/presets",
  "/health",
  "/model",
  "/predict",
  "/paper",
  "/terrain",
  "/reservoir",
  "/roads",
  "/docs",
  "/openapi.json",
];
```

(Vite matches string keys as URL prefixes, so `/screen` already covers `/screening/spatial`; `/roads` covers `/roads/import` and `/roads/{id}/layers`.)

- [ ] **Step 2: Restart the dev server and verify through the proxy**

Close the "Fieldman Frontend :5173" console window (leave the backend :8000 window running), then re-run `start_workbench.bat`. Verify from PowerShell:

```powershell
(Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:5173/roads").Content
```

Expected: a JSON array starting with `[{"road_network_id":"roads-3a57ea2910f5f161"` — NOT HTML. (Before the fix this returns the SPA `index.html`.)

- [ ] **Step 3: Commit**

```bash
git add frontend/vite.config.ts
git commit -m "fix(frontend): proxy /roads through the Vite dev server"
```

---

### Task 2: Pure well-plate helpers (`wellPlates.ts`)

**Files:**
- Create: `frontend/src/viewport/wellPlates.ts`
- Test: `frontend/src/viewport/wellPlates.test.ts`

**Interfaces:**
- Consumes: `reservoirVisualizationFromImport(imported: ReservoirImportResponse | null): ReservoirVisualization | null` (exported from `./ReservoirGrid`), `framesFromPrediction(prediction: PredictionResult): PlumeFrame[]` (from `./plume`), types `PlacedWell`/`FieldPlacement` (from `../state/field.store`), `Selection` (from `../state/selection.store`), `Coordinate`/`PredictionResult`/`ReservoirVisualization` (from `../api/types`), `ReservoirImportResponse` (from `../api/client`).
- Produces (used by Tasks 3–6):
  - `interface WellPlateDescriptor { wellId: string; coordinate: Coordinate; scenarioId: string | null; reservoir: ReservoirVisualization; prediction: PredictionResult | null }`
  - `scenarioIdForWell(detailedKeys: string[], wellId: string, preferredScenarioId?: string | null): string | null`
  - `cachedVisualizationFromImport(imported: ReservoirImportResponse | null): ReservoirVisualization | null`
  - `collectWellPlates(inputs: WellPlateInputs, toVisualization?): WellPlateDescriptor[]`
  - `fieldFocusCoordinate(selection: Selection, wells: PlacedWell[], placement: FieldPlacement | null): Coordinate | null`
  - `maxFrameCount(predictions: Array<PredictionResult | null | undefined>): number`

- [ ] **Step 1: Write the failing tests**

Create `frontend/src/viewport/wellPlates.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import type { PredictionResult, ReservoirVisualization } from "../api/types";
import type { ReservoirImportResponse } from "../api/client";
import type { PlacedWell } from "../state/field.store";
import {
  collectWellPlates,
  fieldFocusCoordinate,
  maxFrameCount,
  scenarioIdForWell,
} from "./wellPlates";

const runtime = (modelId: string) =>
  ({ model_id: modelId }) as unknown as ReservoirImportResponse;
const viz = (id: string) => ({ id }) as unknown as ReservoirVisualization;
const stubConverter = (imported: ReservoirImportResponse | null) =>
  imported
    ? viz(`viz-${(imported as unknown as { model_id: string }).model_id}`)
    : null;
const well = (id: string, lat: number, lon: number): PlacedWell => ({
  id,
  name: id,
  kind: "placed",
  lat,
  lon,
});
const prediction = (frameCount: number) =>
  ({
    fields: Array.from({ length: frameCount }, (_, step_index) => ({
      step_index,
      z_co2: { values: [] },
      gas_saturation: { values: [] },
      pressure_bar: { values: [] },
    })),
  }) as unknown as PredictionResult;

describe("scenarioIdForWell", () => {
  it("prefers the explicitly selected scenario when it belongs to the well", () => {
    const keys = ["W07--AAA", "W07--BBB", "W01--CCC"];
    expect(scenarioIdForWell(keys, "W07", "W07--BBB")).toBe("W07--BBB");
  });

  it("ignores a preferred scenario belonging to a different well", () => {
    const keys = ["W07--AAA", "W01--CCC"];
    expect(scenarioIdForWell(keys, "W07", "W01--CCC")).toBe("W07--AAA");
  });

  it("falls back to the first prefix or exact match, else null", () => {
    expect(scenarioIdForWell(["W07--AAA"], "W07")).toBe("W07--AAA");
    expect(scenarioIdForWell(["W07"], "W07")).toBe("W07");
    expect(scenarioIdForWell(["W01--CCC"], "W07")).toBeNull();
    // W17 must not match W1's prefix or vice versa.
    expect(scenarioIdForWell(["W17--DDD"], "W1")).toBeNull();
  });
});

describe("collectWellPlates", () => {
  const detailedReservoirs = { "W01--CCC": viz("detailed-W01") };
  const detailedPredictions = { "W01--CCC": prediction(3) };

  it("uses retained detailed fields when present, imported geology otherwise", () => {
    const plates = collectWellPlates(
      {
        wells: [well("W01", -6.5, 108.3), well("W02", -6.6, 108.4)],
        runtimes: { W01: runtime("m1"), W02: runtime("m2") },
        detailedReservoirs,
        detailedPredictions,
      },
      stubConverter,
    );
    expect(plates).toHaveLength(2);
    expect(plates[0]).toMatchObject({
      wellId: "W01",
      scenarioId: "W01--CCC",
      reservoir: viz("detailed-W01"),
      coordinate: { latitude: -6.5, longitude: 108.3 },
    });
    expect(plates[0].prediction).not.toBeNull();
    expect(plates[1]).toMatchObject({
      wellId: "W02",
      scenarioId: null,
      reservoir: viz("viz-m2"),
      prediction: null,
    });
  });

  it("omits wells with neither a runtime nor retained detail", () => {
    const plates = collectWellPlates(
      {
        wells: [well("W03", -6.7, 108.5)],
        runtimes: {},
        detailedReservoirs: {},
        detailedPredictions: {},
      },
      stubConverter,
    );
    expect(plates).toHaveLength(0);
  });

  it("keeps prediction null when the detailed reservoir has no retained prediction", () => {
    const plates = collectWellPlates(
      {
        wells: [well("W01", -6.5, 108.3)],
        runtimes: {},
        detailedReservoirs,
        detailedPredictions: {},
      },
      stubConverter,
    );
    expect(plates[0].reservoir).toEqual(viz("detailed-W01"));
    expect(plates[0].prediction).toBeNull();
  });

  it("routes the preferred scenario only to the selected well", () => {
    const twoScenarios = {
      "W01--CCC": viz("detailed-W01-C"),
      "W01--DDD": viz("detailed-W01-D"),
    };
    const plates = collectWellPlates(
      {
        wells: [well("W01", -6.5, 108.3)],
        runtimes: {},
        detailedReservoirs: twoScenarios,
        detailedPredictions: {},
        selectedWellId: "W01",
        preferredScenarioId: "W01--DDD",
      },
      stubConverter,
    );
    expect(plates[0].scenarioId).toBe("W01--DDD");
  });
});

describe("fieldFocusCoordinate", () => {
  const wells = [well("W01", -6.5, 108.3), well("W20", -6.9, 108.6)];
  const placement = {
    name: "Jatibarang",
    center_lat: -6.55,
    center_lon: 108.35,
    rotation_deg: 0,
  };

  it("returns the selected well's coordinate", () => {
    expect(
      fieldFocusCoordinate({ kind: "well", id: "W20" }, wells, placement),
    ).toEqual({ latitude: -6.9, longitude: 108.6 });
  });

  it("falls back to the placement when nothing (or a non-well) is selected", () => {
    expect(
      fieldFocusCoordinate({ kind: "none", id: null }, wells, placement),
    ).toEqual({ latitude: -6.55, longitude: 108.35 });
    expect(
      fieldFocusCoordinate({ kind: "source", id: "S1" }, wells, placement),
    ).toEqual({ latitude: -6.55, longitude: 108.35 });
    expect(
      fieldFocusCoordinate({ kind: "well", id: "W99" }, wells, placement),
    ).toEqual({ latitude: -6.55, longitude: 108.35 });
  });

  it("returns null without a placement or matching well", () => {
    expect(fieldFocusCoordinate({ kind: "none", id: null }, wells, null)).toBeNull();
  });
});

describe("maxFrameCount", () => {
  it("returns the maximum frame count across retained predictions", () => {
    expect(maxFrameCount([prediction(3), null, prediction(7), undefined])).toBe(7);
  });

  it("returns 0 for empty or field-less predictions", () => {
    expect(maxFrameCount([])).toBe(0);
    expect(
      maxFrameCount([{ fields: null } as unknown as PredictionResult]),
    ).toBe(0);
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run (from `frontend/`): `npm test -- --run src/viewport/wellPlates.test.ts`
Expected: FAIL — `Cannot find module './wellPlates'` (or equivalent resolve error).

- [ ] **Step 3: Write the implementation**

Create `frontend/src/viewport/wellPlates.ts`:

```ts
import type {
  Coordinate,
  PredictionResult,
  ReservoirVisualization,
} from "../api/types";
import type { ReservoirImportResponse } from "../api/client";
import type { FieldPlacement, PlacedWell } from "../state/field.store";
import type { Selection } from "../state/selection.store";
import { reservoirVisualizationFromImport } from "./ReservoirGrid";
import { framesFromPrediction } from "./plume";

/** One renderable geology plate anchored at a well. */
export interface WellPlateDescriptor {
  wellId: string;
  coordinate: Coordinate;
  /** Retained detailed scenario backing this plate, when one exists. */
  scenarioId: string | null;
  reservoir: ReservoirVisualization;
  /** Only present when detailed fields were retained for the scenario. */
  prediction: PredictionResult | null;
}

export interface WellPlateInputs {
  wells: PlacedWell[];
  runtimes: Record<string, ReservoirImportResponse>;
  detailedReservoirs: Record<string, ReservoirVisualization>;
  detailedPredictions: Record<string, PredictionResult>;
  /** Scenario the user explicitly picked (shortlist click); applies to selectedWellId only. */
  preferredScenarioId?: string | null;
  selectedWellId?: string | null;
}

export function scenarioIdForWell(
  detailedKeys: string[],
  wellId: string,
  preferredScenarioId?: string | null,
): string | null {
  if (
    preferredScenarioId &&
    (preferredScenarioId === wellId ||
      preferredScenarioId.startsWith(`${wellId}--`)) &&
    detailedKeys.includes(preferredScenarioId)
  ) {
    return preferredScenarioId;
  }
  return (
    detailedKeys.find((id) => id === wellId || id.startsWith(`${wellId}--`)) ??
    null
  );
}

// Imported payloads are large and stable for a session; convert each at most once.
const visualizationCache = new WeakMap<
  ReservoirImportResponse,
  ReservoirVisualization | null
>();

export function cachedVisualizationFromImport(
  imported: ReservoirImportResponse | null,
): ReservoirVisualization | null {
  if (!imported) return null;
  if (!visualizationCache.has(imported)) {
    visualizationCache.set(imported, reservoirVisualizationFromImport(imported));
  }
  return visualizationCache.get(imported) ?? null;
}

export function collectWellPlates(
  inputs: WellPlateInputs,
  toVisualization: (
    imported: ReservoirImportResponse | null,
  ) => ReservoirVisualization | null = cachedVisualizationFromImport,
): WellPlateDescriptor[] {
  const detailedKeys = Object.keys(inputs.detailedReservoirs);
  const plates: WellPlateDescriptor[] = [];
  for (const well of inputs.wells) {
    const preferred =
      well.id === inputs.selectedWellId ? inputs.preferredScenarioId : null;
    const scenarioId = scenarioIdForWell(detailedKeys, well.id, preferred);
    const detailed = scenarioId
      ? inputs.detailedReservoirs[scenarioId]
      : undefined;
    const reservoir = detailed ?? toVisualization(inputs.runtimes[well.id] ?? null);
    if (!reservoir) continue;
    plates.push({
      wellId: well.id,
      coordinate: { latitude: well.lat, longitude: well.lon },
      scenarioId: detailed && scenarioId ? scenarioId : null,
      reservoir,
      prediction:
        detailed && scenarioId
          ? (inputs.detailedPredictions[scenarioId] ?? null)
          : null,
    });
  }
  return plates;
}

/** Field-view focus: the selected well when there is one, else the placement. */
export function fieldFocusCoordinate(
  selection: Selection,
  wells: PlacedWell[],
  placement: FieldPlacement | null,
): Coordinate | null {
  if (selection.kind === "well" && selection.id) {
    const well = wells.find((item) => item.id === selection.id);
    if (well) return { latitude: well.lat, longitude: well.lon };
  }
  return placement
    ? { latitude: placement.center_lat, longitude: placement.center_lon }
    : null;
}

/** Global timeline length: the longest retained playback among visible plates. */
export function maxFrameCount(
  predictions: Array<PredictionResult | null | undefined>,
): number {
  return predictions.reduce(
    (count, prediction) =>
      Math.max(count, prediction ? framesFromPrediction(prediction).length : 0),
    0,
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `npm test -- --run src/viewport/wellPlates.test.ts`
Expected: PASS (all tests).

- [ ] **Step 5: Commit**

```bash
git add frontend/src/viewport/wellPlates.ts frontend/src/viewport/wellPlates.test.ts
git commit -m "feat(viewport): pure well-plate descriptor helpers"
```

---

### Task 3: `ReservoirGrid` takes explicit `reservoir`/`prediction` props

Today `ReservoirGrid` reads the ledger + selection internally and its field-view fallback is wired to the **primary** runtime only — selecting W07 in field view silently shows W01's geology. Make the data an explicit prop; the call sites decide what each plate shows. Timeline driving stays inside for this task (exactly one instance still mounts at a time), and is hoisted in Task 4.

**Files:**
- Modify: `frontend/src/viewport/ReservoirGrid.tsx:31-38` (Props), `:220-253` (component body)
- Modify: `frontend/src/viewport/Viewport3D.tsx` — SceneContent (`wellSpot`/`fieldSpot` call sites, currently around lines 490-618)

**Interfaces:**
- Consumes: `scenarioIdForWell`, `cachedVisualizationFromImport` from Task 2.
- Produces: `ReservoirGrid` props — `{ position: [number, number]; groundY: number; metresPerSceneUnit: number; rotation?: [number, number, number]; reservoir: ReservoirVisualization; prediction?: PredictionResult | null }`. `fallbackReservoir` is removed. Tasks 5–6 rely on this signature.

- [ ] **Step 1: Refactor `ReservoirGrid` props**

In `frontend/src/viewport/ReservoirGrid.tsx`, replace the `Props` interface:

```ts
interface Props {
  position: [number, number];
  groundY: number;
  metresPerSceneUnit: number;
  rotation?: [number, number, number];
  /** Static geology for this plate — retained detailed fields or relinked import. */
  reservoir: ReservoirVisualization;
  /** Retained detailed prediction driving plume playback, when available. */
  prediction?: PredictionResult | null;
}
```

Replace the top of the component (the destructuring through the `frames` memo — currently lines 220-254):

```tsx
export function ReservoirGrid({
  position,
  groundY,
  metresPerSceneUnit,
  rotation = [0, 0, 0],
  reservoir,
  prediction = null,
}: Props) {
  const layers = useWorkspaceStore((state) => state.layers);
  const staticField = useWorkspaceStore((state) => state.reservoirStaticField);
  const dynamicField = useWorkspaceStore((state) => state.colorField);
  const verticalExaggeration = useWorkspaceStore((state) => state.reservoirVerticalExaggeration);
  const dynamicOpacity = useWorkspaceStore((state) => state.dynamicOpacity);
  const plumeThreshold = useWorkspaceStore((state) => state.plumeThreshold);
  const step = useWorkspaceStore((state) => state.timelineStep);
  const playing = useWorkspaceStore((state) => state.timelinePlaying);
  const setStep = useWorkspaceStore((state) => state.setTimelineStep);
  const setFrameCount = useWorkspaceStore((state) => state.setTimelineFrameCount);

  const frames = useMemo(
    () => (prediction ? framesFromPrediction(prediction) : []),
    [prediction],
  );
```

Delete the old `activeEntry`, `selection`, `scenarioId`, and `detailedReservoir` declarations and the line `const reservoir = detailedReservoir ?? fallbackReservoir ?? undefined;` — `reservoir` is now the prop. Keep the `setFrameCount` effect, the `useFrame` advance, and everything from `if (!reservoir || !layers.reservoir) return null;` onward unchanged. Remove the now-unused imports `useLedgerStore` and `useSelectionStore`.

- [ ] **Step 2: Compute plate data at the call sites**

In `frontend/src/viewport/Viewport3D.tsx` SceneContent, next to the existing `wellSpot` memo (around line 514), add (imports at top of file: `import { cachedVisualizationFromImport, scenarioIdForWell } from "./wellPlates";` and add `reservoirRuntimes` to the store reads next to the existing `reservoirRuntime` read at line 492):

```tsx
const reservoirRuntimes = useFieldStore((s) => s.reservoirRuntimes);

const detailedKeys = useMemo(
  () => Object.keys(activeEntry?.result.detailed_reservoirs ?? {}),
  [activeEntry],
);
const selectedScenarioId =
  selection.kind === "well" && selection.id
    ? scenarioIdForWell(detailedKeys, selection.id, selection.scenarioId)
    : null;
const selectedDetailed = selectedScenarioId
  ? (activeEntry?.result.detailed_reservoirs?.[selectedScenarioId] ?? null)
  : null;
const selectedPrediction = selectedScenarioId
  ? (activeEntry?.result.detailed_predictions?.[selectedScenarioId] ?? null)
  : null;
// The field plate follows the SELECTED well's relinked artifact — never
// silently substitute the primary model for another well.
const fieldFallback = cachedVisualizationFromImport(
  selection.kind === "well" && selection.id
    ? (reservoirRuntimes[selection.id] ?? reservoirRuntime)
    : reservoirRuntime,
);
```

Replace the two `ReservoirGrid` usages (currently lines 603-618):

```tsx
{level === "basin" && wellSpot && selectedDetailed && (
  <ReservoirGrid
    position={wellSpot.xz}
    groundY={wellSpot.groundY}
    metresPerSceneUnit={projector.metresPerSceneUnit}
    reservoir={selectedDetailed}
    prediction={selectedPrediction}
  />
)}
{fieldSpot && (selectedDetailed ?? fieldFallback) && (
  <ReservoirGrid
    position={fieldSpot.xz}
    groundY={fieldSpot.groundY}
    metresPerSceneUnit={projector.metresPerSceneUnit}
    rotation={fieldSpot.rotation}
    reservoir={(selectedDetailed ?? fieldFallback)!}
    prediction={selectedDetailed ? selectedPrediction : null}
  />
)}
```

Delete SceneContent's now-unused `importedReservoir` memo (lines 494-497) if nothing else references it.

- [ ] **Step 3: Verify types and full suite**

Run (from `frontend/`): `npx tsc -b` then `npm test -- --run`
Expected: tsc clean; all tests pass (177+ plus Task 2's new file).

- [ ] **Step 4: Commit**

```bash
git add frontend/src/viewport/ReservoirGrid.tsx frontend/src/viewport/Viewport3D.tsx
git commit -m "refactor(viewport): explicit reservoir props for ReservoirGrid and per-well field fallback"
```

---

### Task 4: Hoist timeline driving into a single `TimelineDriver`

`ReservoirGrid` currently calls `setTimelineFrameCount` in an effect and advances `timelineStep` in `useFrame`. With N mounted plates (Task 5) each instance would advance the shared step — N× speed — and their mount/unmount effects would fight over the frame count. One driver owns both.

**Files:**
- Create: `frontend/src/viewport/TimelineDriver.tsx`
- Modify: `frontend/src/viewport/ReservoirGrid.tsx` (remove timeline effect + advance)
- Modify: `frontend/src/viewport/Viewport3D.tsx` (mount driver in SceneContent)

**Interfaces:**
- Consumes: `maxFrameCount` from Task 2; workspace store timeline API (`setTimelineFrameCount`, `setTimelineStep`, `timelinePlaying`, `timelineStep`).
- Produces: `TimelineDriver({ predictions }: { predictions: Array<PredictionResult | null | undefined> })` — must be mounted **inside the r3f Canvas** (it uses `useFrame`). Task 5 feeds it every visible plate's prediction.

- [ ] **Step 1: Create the driver**

Create `frontend/src/viewport/TimelineDriver.tsx`:

```tsx
import { useEffect, useMemo, useRef } from "react";
import { useFrame } from "@react-three/fiber";
import type { PredictionResult } from "../api/types";
import { useWorkspaceStore } from "../state/workspace.store";
import { maxFrameCount } from "./wellPlates";

/**
 * The single owner of the global playback timeline. Exactly one instance is
 * mounted inside the Canvas; individual reservoir plates only READ the step.
 */
export function TimelineDriver({
  predictions,
}: {
  predictions: Array<PredictionResult | null | undefined>;
}) {
  const playing = useWorkspaceStore((state) => state.timelinePlaying);
  const step = useWorkspaceStore((state) => state.timelineStep);
  const setStep = useWorkspaceStore((state) => state.setTimelineStep);
  const setFrameCount = useWorkspaceStore((state) => state.setTimelineFrameCount);

  const count = useMemo(() => maxFrameCount(predictions), [predictions]);

  useEffect(() => {
    setFrameCount(count);
    return () => setFrameCount(0);
  }, [count, setFrameCount]);

  const accumulator = useRef(0);
  useFrame((_, delta) => {
    if (!playing || count === 0) return;
    accumulator.current += delta;
    if (accumulator.current > 0.18) {
      accumulator.current = 0;
      setStep((step + 1) % count);
    }
  });

  return null;
}
```

- [ ] **Step 2: Strip timeline driving from `ReservoirGrid`**

In `frontend/src/viewport/ReservoirGrid.tsx` delete:
- the `playing`, `setStep`, and `setFrameCount` store reads,
- the `useEffect` that calls `setFrameCount(frames.length)`,
- the `accumulator` ref and the whole `useFrame((_, delta) => { ... })` block.

Keep the `step` read and `const frame = frameAtStep(frames, step);`. Remove `useFrame` from the r3f import if now unused (`useEffect`/`useRef` may also drop out of the React import — remove any import tsc flags as unused).

- [ ] **Step 3: Mount the driver in SceneContent**

In `frontend/src/viewport/Viewport3D.tsx` SceneContent, add below the `fieldFallback` computation from Task 3:

```tsx
const driverPredictions = useMemo(
  () => [selectedDetailed ? selectedPrediction : null],
  [selectedDetailed, selectedPrediction],
);
```

and render, as the first child inside the returned `<group>` (import `TimelineDriver` at top of file):

```tsx
<TimelineDriver predictions={driverPredictions} />
```

- [ ] **Step 4: Verify types and full suite**

Run: `npx tsc -b` then `npm test -- --run`
Expected: clean / all pass.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/viewport/TimelineDriver.tsx frontend/src/viewport/ReservoirGrid.tsx frontend/src/viewport/Viewport3D.tsx
git commit -m "refactor(viewport): single timeline driver for plume playback"
```

---

### Task 5: Per-well plates in basin view with simultaneous playback

Replace the single selected-well cutaway with one plate per `WellPlateDescriptor`: every well with a relinked runtime shows its own static geology; every well with retained detailed predictions animates on the shared timeline.

**Files:**
- Modify: `frontend/src/viewport/Viewport3D.tsx` — SceneContent only

**Interfaces:**
- Consumes: `collectWellPlates` (Task 2), `ReservoirGrid` explicit props (Task 3), `TimelineDriver` (Task 4).
- Produces: `plates: WellPlateDescriptor[]` memo inside SceneContent — Task 6 reuses it for the field-view focused plate.

- [ ] **Step 1: Build the plate list and positions**

In SceneContent, replace the Task 3 `selectedScenarioId`/`selectedDetailed`/`selectedPrediction`/`fieldFallback` block AND the `wellSpot` memo (lines ~514-520) with:

```tsx
const plates = useMemo(
  () =>
    collectWellPlates({
      wells: fieldWells,
      runtimes: reservoirRuntimes,
      detailedReservoirs: activeEntry?.result.detailed_reservoirs ?? {},
      detailedPredictions: activeEntry?.result.detailed_predictions ?? {},
      preferredScenarioId:
        selection.kind === "well" ? (selection.scenarioId ?? null) : null,
      selectedWellId: selection.kind === "well" ? selection.id : null,
    }),
  [activeEntry, fieldWells, reservoirRuntimes, selection],
);

const platePositions = useMemo(
  () =>
    plates.map((plate) => {
      const [x, z] = projector.toXZ(plate.coordinate);
      return {
        plate,
        xz: [x, z] as [number, number],
        groundY: projector.heightOf(
          projector.elevationAt(plate.coordinate),
          exaggeration,
        ),
      };
    }),
  [exaggeration, plates, projector],
);

const driverPredictions = useMemo(
  () => plates.map((plate) => plate.prediction),
  [plates],
);
```

(`collectWellPlates` import joins the Task 3 import from `./wellPlates`; `scenarioIdForWell` and `cachedVisualizationFromImport` imports can be dropped from Viewport3D if now unused.)

- [ ] **Step 2: Render one plate per well in basin view**

Replace the basin `ReservoirGrid` block from Task 3 (`{level === "basin" && wellSpot && selectedDetailed && (...)}`) with:

```tsx
{level === "basin" &&
  platePositions.map(({ plate, xz, groundY }) => (
    <ReservoirGrid
      key={plate.wellId}
      position={xz}
      groundY={groundY}
      metresPerSceneUnit={projector.metresPerSceneUnit}
      rotation={[0, -(placement?.rotation_deg ?? 0) * DEG2RAD, 0]}
      reservoir={plate.reservoir}
      prediction={plate.prediction}
    />
  ))}
```

For the **field-level** plate, keep it working with the plate list (Task 6 moves its anchor):

```tsx
{fieldSpot &&
  (() => {
    const focused =
      plates.find(
        (plate) =>
          plate.wellId ===
          (selection.kind === "well" && selection.id
            ? selection.id
            : fieldWells[0]?.id),
      ) ?? null;
    return focused ? (
      <ReservoirGrid
        position={fieldSpot.xz}
        groundY={fieldSpot.groundY}
        metresPerSceneUnit={projector.metresPerSceneUnit}
        rotation={fieldSpot.rotation}
        reservoir={focused.reservoir}
        prediction={focused.prediction}
      />
    ) : null;
  })()}
```

- [ ] **Step 3: Verify types and full suite**

Run: `npx tsc -b` then `npm test -- --run`
Expected: clean / all pass.

- [ ] **Step 4: Manual smoke (dev server)**

With backend + frontend running and the 20-well memo open (`output/playwright/jatibarang-20well-final.study.json`): at basin level all 20 wells show geology plates; pressing play animates every shortlisted/retained well at once; unchecking Layers → "Reservoir cells" hides all plates.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/viewport/Viewport3D.tsx
git commit -m "feat(viewport): per-well geology plates with simultaneous plume playback"
```

---

### Task 6: Field view frames the selected well

`CameraRig` short-circuits every framing request in field view back to the placement, and the high-res terrain window is fetched around the placement — so "Field" always lands on the W01 area no matter what is selected. Focus becomes: selected well if any, else placement.

**Files:**
- Modify: `frontend/src/viewport/Viewport3D.tsx` — the field-window effect (lines ~113-150), SceneContent `fieldSpot` (lines ~522-541), `CameraRig` `fieldTarget` (lines ~1394-1403)

**Interfaces:**
- Consumes: `fieldFocusCoordinate(selection, wells, placement)` from Task 2; `plates` memo from Task 5.
- Produces: no new exports — behavior change only.

- [ ] **Step 1: Center the field terrain window on the focus**

In the `Viewport3D` component (top level), add near the existing store reads (imports: add `fieldFocusCoordinate` to the `./wellPlates` import):

```tsx
const fieldFocus = useMemo(
  () => fieldFocusCoordinate(selection, wells, placement),
  [placement, selection, wells],
);
```

In the field-window effect (currently lines 113-150), replace

```tsx
    if (!terrain || !placement || !reservoir) return;
```

with

```tsx
    if (!terrain || !fieldFocus || !reservoir) return;
```

and

```tsx
    const bounds = fieldWindowBounds(
      { latitude: placement.center_lat, longitude: placement.center_lon },
      reservoir,
    );
```

with

```tsx
    const bounds = fieldWindowBounds(fieldFocus, reservoir);
```

and change the dependency array from `[level, placement, reservoir, terrain]` to `[fieldFocus, level, reservoir, terrain]`. (Selecting a different well while in field view now reloads the window around it.)

- [ ] **Step 2: Anchor `fieldSpot` at the focus**

In SceneContent, add the same `fieldFocus` memo (SceneContent has its own `selection`, `fieldWells`, `placement` reads):

```tsx
const fieldFocus = useMemo(
  () => fieldFocusCoordinate(selection, fieldWells, placement),
  [fieldWells, placement, selection],
);
```

and replace the `fieldSpot` memo (lines ~522-541) with:

```tsx
const fieldSpot = useMemo(() => {
  if (level !== "field" || !fieldFocus || !placement || !reservoir) return null;
  const [x, z] = projector.toXZ(fieldFocus);
  return {
    xz: [x, z] as [number, number],
    groundY: projector.heightOf(
      projector.elevationAt(fieldFocus),
      exaggeration,
    ),
    rotation: [0, -placement.rotation_deg * DEG2RAD, 0] as [
      number,
      number,
      number,
    ],
  };
}, [exaggeration, fieldFocus, level, placement, projector, reservoir]);
```

- [ ] **Step 3: Aim the camera at the focus**

In `CameraRig`, add a wells read next to the existing `placement` read:

```tsx
const wells = useFieldStore((state) => state.wells);
```

and replace the `fieldTarget` memo (lines ~1394-1403) with:

```tsx
const fieldTarget = useMemo(() => {
  if (level !== "field") return null;
  const coordinate = fieldFocusCoordinate(selection, wells, placement);
  if (!coordinate) return null;
  const [x, z] = projector.toXZ(coordinate);
  const y = projector.heightOf(projector.elevationAt(coordinate), exaggeration);
  return new THREE.Vector3(x, y + 0.08, z);
}, [exaggeration, level, placement, projector, selection, wells]);
```

(`fieldFocusCoordinate` is already imported at file top from Step 1.)

- [ ] **Step 4: Verify types and full suite**

Run: `npx tsc -b` then `npm test -- --run`
Expected: clean / all pass.

- [ ] **Step 5: Manual smoke (dev server)**

Open the 20-well memo, select W20 in the wells rail, click "Field ▸": the high-res window loads around W20, the camera frames W20's plate, and the plate shows W20's own geology (inspector artifact id matches). Clicking W05 while still in field view refocuses to W05. With nothing selected, Field opens on the placement as before.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/viewport/Viewport3D.tsx
git commit -m "feat(viewport): field view frames the selected well"
```

---

### Task 7: Whole-feature verification

**Files:** none (verification only; fix regressions in place if found)

- [ ] **Step 1: Full frontend gates**

Run from `frontend/`: `npm test -- --run` then `npx tsc -b` then `npm run build`
Expected: all tests pass, tsc clean, build succeeds.

- [ ] **Step 2: Restart the stack cleanly**

Close the "Fieldman Frontend :5173" window if the Vite config change from Task 1 has not been picked up yet, re-run `start_workbench.bat` (backend :8000 may stay up — no backend changes).

- [ ] **Step 3: Manual QA checklist against the 20-well memo**

Open `output/playwright/jatibarang-20well-final.study.json`, then confirm:
1. **No** "road network could not be found" banner; basin view shows roads, coastline, and place labels (Jatibarang, Indramayu…) when their layer checkboxes are on.
2. Trucking routes follow roads (solid road-following polyline), not the dashed great-circle fallback.
3. All 20 wells show their own geology plates in basin view; wells without relinked artifacts (if any) show none.
4. Press play: every retained well animates simultaneously; the scrubber drives all plates.
5. Select W20 → Field: camera and terrain window center on W20 with W20's geology.
6. Escape exits field → basin; basin selection framing still works.

- [ ] **Step 4: Commit any residual fixes**

```bash
git status
```

If Steps 1-3 forced code changes, commit them with a `fix(viewport): ...` message describing what regressed.

---

## Self-Review

- **Spec coverage:** labels/coastline → Task 1; per-well geology for all relinked wells → Tasks 2, 3, 5; simultaneous playback on retained wells → Tasks 4, 5; field view focuses the selected well (and shows its geology, fixing the W01-only fallback) → Tasks 3, 6. Verified against the four user requirements.
- **Placeholder scan:** all code steps carry complete code; no TBDs.
- **Type consistency:** `WellPlateDescriptor`/`collectWellPlates`/`fieldFocusCoordinate`/`maxFrameCount`/`cachedVisualizationFromImport`/`scenarioIdForWell` names and signatures match across Tasks 2-6; `ReservoirGrid` props defined in Task 3 are what Tasks 5-6 pass.
