import { useMemo, useState, type FormEvent } from "react";
import { getActions, useActionsStore } from "../state/actions.store";
import { useStudyStore } from "../state/study.store";

export function NewStudyDialog({ onDone }: { onDone: () => void }) {
  useActionsStore((s) => s.actions.createNewStudy);
  const current = useStudyStore((s) => s.study);
  const [name, setName] = useState("Untitled Jatibarang study");
  const [analyst, setAnalyst] = useState(current.analyst);
  const [notes, setNotes] = useState("");
  const [template, setTemplate] = useState<"demo" | "current">("demo");
  const [memoName, setMemoName] = useState("");
  const [memoTouched, setMemoTouched] = useState(false);
  const [startView, setStartView] = useState<"2d" | "3d">("3d");
  const [exaggeration, setExaggeration] = useState(5);

  const suggestedMemo = useMemo(() => {
    if (memoTouched && memoName.trim()) return memoName.trim();
    const stem = name
      .trim()
      .replace(/[^a-z0-9._-]+/gi, "_")
      .replace(/^_+|_+$/g, "")
      .toLowerCase();
    return `${stem || "jatibarang-study"}.study.json`;
  }, [memoName, memoTouched, name]);

  function submit(event: FormEvent) {
    event.preventDefault();
    const create = getActions().createNewStudy;
    if (!create || !name.trim()) return;
    create({
      name,
      analyst,
      notes,
      template,
      memoFileName: suggestedMemo,
      startView,
      verticalExaggeration: exaggeration,
    });
    onDone();
  }

  return (
    <form className="dialog-form" onSubmit={submit}>
      <p className="dialog-intro">
        Create a clean study definition. Existing runs stay in the session ledger
        for comparison, while the new draft receives its own human-readable memo.
      </p>

      <div className="dialog-grid">
        <label className="dialog-field dialog-field-wide">
          <span>Study name</span>
          <input value={name} onChange={(e) => setName(e.target.value)} autoFocus required />
        </label>
        <label className="dialog-field">
          <span>Analyst</span>
          <input
            value={analyst}
            onChange={(e) => setAnalyst(e.target.value)}
            placeholder="Optional"
          />
        </label>
        <label className="dialog-field">
          <span>Starting definition</span>
          <select value={template} onChange={(e) => setTemplate(e.target.value as "demo" | "current")}>
            <option value="demo">Jatibarang demo base</option>
            <option value="current">Copy current composer</option>
          </select>
        </label>
        <label className="dialog-field">
          <span>Initial viewport</span>
          <select value={startView} onChange={(e) => setStartView(e.target.value as "2d" | "3d")}>
            <option value="3d">3D field twin</option>
            <option value="2d">2D map</option>
          </select>
        </label>
        <label className="dialog-field">
          <span>Terrain exaggeration</span>
          <select value={exaggeration} onChange={(e) => setExaggeration(Number(e.target.value))}>
            {[1, 2, 5, 10].map((value) => (
              <option key={value} value={value}>{value}{"\u00d7"}</option>
            ))}
          </select>
        </label>
        <label className="dialog-field dialog-field-wide">
          <span>Study memo file name</span>
          <input
            value={suggestedMemo}
            onChange={(e) => {
              setMemoTouched(true);
              setMemoName(e.target.value);
            }}
          />
        </label>
        <label className="dialog-field dialog-field-wide">
          <span>Save location</span>
          <input value="Choose a folder when Save Study is used" readOnly aria-readonly="true" />
          <small>
            Browsers cannot preselect an arbitrary local path. The native save dialog
            opens on first save and uses the file name above.
          </small>
        </label>
        <label className="dialog-field dialog-field-wide">
          <span>Study notes</span>
          <textarea
            rows={3}
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Decision context, assumptions, or review purpose"
          />
        </label>
      </div>

      <footer className="dialog-actions">
        <button type="button" className="btn" onClick={onDone}>Cancel</button>
        <button type="submit" className="btn btn-accent" disabled={!name.trim() || !getActions().createNewStudy}>
          Create Study
        </button>
      </footer>
    </form>
  );
}
