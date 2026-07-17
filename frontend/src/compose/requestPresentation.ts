import {
  displayWireKey,
  scientificDisplayText,
} from "../ui/presentation";

/**
 * Produce readable, vocabulary-safe request JSON without mutating wire data.
 * Large geology and launch-pad catalogs remain count-only summaries.
 */
export function requestForDisplay(value: unknown, depth = 0): unknown {
  if (Array.isArray(value)) {
    if (value.length > 24 && value.every((item) => typeof item === "number")) {
      return `\u27e8${value.length} numbers elided\u27e9`;
    }
    return value.map((item) => requestForDisplay(item, depth + 1));
  }
  if (typeof value === "string") return scientificDisplayText(value);
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value)) {
      const displayKey = displayWireKey(key);
      if (
        (key === "geologies" || key === "seeds") &&
        depth === 0 &&
        item &&
        typeof item === "object"
      ) {
        const count = Object.keys(item).length;
        out[displayKey] = `\u27e8${count} entr${count === 1 ? "y" : "ies"} elided\u27e9`;
      } else if (
        key === "seed_by_schedule_fingerprint" &&
        item &&
        typeof item === "object"
      ) {
        const count = Object.keys(item).length;
        out[displayKey] = `\u27e8${count} schedule link${count === 1 ? "" : "s"} elided\u27e9`;
      } else if (key === "routing_basis_id" || key === "pipeline_basis_id") {
        out[displayKey] = "\u27e8configured basis\u27e9";
      } else {
        out[displayKey] = requestForDisplay(item, depth + 1);
      }
    }
    return out;
  }
  return value;
}
