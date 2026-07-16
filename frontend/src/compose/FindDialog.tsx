import { useMemo, useState } from "react";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore, type SelectionKind } from "../state/selection.store";
import { planForPrice } from "../results/priceScrubber";

/** Find Object — jump-to a well, source, or route by id (design §3.2 Edit). */
export function FindDialog({ onDone }: { onDone: () => void }) {
  const [query, setQuery] = useState("");
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const carbonPriceId = useSelectionStore((s) => s.carbonPriceId);
  const select = useSelectionStore((s) => s.select);

  const objects = useMemo(() => {
    if (!activeEntry) return [];
    const plan = planForPrice(activeEntry.result, carbonPriceId);
    const items: { kind: SelectionKind; id: string; label: string }[] = [];
    if (activeEntry.request.mode === "inline") {
      for (const s of activeEntry.request.sources) items.push({ kind: "source", id: s.id, label: `source ${s.id}` });
    }
    for (const w of plan?.well_strategies ?? []) items.push({ kind: "well", id: w.candidate_id, label: `well ${w.candidate_id}` });
    for (const seg of plan?.pipeline.built_segments ?? []) items.push({ kind: "route", id: seg.segment_id, label: `route ${seg.from_node}→${seg.to_node}` });
    return items;
  }, [activeEntry, carbonPriceId]);

  const matches = objects.filter((o) => o.id.toLowerCase().includes(query.toLowerCase()));

  return (
    <div>
      <input
        autoFocus
        type="text"
        placeholder="Type a well, source, or route id…"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        style={{ width: "100%", marginBottom: 8 }}
      />
      {objects.length === 0 ? (
        <p className="empty-hint">Load a study to search its objects.</p>
      ) : (
        <ul className="find-results">
          {matches.slice(0, 30).map((o) => (
            <li key={`${o.kind}-${o.id}`}>
              <button
                type="button"
                className="tree-node"
                onClick={() => {
                  select({ kind: o.kind, id: o.id });
                  onDone();
                }}
              >
                {o.label}
              </button>
            </li>
          ))}
          {matches.length === 0 && <li className="empty-hint">No matches.</li>}
        </ul>
      )}
    </div>
  );
}
