import type { ReservoirCatalogEntry } from "../api/client";

interface ReservoirCatalogDocument {
  entries?: unknown;
}

/** Parse the small, local-only catalog used to assign one MRST realization per well. */
export function parseReservoirCatalog(text: string): ReservoirCatalogEntry[] {
  let document: unknown;
  try {
    document = JSON.parse(text);
  } catch {
    throw new Error("Reservoir catalog must be valid JSON.");
  }
  const rawEntries = Array.isArray(document)
    ? document
    : (document as ReservoirCatalogDocument | null)?.entries;
  if (!Array.isArray(rawEntries) || rawEntries.length < 1 || rawEntries.length > 20) {
    throw new Error("Reservoir catalog must contain 1 to 20 entries.");
  }
  const entries = rawEntries.map((raw, index) => {
    if (!raw || typeof raw !== "object") {
      throw new Error(`Reservoir catalog entry ${index + 1} must be an object.`);
    }
    const candidate = raw as Record<string, unknown>;
    const wellId = typeof candidate.well_id === "string"
      ? candidate.well_id.trim().toUpperCase()
      : "";
    const modelPath = typeof candidate.model_path === "string"
      ? candidate.model_path.trim()
      : "";
    const bankPath = typeof candidate.bank_path === "string"
      ? candidate.bank_path.trim()
      : "";
    if (!/^W(?:0[1-9]|1\d|20)$/.test(wellId)) {
      throw new Error(`Reservoir catalog entry ${index + 1} has an invalid well_id.`);
    }
    if (!modelPath) {
      throw new Error(`Reservoir catalog entry ${index + 1} has no model_path.`);
    }
    return {
      well_id: wellId,
      model_path: modelPath,
      bank_path: bankPath || null,
    } satisfies ReservoirCatalogEntry;
  });
  const ids = new Set(entries.map((entry) => entry.well_id));
  if (ids.size !== entries.length) {
    throw new Error("Reservoir catalog well_id values must be unique.");
  }
  const ordered = [...entries].sort((left, right) =>
    left.well_id.localeCompare(right.well_id),
  );
  ordered.forEach((entry, index) => {
    const expected = `W${String(index + 1).padStart(2, "0")}`;
    if (entry.well_id !== expected) {
      throw new Error(`Reservoir catalog well ids must be contiguous from W01; expected ${expected}.`);
    }
  });
  return ordered;
}
