export interface WellsCsvRow {
  id: string;
  lat: number;
  lon: number;
}

export interface WellPlacementActions {
  addWell: (lat: number, lon: number) => { id: string };
  renameWell: (id: string, name: string) => void;
}

const EXPECTED_HEADER = ["id", "lat", "lon"];

/**
 * Parse the intentionally small well-placement CSV contract used by New Study.
 * Quoted fields are unnecessary because ids and coordinates may not contain
 * commas; rejecting extra columns keeps mistakes visible to the user.
 */
export function parseWellsCsv(text: string): WellsCsvRow[] {
  const lines = text.replace(/^\uFEFF/, "").split(/\r?\n/);
  const header = (lines[0] ?? "").split(",").map((part) => part.trim());

  if (
    header.length !== EXPECTED_HEADER.length ||
    header.some((part, index) => part.toLowerCase() !== EXPECTED_HEADER[index])
  ) {
    throw new Error("Wells CSV header must be id,lat,lon");
  }

  const rows: WellsCsvRow[] = [];
  const ids = new Set<string>();
  lines.slice(1).forEach((rawLine, offset) => {
    const lineNumber = offset + 2;
    if (!rawLine.trim()) return;

    const columns = rawLine.split(",").map((part) => part.trim());
    if (columns.length !== 3 || !columns[0]) {
      throw new Error(`Malformed wells CSV row on line ${lineNumber}`);
    }

    const lat = Number(columns[1]);
    const lon = Number(columns[2]);
    if (
      !Number.isFinite(lat) ||
      !Number.isFinite(lon) ||
      lat < -90 ||
      lat > 90 ||
      lon < -180 ||
      lon > 180
    ) {
      throw new Error(`Invalid well coordinates on line ${lineNumber}`);
    }

    const normalizedId = columns[0].toUpperCase();
    if (ids.has(normalizedId)) {
      throw new Error(`Duplicate well id on line ${lineNumber}`);
    }
    ids.add(normalizedId);
    rows.push({ id: columns[0], lat, lon });
  });

  return rows;
}

/**
 * Add CSV wells without ever replacing the reservoir model's derived W01.
 * CSV ids are display labels; stable request ids remain store-assigned.
 */
export function applyWellsCsvRows(
  rows: WellsCsvRow[],
  actions: WellPlacementActions,
): number {
  let added = 0;
  for (const row of rows) {
    if (row.id.toUpperCase() === "W01") continue;
    const well = actions.addWell(row.lat, row.lon);
    actions.renameWell(well.id, row.id);
    added += 1;
  }
  return added;
}
