import { type ReactNode } from "react";
import { useUiStore } from "../state/ui.store";
import { commands } from "./commands";
import { APP_VERSION, API_CONTRACT_VERSION } from "../version";
import { FindDialog } from "../compose/FindDialog";
import { CompareDialog } from "../results/CompareDialog";
import { ValidateDialog } from "../compose/ValidateDialog";

/** All modal dialogs, driven by the ui store. */
export function Modals() {
  const modal = useUiStore((s) => s.modal);
  const close = useUiStore((s) => s.closeModal);
  if (modal === null) return null;

  switch (modal) {
    case "shortcuts":
      return (
        <Shell title="Keyboard Shortcuts" onClose={close}>
          <ShortcutsBody />
        </Shell>
      );
    case "about":
      return (
        <Shell title="About" onClose={close}>
          <AboutBody />
        </Shell>
      );
    case "find":
      return (
        <Shell title="Find Object" onClose={close}>
          <FindDialog onDone={close} />
        </Shell>
      );
    case "compare":
      return (
        <Shell title="Compare Studies" onClose={close}>
          <CompareDialog />
        </Shell>
      );
    case "validate":
      return (
        <Shell title="Preflight Validation" onClose={close}>
          <ValidateDialog />
        </Shell>
      );
    case "preferences":
      return (
        <Shell title="Preferences" onClose={close}>
          <p className="empty-hint">
            Units, default vertical exaggeration, and colormap bins are fixed to
            sensible defaults in this build.
          </p>
        </Shell>
      );
    default:
      return null;
  }
}

function Shell({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  return (
    <div className="modal-scrim" onClick={onClose}>
      <div className="modal" role="dialog" aria-label={title} onClick={(e) => e.stopPropagation()}>
        <header className="modal-head">
          <h2>{title}</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Close">
            ✕
          </button>
        </header>
        <div className="modal-body">{children}</div>
      </div>
    </div>
  );
}

function ShortcutsBody() {
  const withKeys = commands.filter((c) => c.shortcut);
  return (
    <table className="shortcut-table">
      <tbody>
        {withKeys.map((c) => (
          <tr key={c.id}>
            <td>{c.shortcut}</td>
            <td>{c.label}</td>
          </tr>
        ))}
        <tr>
          <td>Space</td>
          <td>Play / pause plume timeline</td>
        </tr>
        <tr>
          <td>← / →</td>
          <td>Step timeline frames</td>
        </tr>
      </tbody>
    </table>
  );
}

function AboutBody() {
  return (
    <div>
      <p style={{ marginTop: 0 }}>
        Jatibarang CCUS Screening Workbench — a Fieldman CCUS-planning module.
        Screening-grade results; not FEED, PSC, or final-paper economics.
      </p>
      <dl className="kv">
        <dt>App version</dt>
        <dd>{APP_VERSION}</dd>
        <dt>API contract version</dt>
        <dd>{API_CONTRACT_VERSION}</dd>
        <dt>Promoted checkpoint SHA-256</dt>
        <dd>see GET /model/info</dd>
        <dt>Solver</dt>
        <dd>CBC (see GET /health)</dd>
      </dl>
      <p className="empty-hint" style={{ paddingLeft: 0 }}>
        Provenance (checkpoint hash, solver version) is reported live by the
        backend at <code>/model/info</code> and <code>/health</code>.
      </p>
    </div>
  );
}
