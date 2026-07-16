import { useMemo } from "react";
import { useComposeStore } from "./compose.store";

/**
 * The request-JSON drawer (design §7.2 — "the payload is the deck"). The full
 * request carries multi-megabyte 64×64 geology/seed grids, so those blocks are
 * elided to a summary; the decision-relevant fields are shown verbatim.
 */
export function RequestDrawer() {
  const draft = useComposeStore((s) => s.draft);
  const text = useMemo(() => (draft ? JSON.stringify(elide(draft), null, 2) : ""), [draft]);
  if (!draft) return null;
  return (
    <div className="request-drawer">
      <div className="request-drawer-note">
        Geology and seed grids (64×64 fields) are elided for readability. This is
        the exact request that will be sent, minus those large arrays.
      </div>
      <pre className="request-json mono">{text}</pre>
    </div>
  );
}

/** Replace bulky nested arrays with a shape summary. */
function elide(value: unknown, key = "", depth = 0): unknown {
  if (Array.isArray(value)) {
    if (value.length > 24 && value.every((v) => typeof v === "number")) {
      return `⟨${value.length} numbers elided⟩`;
    }
    return value.map((v, i) => elide(v, String(i), depth + 1));
  }
  if (value && typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) {
      // Collapse the largest opaque blocks to a summary.
      if ((k === "geologies" || k === "seeds") && depth === 0 && v && typeof v === "object") {
        out[k] = `⟨${Object.keys(v).length} entr${Object.keys(v).length === 1 ? "y" : "ies"} elided⟩`;
      } else {
        out[k] = elide(v, k, depth + 1);
      }
    }
    return out;
  }
  void key;
  return value;
}
