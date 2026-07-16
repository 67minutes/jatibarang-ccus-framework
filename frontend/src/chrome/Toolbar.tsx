import { getCommand, isCommandEnabled, runCommand } from "./commands";
import { useWorkspaceStore } from "../state/workspace.store";
import { useActionsStore } from "../state/actions.store";
import { useRunStore } from "../state/run.store";
import { useComposeStore } from "../compose/compose.store";
import type { CellField } from "../api/types";
import "./chrome.css";

/**
 * The toolbar: the frequency layer (design §3 clause 2). Every button is a
 * promoted duplicate of a menu command — no unique capabilities — plus the
 * viewport encoding dropdowns and the exaggeration stepper.
 */

// Toolbar groups, separated by dividers. Ids reference the command registry.
const GROUPS: string[][] = [
  ["file.new", "file.open", "file.save"],
  ["edit.undo", "edit.redo"],
  ["tools.probe", "tools.measure"],
  ["view.toggleViewport"],
];

const FIELD_OPTIONS: { value: CellField; label: string }[] = [
  { value: "gas_saturation", label: "Gas sat." },
  { value: "pressure_bar", label: "Pressure" },
  { value: "z_co2", label: "z_CO₂" },
  { value: "oil_saturation", label: "Oil sat." },
];

export function Toolbar() {
  // Subscribe so enabled-state and encoding controls stay reactive. Command
  // enablement depends on the actions registry, the run status, and the compose
  // draft/history (Screen, Undo, Redo), so the toolbar must observe all three.
  useActionsStore((s) => s.actions);
  useRunStore((s) => s.status);
  useComposeStore((s) => s.draft);
  useComposeStore((s) => s.past.length);
  useComposeStore((s) => s.future.length);
  const colorField = useWorkspaceStore((s) => s.colorField);
  const heightField = useWorkspaceStore((s) => s.heightField);
  const exaggeration = useWorkspaceStore((s) => s.verticalExaggeration);
  const setColorField = useWorkspaceStore((s) => s.setColorField);
  const setHeightField = useWorkspaceStore((s) => s.setHeightField);
  const setExaggeration = useWorkspaceStore((s) => s.setExaggeration);

  return (
    <div className="toolbar" role="toolbar" aria-label="Workbench tools">
      {GROUPS.map((group, gi) => (
        <div className="toolbar-group" key={gi}>
          {group.map((id) => (
            <ToolButton key={id} commandId={id} />
          ))}
        </div>
      ))}

      <div className="toolbar-sep" />

      <label className="toolbar-field">
        <span>Color</span>
        <select
          value={colorField}
          onChange={(e) => setColorField(e.target.value as CellField)}
        >
          {FIELD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <label className="toolbar-field">
        <span>Height</span>
        <select
          value={heightField}
          onChange={(e) => setHeightField(e.target.value as CellField)}
        >
          {FIELD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <div className="toolbar-stepper">
        <span>Exagg</span>
        <button
          type="button"
          aria-label="Decrease vertical exaggeration"
          onClick={() => setExaggeration(exaggeration - 1)}
        >
          −
        </button>
        <span className="mono toolbar-stepper-value">{exaggeration}×</span>
        <button
          type="button"
          aria-label="Increase vertical exaggeration"
          onClick={() => setExaggeration(exaggeration + 1)}
        >
          +
        </button>
      </div>

      <div className="toolbar-spacer" />

      <div className="toolbar-group toolbar-run">
        <RunButton commandId="study.screen" />
        <RunButton commandId="study.cancel" />
      </div>
    </div>
  );
}

function ToolButton({ commandId }: { commandId: string }) {
  const command = getCommand(commandId);
  if (!command) return null;
  return (
    <button
      type="button"
      className="tool-button"
      title={`${command.label}${command.shortcut ? `  (${command.shortcut})` : ""}`}
      aria-label={command.label}
      disabled={!isCommandEnabled(command.id)}
      onClick={() => runCommand(command.id)}
    >
      <span aria-hidden>{command.icon ?? "•"}</span>
    </button>
  );
}

function RunButton({ commandId }: { commandId: string }) {
  const command = getCommand(commandId);
  if (!command) return null;
  return (
    <button
      type="button"
      className={`run-button${command.accent ? " run-button-accent" : ""}`}
      title={`${command.label}${command.shortcut ? `  (${command.shortcut})` : ""}`}
      disabled={!isCommandEnabled(command.id)}
      onClick={() => runCommand(command.id)}
    >
      <span aria-hidden>{command.icon}</span> {command.label}
    </button>
  );
}
