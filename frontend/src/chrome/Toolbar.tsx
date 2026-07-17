import { getCommand, isCommandEnabled, runCommand } from "./commands";
import {
  EXAGGERATION_MAX,
  EXAGGERATION_MIN,
  RESERVOIR_EXAGGERATION_MAX,
  RESERVOIR_EXAGGERATION_MIN,
  useWorkspaceStore,
} from "../state/workspace.store";
import { useActionsStore } from "../state/actions.store";
import { useRunStore } from "../state/run.store";
import { useComposeStore } from "../compose/compose.store";
import type { CellField } from "../api/types";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";
import { availablePredictionFields } from "../viewport/fieldAvailability";
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
  ["tools.select", "tools.orbit", "tools.probe", "tools.measure"],
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
  const activeEntry = useLedgerStore((s) => s.entryById(s.activeEntryId));
  const selection = useSelectionStore((s) => s.selection);
  useComposeStore((s) => s.draft);
  useComposeStore((s) => s.past.length);
  useComposeStore((s) => s.future.length);
  const colorField = useWorkspaceStore((s) => s.colorField);
  const heightField = useWorkspaceStore((s) => s.heightField);
  const exaggeration = useWorkspaceStore((s) => s.verticalExaggeration);
  const reservoirExaggeration = useWorkspaceStore((s) => s.reservoirVerticalExaggeration);
  const setColorField = useWorkspaceStore((s) => s.setColorField);
  const setHeightField = useWorkspaceStore((s) => s.setHeightField);
  const setExaggeration = useWorkspaceStore((s) => s.setExaggeration);
  const setReservoirExaggeration = useWorkspaceStore((s) => s.setReservoirExaggeration);
  const scenarioId = selection.scenarioId
    ?? (selection.kind === "well" && selection.id
      ? Object.keys(activeEntry?.result.detailed_predictions ?? {}).find((id) => id === selection.id || id.startsWith(`${selection.id}--`))
      : null);
  const prediction = scenarioId ? activeEntry?.result.detailed_predictions[scenarioId] : undefined;
  const reservoir = scenarioId ? activeEntry?.result.detailed_reservoirs?.[scenarioId] : undefined;
  const availableFields = availablePredictionFields(prediction, reservoir?.baseline_state);
  const hasFieldContext = Boolean(prediction && reservoir);

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
        <span>Response</span>
        <select
          aria-label="Dynamic response field"
          value={colorField}
          disabled={!hasFieldContext}
          onChange={(e) => setColorField(e.target.value as CellField)}
        >
          {FIELD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value} disabled={!availableFields.has(o.value)}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <label className="toolbar-field">
        <span>Columns</span>
        <select
          aria-label="Height field"
          value={heightField}
          disabled={!hasFieldContext}
          onChange={(e) => setHeightField(e.target.value as CellField)}
        >
          {FIELD_OPTIONS.map((o) => (
            <option key={o.value} value={o.value} disabled={!availableFields.has(o.value)}>
              {o.label}
            </option>
          ))}
        </select>
      </label>

      <div className="toolbar-stepper">
        <span>Terrain</span>
        <button
          type="button"
          aria-label="Decrease vertical exaggeration"
          disabled={exaggeration <= EXAGGERATION_MIN}
          onClick={() => setExaggeration(exaggeration - 1)}
        >
          −
        </button>
        <span className="mono toolbar-stepper-value">{exaggeration}×</span>
        <button
          type="button"
          aria-label="Increase vertical exaggeration"
          disabled={exaggeration >= EXAGGERATION_MAX}
          onClick={() => setExaggeration(exaggeration + 1)}
        >
          +
        </button>
      </div>

      <div className="toolbar-stepper">
        <span>Reservoir</span>
        <button
          type="button"
          aria-label="Decrease reservoir vertical exaggeration"
          disabled={reservoirExaggeration <= RESERVOIR_EXAGGERATION_MIN}
          onClick={() => setReservoirExaggeration(reservoirExaggeration - 1)}
        >
          −
        </button>
        <span className="mono toolbar-stepper-value">{reservoirExaggeration}×</span>
        <button
          type="button"
          aria-label="Increase reservoir vertical exaggeration"
          disabled={reservoirExaggeration >= RESERVOIR_EXAGGERATION_MAX}
          onClick={() => setReservoirExaggeration(reservoirExaggeration + 1)}
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
  const activeTool = useWorkspaceStore((s) => s.activeTool);
  const viewport = useWorkspaceStore((s) => s.viewport);
  if (!command) return null;
  const toolId = commandId.startsWith("tools.") ? commandId.slice("tools.".length) : null;
  const active = toolId ? activeTool === toolId : commandId === "view.toggleViewport" && viewport === "3d";
  return (
    <button
      type="button"
      className={`tool-button${active ? " tool-button-active" : ""}`}
      title={`${command.label}${command.shortcut ? `  (${command.shortcut})` : ""}`}
      aria-label={command.label}
      disabled={!isCommandEnabled(command.id)}
      aria-pressed={active}
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
