import type {
  HealthResponse,
  PresetInfo,
  ScreenRequest,
  ScreenResult,
  ValidationErrorItem,
} from "./types";

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

export function getHealth(): Promise<HealthResponse> {
  return getJson<HealthResponse>("/health");
}

export function getPresets(): Promise<PresetInfo[]> {
  return getJson<PresetInfo[]>("/presets");
}

/** Synchronous screening (SSE fallback path). */
export async function postScreen(request: ScreenRequest): Promise<ScreenResult> {
  const response = await fetch("/screen", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/json" },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw await parseError(response);
  return (await response.json()) as ScreenResult;
}

/** Cooperative cancellation of an active streaming run. */
export async function deleteRun(runId: string): Promise<void> {
  const response = await fetch(`/screen/runs/${encodeURIComponent(runId)}`, {
    method: "DELETE",
  });
  // 404 (run already finished) is acceptable for a cancel request.
  if (!response.ok && response.status !== 404) throw await parseError(response);
}
