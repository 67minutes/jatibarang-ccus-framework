import type {
  HealthResponse,
  PresetInfo,
  ScreenRequest,
  ScreenResult,
  ValidationErrorItem,
} from "./types";
import type { TerrainData } from "../viewport/terrain";

/**
 * Typed API client for the Feature 005 backend. In dev, Vite proxies these
 * paths to the FastAPI server; in production the SPA is served by that same
 * process so the relative paths resolve directly.
 */

/** HTTP error carrying the status and (for 422) the field-level detail. */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
    readonly detail?: ValidationErrorItem[] | string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseError(response: Response): Promise<ApiError> {
  let detail: ValidationErrorItem[] | string | undefined;
  let message = `${response.status} ${response.statusText}`;
  try {
    const body = await response.json();
    if (body && typeof body === "object" && "detail" in body) {
      detail = (body as { detail: ValidationErrorItem[] | string }).detail;
      if (typeof detail === "string") message = detail;
    }
  } catch {
    // Non-JSON error body; keep the status-line message.
  }
  return new ApiError(response.status, message, detail);
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path, { headers: { Accept: "application/json" } });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(path, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health");
}

export function getPresets(): Promise<PresetInfo[]> {
  return getJson<PresetInfo[]>("/presets");
}

export interface TerrainExtent {
  minLon: number;
  minLat: number;
  maxLon: number;
  maxLat: number;
}

export interface TerrainImportResponse {
  terrain_id: string;
  sha256: string;
  extent: TerrainExtent;
  cell_size_m: number;
  overview: TerrainData;
}

export interface RegisteredTerrain {
  terrain_id: string;
  sha256: string;
  source_path: string;
  extent: TerrainExtent;
  cell_size_m: number;
}

export function importTerrain(path: string): Promise<TerrainImportResponse> {
  return postJson<TerrainImportResponse>("/terrain/import", { path });
}

export function listTerrains(): Promise<RegisteredTerrain[]> {
  return getJson<RegisteredTerrain[]>("/terrain");
}

export function getTerrainWindow(
  terrainId: string,
  bounds: TerrainExtent,
  maxPx = 768,
): Promise<TerrainData> {
  const query = new URLSearchParams({
    min_lon: String(bounds.minLon),
    min_lat: String(bounds.minLat),
    max_lon: String(bounds.maxLon),
    max_lat: String(bounds.maxLat),
    max_px: String(maxPx),
  });
  return getJson<TerrainData>(
    `/terrain/${encodeURIComponent(terrainId)}/window?${query.toString()}`,
  );
}

export interface ReservoirImportResponse {
  model_id: string;
  sha256: string;
  source_file: string;
  geology: Record<string, unknown>;
  native_schedule: Record<string, number>;
  native_fingerprint: string;
  /** Runtime-only launch-pad payload; never copied into a study memo. */
  native_seed: Record<string, unknown>;
  /** Runtime-only launch-pad payloads keyed by schedule fingerprint. */
  bank_seeds: Record<string, Record<string, unknown>>;
  well_ij: [number, number];
  completion_ij: [number, number][];
  launchpads: {
    bank_id: string | null;
    bank_sha256: string | null;
    covered_fingerprints: string[];
  };
}

export function importReservoir(
  modelPath: string,
  bankPath?: string | null,
): Promise<ReservoirImportResponse> {
  return postJson<ReservoirImportResponse>("/reservoir/import", {
    model_path: modelPath,
    bank_path: bankPath ?? null,
  });
}

/** Synchronous screening (SSE fallback path). */
export async function postScreen(request: ScreenRequest): Promise<ScreenResult> {
  return postJson<ScreenResult>("/screen", request);
}

/** Cooperative cancellation of an active streaming run. */
export async function deleteRun(runId: string): Promise<void> {
  const response = await fetch(`/screen/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });
  // 404 (run already finished) is acceptable for a cancel request.
  if (!response.ok && response.status !== 404) throw await parseError(response);
}
