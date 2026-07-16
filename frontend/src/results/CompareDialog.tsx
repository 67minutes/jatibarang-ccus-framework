import { useLedgerStore } from "../state/ledger.store";
import { compareEntries } from "./compare";
import { shortFingerprint, type LedgerEntry } from "../memo/studyMemo";
import { usd } from "../util/format";

/** Compare two ledger entries — the A/B/C view as a fingerprint diff (§7.4). */
export function CompareDialog() {
  const entries = useLedgerStore((s) => s.entries);
  const compareIds = useLedgerStore((s) => s.compareIds);
  const setCompare = useLedgerStore((s) => s.setCompare);
  const entryById = useLedgerStore((s) => s.entryById);

  if (entries.length < 2) {
    return <p className="empty-hint">Run or open at least two studies to compare.</p>;
  }

  const a = entryById(compareIds[0] ?? entries[0].entryId);
  const b = entryById(compareIds[1] ?? entries[1].entryId);

  return (
    <div>
      <div className="compare-picker">
        <select value={a?.entryId ?? ""} onChange={(e) => setCompare(0, e.target.value)}>
          {entries.map((e) => (
            <option key={e.entryId} value={e.entryId}>
              A · {e.label} ({shortFingerprint(e.fingerprint)})
            </option>
          ))}
        </select>
        <select value={b?.entryId ?? ""} onChange={(e) => setCompare(1, e.target.value)}>
          {entries.map((e) => (
            <option key={e.entryId} value={e.entryId}>
              B · {e.label} ({shortFingerprint(e.fingerprint)})
            </option>
          ))}
        </select>
      </div>

      {a && b && <CompareBody a={a} b={b} />}
    </div>
  );
}

function CompareBody({ a, b }: { a: LedgerEntry; b: LedgerEntry }) {
  const cmp = compareEntries(a, b);
  return (
    <div>
      {cmp.sameFingerprint ? (
        <p className="empty-hint">
          Identical request fingerprints — these two runs used the same inputs.
        </p>
      ) : (
        <>
          <h4>Request deltas</h4>
          {cmp.requestDeltas.length === 0 ? (
            <p className="empty-hint">No summarized request fields differ.</p>
          ) : (
            <table className="data-table" style={{ marginBottom: 12 }}>
              <thead>
                <tr>
                  <th>Field</th>
                  <th>A</th>
                  <th>B</th>
                </tr>
              </thead>
              <tbody>
                {cmp.requestDeltas.map((d) => (
                  <tr key={d.field}>
                    <td className="mono">{d.field}</td>
                    <td>{d.a}</td>
                    <td>{d.b}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}

      <h4>Rank trajectories</h4>
      <table className="data-table">
        <thead>
          <tr>
            <th>Candidate</th>
            <th className="num">Rank A</th>
            <th className="num">Rank B</th>
            <th className="num">NPV A</th>
            <th className="num">NPV B</th>
            <th className="num">ΔNPV</th>
          </tr>
        </thead>
        <tbody>
          {cmp.trajectories.map((t) => {
            const delta = t.npvA != null && t.npvB != null ? t.npvB - t.npvA : null;
            return (
              <tr key={t.candidateId}>
                <td className="mono">{t.candidateId}</td>
                <td className="num">{t.rankA ?? "—"}</td>
                <td className="num">{t.rankB ?? "—"}</td>
                <td className="num">{usd(t.npvA)}</td>
                <td className="num">{usd(t.npvB)}</td>
                <td className={`num ${delta != null ? (delta >= 0 ? "delta-add" : "delta-del") : ""}`}>
                  {delta != null ? usd(delta) : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
