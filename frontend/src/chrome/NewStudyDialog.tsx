import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type ChangeEvent,
  type FormEvent,
} from "react";
import {
  getTerrainWindow,
  importReservoir,
  importTerrain,
  listTerrains,
  type RegisteredTerrain,
  type ReservoirImportResponse,
} from "../api/client";
import { DEFAULT_OPERATIONAL_GRID } from "../compose/defaults";
import {
  studySchedulePlan,
  type StudySchedulePlan,
} from "../compose/studyRequest";
import { useActionsStore } from "../state/actions.store";
import {
  useFieldStore,
  type ReservoirRef,
  type TerrainRef,
} from "../state/field.store";
import { useRunStore } from "../state/run.store";
import {
  DEFAULT_STUDY_NAME,
  useStudyStore,
} from "../state/study.store";
import { applyWellsCsvRows, parseWellsCsv } from "./wellsCsv";

const IMPORT_TERRAIN = "__import__";

function fileLabel(path: string): string {
  return path.split(/[\\/]/).filter(Boolean).at(-1) ?? path;
}

function midpoint(extent: RegisteredTerrain["extent"]): [number, number] {
  return [
    (extent.minLat + extent.maxLat) / 2,
    (extent.minLon + extent.maxLon) / 2,
  ];
}

function requiredGeologyNumber(
  geology: Record<string, unknown>,
  field: "length_x_m" | "length_y_m",
): number {
  const value = geology[field];
  if (typeof value !== "number" || !Number.isFinite(value) || value <= 0) {
    throw new Error(`Imported reservoir model is missing a valid ${field}.`);
  }
  return value;
}

export function reservoirRefFromImport(
  imported: ReservoirImportResponse,
): ReservoirRef {
  return {
    model_id: imported.model_id,
    sha256: imported.sha256,
    source_file: imported.source_file,
    native_fingerprint: imported.native_fingerprint,
    covered_fingerprints: [...imported.launchpads.covered_fingerprints],
    bank_id: imported.launchpads.bank_id,
    well_ij: [...imported.well_ij],
    length_x_m: requiredGeologyNumber(imported.geology, "length_x_m"),
    length_y_m: requiredGeologyNumber(imported.geology, "length_y_m"),
  };
}

function terrainRefFromRecord(record: RegisteredTerrain): TerrainRef {
  return {
    terrain_id: record.terrain_id,
    sha256: record.sha256,
    source_path: record.source_path,
    extent: { ...record.extent },
  };
}

function finiteCoordinate(
  raw: string,
  label: string,
  minimum: number,
  maximum: number,
): number {
  const value = Number(raw);
  if (!Number.isFinite(value) || value < minimum || value > maximum) {
    throw new Error(`${label} must be between ${minimum} and ${maximum}.`);
  }
  return value;
}

function messageFrom(error: unknown): string {
  return error instanceof Error ? error.message : "The import could not be completed.";
}

interface LaunchPadCoveragePreview {
  plan: StudySchedulePlan | null;
  error: string | null;
}

/**
 * Keep model inspection resilient to older or incomplete import payloads. A
 * malformed preview must not take down the New Study dialog; final request
 * construction still performs the same strict validation before screening.
 */
export function launchPadCoveragePreview(
  imported: ReservoirImportResponse,
): LaunchPadCoveragePreview {
  try {
    return {
      plan: studySchedulePlan(DEFAULT_OPERATIONAL_GRID, imported),
      error: null,
    };
  } catch (error) {
    return { plan: null, error: messageFrom(error) };
  }
}

export function NewStudyDialog({ onDone }: { onDone: () => void }) {
  const createNewStudy = useActionsStore((state) => state.actions.createNewStudy);
  const current = useStudyStore((state) => state.study);
  const runStatus = useRunStore((state) => state.status);
  const mounted = useRef(true);

  const [name, setName] = useState(
    current.name === DEFAULT_STUDY_NAME ? "" : current.name,
  );
  const [analyst, setAnalyst] = useState(current.analyst);
  const [notes, setNotes] = useState("");
  const [memoName, setMemoName] = useState("");
  const [memoTouched, setMemoTouched] = useState(false);
  const [startView, setStartView] = useState<"2d" | "3d">("3d");
  const [exaggeration, setExaggeration] = useState(5);

  const [terrains, setTerrains] = useState<RegisteredTerrain[]>([]);
  const [terrainSelection, setTerrainSelection] = useState(IMPORT_TERRAIN);
  const [terrainPath, setTerrainPath] = useState("");
  const [terrainOverview, setTerrainOverview] = useState<{
    terrainId: string;
    data: Awaited<ReturnType<typeof getTerrainWindow>>;
  } | null>(null);
  const [terrainLoading, setTerrainLoading] = useState(true);
  const [terrainImporting, setTerrainImporting] = useState(false);
  const [terrainError, setTerrainError] = useState<string | null>(null);

  const [modelPath, setModelPath] = useState("");
  const [bankPath, setBankPath] = useState("");
  const [reservoirImporting, setReservoirImporting] = useState(false);
  const [reservoirError, setReservoirError] = useState<string | null>(null);
  const [reservoirImportResult, setReservoirImportResult] =
    useState<ReservoirImportResponse | null>(null);
  const [reservoirImportKey, setReservoirImportKey] = useState<string | null>(null);

  const [centerLat, setCenterLat] = useState("");
  const [centerLon, setCenterLon] = useState("");
  const [rotation, setRotation] = useState("0");
  const [wellsCsv, setWellsCsv] = useState("");
  const [wellsError, setWellsError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const runActive = runStatus === "running" || runStatus === "stalled";
  const pending = terrainImporting || reservoirImporting || submitting;
  const currentReservoirKey = `${modelPath.trim()}\n${bankPath.trim()}`;

  const suggestedMemo = useMemo(() => {
    if (memoTouched && memoName.trim()) return memoName.trim();
    const stem = name
      .trim()
      .replace(/[^a-z0-9._-]+/gi, "_")
      .replace(/^_+|_+$/g, "")
      .toLowerCase();
    return `${stem || "untitled-study"}.study.json`;
  }, [memoName, memoTouched, name]);

  const coveragePreview = useMemo(
    () =>
      reservoirImportResult
        ? launchPadCoveragePreview(reservoirImportResult)
        : null,
    [reservoirImportResult],
  );

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    void listTerrains()
      .then((records) => {
        if (cancelled) return;
        setTerrains(records);
        if (records.length > 0) {
          setTerrainSelection(records[0].terrain_id);
          const [lat, lon] = midpoint(records[0].extent);
          setCenterLat(String(lat));
          setCenterLon(String(lon));
        }
      })
      .catch((error: unknown) => {
        if (!cancelled) setTerrainError(messageFrom(error));
      })
      .finally(() => {
        if (!cancelled) setTerrainLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  function selectTerrain(terrainId: string) {
    setTerrainSelection(terrainId);
    setTerrainError(null);
    if (terrainOverview?.terrainId !== terrainId) setTerrainOverview(null);
    const record = terrains.find((item) => item.terrain_id === terrainId);
    if (record) {
      const [lat, lon] = midpoint(record.extent);
      setCenterLat(String(lat));
      setCenterLon(String(lon));
    }
  }

  async function registerTerrain() {
    const path = terrainPath.trim();
    if (!path) {
      setTerrainError("Enter the backend-visible path to a GeoTIFF.");
      return;
    }
    setTerrainImporting(true);
    setTerrainError(null);
    try {
      const imported = await importTerrain(path);
      const records = await listTerrains();
      const record = records.find(
        (item) => item.terrain_id === imported.terrain_id,
      );
      if (!record) {
        throw new Error("The terrain was imported but is absent from the registry.");
      }
      if (!mounted.current) return;
      setTerrains(records);
      setTerrainSelection(record.terrain_id);
      setTerrainOverview({ terrainId: record.terrain_id, data: imported.overview });
      const [lat, lon] = midpoint(record.extent);
      setCenterLat(String(lat));
      setCenterLon(String(lon));
    } catch (error) {
      if (mounted.current) setTerrainError(messageFrom(error));
    } finally {
      if (mounted.current) setTerrainImporting(false);
    }
  }

  async function loadReservoir(): Promise<ReservoirImportResponse | null> {
    const path = modelPath.trim();
    if (!path) {
      setReservoirError("Enter the backend-visible path to an MRST .mat model.");
      return null;
    }
    const key = currentReservoirKey;
    setReservoirImporting(true);
    setReservoirError(null);
    try {
      const imported = await importReservoir(path, bankPath.trim() || null);
      if (!mounted.current) return null;
      setReservoirImportResult(imported);
      setReservoirImportKey(key);
      return imported;
    } catch (error) {
      if (mounted.current) setReservoirError(messageFrom(error));
      return null;
    } finally {
      if (mounted.current) setReservoirImporting(false);
    }
  }

  function invalidateReservoirImport() {
    setReservoirImportResult(null);
    setReservoirImportKey(null);
    setReservoirError(null);
  }

  async function readWellsFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    setWellsError(null);
    try {
      setWellsCsv(await file.text());
    } catch {
      setWellsError("The selected wells CSV could not be read.");
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFormError(null);
    setWellsError(null);

    if (!createNewStudy) {
      setFormError("The workbench is still initializing. Try again in a moment.");
      return;
    }
    const currentRun = useRunStore.getState().status;
    if (currentRun === "running" || currentRun === "stalled") {
      setFormError("Finish or cancel the active screening run first.");
      return;
    }
    const fieldName = name.trim();
    if (!fieldName) {
      setFormError("Field / reservoir name is required.");
      return;
    }
    if (!modelPath.trim()) {
      setFormError("Reservoir model path is required.");
      return;
    }
    const terrainRecord = terrains.find(
      (item) => item.terrain_id === terrainSelection,
    );
    if (!terrainRecord) {
      setFormError("Select or import a registered terrain.");
      return;
    }

    let csvRows: ReturnType<typeof parseWellsCsv> = [];
    try {
      if (wellsCsv.trim()) csvRows = parseWellsCsv(wellsCsv);
    } catch (error) {
      setWellsError(messageFrom(error));
      return;
    }

    let latitude: number;
    let longitude: number;
    let rotationDegrees: number;
    try {
      latitude = finiteCoordinate(centerLat, "Center latitude", -90, 90);
      longitude = finiteCoordinate(centerLon, "Center longitude", -180, 180);
      rotationDegrees = finiteCoordinate(rotation, "Rotation", -360, 360);
    } catch (error) {
      setFormError(messageFrom(error));
      return;
    }

    setSubmitting(true);
    try {
      const overview =
        terrainOverview?.terrainId === terrainRecord.terrain_id
          ? terrainOverview.data
          : await getTerrainWindow(
              terrainRecord.terrain_id,
              terrainRecord.extent,
              512,
            );
      if (!mounted.current) return;
      const importedReservoir =
        reservoirImportResult && reservoirImportKey === currentReservoirKey
          ? reservoirImportResult
          : await importReservoir(modelPath.trim(), bankPath.trim() || null);
      if (!mounted.current) return;

      const field = useFieldStore.getState();
      field.setup(
        terrainRefFromRecord(terrainRecord),
        reservoirRefFromImport(importedReservoir),
        {
          name: fieldName,
          center_lat: latitude,
          center_lon: longitude,
          rotation_deg: ((rotationDegrees % 360) + 360) % 360,
        },
        overview,
        importedReservoir,
      );
      applyWellsCsvRows(csvRows, useFieldStore.getState());
      createNewStudy({
        name: fieldName,
        analyst,
        notes,
        memoFileName: suggestedMemo,
        startView,
        verticalExaggeration: exaggeration,
      });
      useFieldStore.getState().exitField();
      onDone();
    } catch (error) {
      if (mounted.current) setFormError(messageFrom(error));
    } finally {
      if (mounted.current) setSubmitting(false);
    }
  }

  return (
    <form className="dialog-form" onSubmit={submit}>
      <p className="dialog-intro">
        Register terrain and one reservoir model, place the field, then build a
        screening study from explicit engineering inputs.
      </p>

      <div className="dialog-grid">
        <label className="dialog-field dialog-field-wide">
          <span>Field / reservoir name</span>
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Required"
            autoFocus
            required
          />
        </label>
        <label className="dialog-field">
          <span>Analyst</span>
          <input
            value={analyst}
            onChange={(event) => setAnalyst(event.target.value)}
            placeholder="Optional"
          />
        </label>
        <label className="dialog-field">
          <span>Terrain</span>
          <select
            value={terrainSelection}
            onChange={(event) => selectTerrain(event.target.value)}
            disabled={terrainLoading || pending}
          >
            {terrains.map((terrain) => (
              <option key={terrain.terrain_id} value={terrain.terrain_id}>
                {fileLabel(terrain.source_path)} · {terrain.sha256.slice(0, 8)}
              </option>
            ))}
            <option value={IMPORT_TERRAIN}>Import GeoTIFF…</option>
          </select>
        </label>

        {terrainSelection === IMPORT_TERRAIN ? (
          <div className="dialog-field dialog-field-wide">
            <span>GeoTIFF path</span>
            <div className="dialog-inline">
              <input
                value={terrainPath}
                onChange={(event) => setTerrainPath(event.target.value)}
                placeholder="C:\\path\\to\\terrain.tif"
                disabled={pending}
                aria-label="GeoTIFF path"
              />
              <button
                type="button"
                className="btn"
                onClick={() => void registerTerrain()}
                disabled={pending || !terrainPath.trim()}
              >
                {terrainImporting ? "Importing…" : "Import terrain"}
              </button>
            </div>
            <small>The path must be readable by the local backend.</small>
          </div>
        ) : null}
        {terrainError ? <p className="dialog-error dialog-field-wide">{terrainError}</p> : null}

        <div className="dialog-field dialog-field-wide">
          <span>Reservoir model</span>
          <div className="dialog-inline">
            <input
              value={modelPath}
              onChange={(event) => {
                setModelPath(event.target.value);
                invalidateReservoirImport();
              }}
              placeholder="C:\\path\\to\\reservoir.mat"
              disabled={pending}
              aria-label="Reservoir model path"
              required
            />
            <button
              type="button"
              className="btn"
              onClick={() => void loadReservoir()}
              disabled={pending || !modelPath.trim()}
            >
              {reservoirImporting ? "Inspecting…" : "Inspect model"}
            </button>
          </div>
        </div>
        <label className="dialog-field dialog-field-wide">
          <span>Launch-pad bank</span>
          <input
            value={bankPath}
            onChange={(event) => {
              setBankPath(event.target.value);
              invalidateReservoirImport();
            }}
            placeholder="Optional .npz path"
            disabled={pending}
          />
          <small>
            Without a bank, screening is limited to the model&apos;s native schedule.
          </small>
        </label>
        {reservoirError ? (
          <p className="dialog-error dialog-field-wide">{reservoirError}</p>
        ) : null}
        <div className="dialog-status dialog-field-wide" aria-live="polite">
          {coveragePreview?.plan ? (
            <>
              <strong>
                {coveragePreview.plan.coverage.covered.toLocaleString()} of{" "}
                {coveragePreview.plan.coverage.total.toLocaleString()}
              </strong>{" "}
              grid schedules have launch pads.
              {coveragePreview.plan.native.available &&
              !coveragePreview.plan.native.onGrid ? (
                <span>
                  {" "}The native schedule is real and runnable, but outside the
                  active grid.
                </span>
              ) : null}
            </>
          ) : coveragePreview?.error ? (
            <>
              Launch-pad coverage preview unavailable: {coveragePreview.error}
            </>
          ) : (
            <>Inspect the reservoir model to preview launch-pad coverage.</>
          )}
        </div>

        <label className="dialog-field">
          <span>Center latitude</span>
          <input
            type="number"
            step="any"
            value={centerLat}
            onChange={(event) => setCenterLat(event.target.value)}
            required
          />
        </label>
        <label className="dialog-field">
          <span>Center longitude</span>
          <input
            type="number"
            step="any"
            value={centerLon}
            onChange={(event) => setCenterLon(event.target.value)}
            required
          />
        </label>
        <label className="dialog-field">
          <span>Field rotation (degrees)</span>
          <input
            type="number"
            min={-360}
            max={360}
            step="any"
            value={rotation}
            onChange={(event) => setRotation(event.target.value)}
            required
          />
          <small>The field outline remains draggable and rotatable later.</small>
        </label>
        <label className="dialog-field">
          <span>Wells CSV file</span>
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(event) => void readWellsFile(event)}
          />
          <small>Optional header: id,lat,lon. W01 remains model-derived.</small>
        </label>
        <label className="dialog-field dialog-field-wide">
          <span>Wells CSV paste</span>
          <textarea
            rows={3}
            value={wellsCsv}
            onChange={(event) => {
              setWellsCsv(event.target.value);
              setWellsError(null);
            }}
            placeholder={"id,lat,lon\nW02,-6.47,108.31"}
          />
        </label>
        {wellsError ? <p className="dialog-error dialog-field-wide">{wellsError}</p> : null}

        <label className="dialog-field">
          <span>Initial viewport</span>
          <select
            value={startView}
            onChange={(event) => setStartView(event.target.value as "2d" | "3d")}
          >
            <option value="3d">3D field twin</option>
            <option value="2d">2D map</option>
          </select>
        </label>
        <label className="dialog-field">
          <span>Terrain exaggeration</span>
          <select
            value={exaggeration}
            onChange={(event) => setExaggeration(Number(event.target.value))}
          >
            {[1, 2, 5, 10].map((value) => (
              <option key={value} value={value}>
                {value}{"\u00d7"}
              </option>
            ))}
          </select>
        </label>
        <label className="dialog-field dialog-field-wide">
          <span>Study memo file name</span>
          <input
            value={suggestedMemo}
            onChange={(event) => {
              setMemoTouched(true);
              setMemoName(event.target.value);
            }}
          />
        </label>
        <label className="dialog-field dialog-field-wide">
          <span>Save location</span>
          <input
            value="Choose a folder when Save Study is used"
            readOnly
            aria-readonly="true"
          />
          <small>
            The browser&apos;s native save dialog chooses the location on first save.
          </small>
        </label>
        <label className="dialog-field dialog-field-wide">
          <span>Study notes</span>
          <textarea
            rows={2}
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            placeholder="Decision context or assumptions (optional)"
          />
        </label>
      </div>

      {runActive ? (
        <p className="dialog-error">
          Finish or cancel the active screening run before creating a new study.
        </p>
      ) : null}
      {formError ? <p className="dialog-error" role="alert">{formError}</p> : null}

      <footer className="dialog-actions">
        <button type="button" className="btn" onClick={onDone} disabled={pending}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn btn-accent"
          disabled={
            pending ||
            runActive ||
            !name.trim() ||
            !modelPath.trim() ||
            terrainSelection === IMPORT_TERRAIN ||
            !createNewStudy
          }
        >
          {submitting ? "Creating…" : "Create Study"}
        </button>
      </footer>
    </form>
  );
}
