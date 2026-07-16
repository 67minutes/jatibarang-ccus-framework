import { getActions } from "../state/actions.store";
import { useUiStore } from "../state/ui.store";
import {
  EXAGGERATION_MAX,
  EXAGGERATION_MIN,
  useWorkspaceStore,
} from "../state/workspace.store";
import type { CellField } from "../api/types";

/**
 * The single command registry. The classical WIMP contract (design §3):
 *
 *   1. The menu bar is the COMPLETE command inventory — every command below
 *      appears in exactly one menu. Nothing hides behind hover-reveals.
 *   2. The toolbar is the FREQUENCY layer — a strict subset (`toolbar: true`),
 *      no unique capabilities.
 *
 * Both `MenuBar` and `Toolbar` render from this list, which makes the contract
 * provable rather than aspirational.
 */

export interface Command {
  id: string;
  label: string;
  /** Human-readable shortcut, shown right-aligned in menus. */
  shortcut?: string;
  /** Promoted to the toolbar when true. */
  toolbar?: boolean;
  /** Icon glyph for the toolbar (text-based; no icon font dependency). */
  icon?: string;
  /** Danger/accent styling hint for the toolbar (e.g. the Screen button). */
  accent?: boolean;
  isEnabled?: () => boolean;
  run: () => void;
}

export type MenuNode =
  | { kind: "command"; commandId: string }
  | { kind: "separator" }
  | { kind: "submenu"; label: string; items: MenuNode[] };

export interface Menu {
  label: string;
  items: MenuNode[];
}

const CELL_FIELDS: { field: CellField; label: string; digit: string }[] = [
  { field: "gas_saturation", label: "Gas saturation", digit: "1" },
  { field: "pressure_bar", label: "Pressure", digit: "2" },
  { field: "z_co2", label: "z_CO₂", digit: "3" },
  { field: "oil_saturation", label: "Oil saturation", digit: "4" },
];

function ws() {
  return useWorkspaceStore.getState();
}

export const commands: Command[] = [
  // ---- File -------------------------------------------------------------
  {
    id: "file.new",
    label: "New Study",
    shortcut: "Ctrl+N",
    toolbar: true,
    icon: "🗋",
    run: () => getActions().newStudy?.(),
    isEnabled: () => Boolean(getActions().newStudy),
  },
  {
    id: "file.open",
    label: "Open Study…",
    shortcut: "Ctrl+O",
    toolbar: true,
    icon: "📂",
    run: () => getActions().openStudy?.(),
    isEnabled: () => Boolean(getActions().openStudy),
  },
  {
    id: "file.save",
    label: "Save Study",
    shortcut: "Ctrl+S",
    toolbar: true,
    icon: "💾",
    run: () => getActions().saveStudy?.(),
    isEnabled: () => Boolean(getActions().saveStudy && getActions().hasActiveResult?.()),
  },
  {
    id: "file.saveAs",
    label: "Save Study As…",
    shortcut: "Ctrl+Shift+S",
    run: () => getActions().saveStudyAs?.(),
    isEnabled: () => Boolean(getActions().saveStudyAs && getActions().hasActiveResult?.()),
  },
  {
    id: "file.exportRanking",
    label: "Export Ranking CSV",
    run: () => getActions().exportRankingCsv?.(),
    isEnabled: () => Boolean(getActions().exportRankingCsv && getActions().hasActiveResult?.()),
  },
  {
    id: "file.exportSnapshot",
    label: "Export Scene Snapshot PNG",
    run: () => getActions().exportSnapshot?.(),
    isEnabled: () => Boolean(getActions().exportSnapshot),
  },

  // ---- Edit -------------------------------------------------------------
  {
    id: "edit.undo",
    label: "Undo",
    shortcut: "Ctrl+Z",
    toolbar: true,
    icon: "↶",
    run: () => getActions().undo?.(),
    isEnabled: () => Boolean(getActions().canUndo?.()),
  },
  {
    id: "edit.redo",
    label: "Redo",
    shortcut: "Ctrl+Y",
    toolbar: true,
    icon: "↷",
    run: () => getActions().redo?.(),
    isEnabled: () => Boolean(getActions().canRedo?.()),
  },
  {
    id: "edit.find",
    label: "Find Object…",
    shortcut: "Ctrl+F",
    run: () => useUiStore.getState().openModal("find"),
  },
  {
    id: "edit.preferences",
    label: "Preferences…",
    run: () => useUiStore.getState().openModal("preferences"),
  },

  // ---- View -------------------------------------------------------------
  {
    id: "view.toggleViewport",
    label: "Toggle 2D / 3D",
    shortcut: "V",
    toolbar: true,
    icon: "▦",
    run: () => ws().toggleViewport(),
  },
  {
    id: "view.resetCamera",
    label: "Reset Camera",
    run: () => window.dispatchEvent(new CustomEvent("viewport:reset-camera")),
  },
  {
    id: "view.frameSelection",
    label: "Frame Selection",
    shortcut: "F",
    run: () => window.dispatchEvent(new CustomEvent("viewport:frame-selection")),
  },
  {
    id: "view.togglePanelTree",
    label: "Show Project Tree",
    run: () => ws().togglePanel("tree"),
  },
  {
    id: "view.togglePanelInspector",
    label: "Show Inspector",
    run: () => ws().togglePanel("inspector"),
  },
  {
    id: "view.togglePanelDashboard",
    label: "Show Dashboard",
    run: () => ws().togglePanel("dashboard"),
  },
  {
    id: "view.exaggUp",
    label: "Increase Vertical Exaggeration",
    run: () => ws().setExaggeration(ws().verticalExaggeration + 1),
    isEnabled: () => ws().verticalExaggeration < EXAGGERATION_MAX,
  },
  {
    id: "view.exaggDown",
    label: "Decrease Vertical Exaggeration",
    run: () => ws().setExaggeration(ws().verticalExaggeration - 1),
    isEnabled: () => ws().verticalExaggeration > EXAGGERATION_MIN,
  },
  // Color-by commands (one per field, with 1–4 shortcuts).
  ...CELL_FIELDS.map<Command>(({ field, label, digit }) => ({
    id: `view.colorBy.${field}`,
    label: `Color By ${label}`,
    shortcut: digit,
    run: () => ws().setColorField(field),
  })),
  ...CELL_FIELDS.map<Command>(({ field, label }) => ({
    id: `view.heightBy.${field}`,
    label: `Height By ${label}`,
    run: () => ws().setHeightField(field),
  })),

  // ---- Study ------------------------------------------------------------
  {
    id: "study.screen",
    label: "Screen",
    shortcut: "Ctrl+Enter",
    toolbar: true,
    icon: "▶",
    accent: true,
    run: () => getActions().screen?.(),
    isEnabled: () => Boolean(getActions().screen && getActions().canScreen?.()),
  },
  {
    id: "study.cancel",
    label: "Cancel Run",
    shortcut: "Esc",
    toolbar: true,
    icon: "■",
    run: () => getActions().cancelRun?.(),
    isEnabled: () => Boolean(getActions().cancelRun && getActions().canCancel?.()),
  },
  {
    id: "study.validate",
    label: "Validate (Preflight)",
    run: () => {
      getActions().validate?.();
      useUiStore.getState().openModal("validate");
    },
  },
  {
    id: "study.recompose",
    label: "Re-compose from Ledger Entry",
    run: () => getActions().recomposeActive?.(),
    isEnabled: () => Boolean(getActions().recomposeActive && getActions().hasActiveResult?.()),
  },
  {
    id: "study.compare",
    label: "Compare Studies…",
    run: () => useUiStore.getState().openModal("compare"),
  },

  // ---- Tools ------------------------------------------------------------
  {
    id: "tools.probe",
    label: "Grid Probe",
    toolbar: true,
    icon: "⌖",
    run: () => window.dispatchEvent(new CustomEvent("tool:activate", { detail: "probe" })),
  },
  {
    id: "tools.measure",
    label: "Measure Distance",
    toolbar: true,
    icon: "📏",
    run: () => window.dispatchEvent(new CustomEvent("tool:activate", { detail: "measure" })),
  },
  {
    id: "tools.elevationProfile",
    label: "Elevation Profile Along Route",
    run: () => window.dispatchEvent(new CustomEvent("tool:activate", { detail: "elevation" })),
  },

  // ---- Help -------------------------------------------------------------
  {
    id: "help.shortcuts",
    label: "Keyboard Shortcuts",
    run: () => useUiStore.getState().openModal("shortcuts"),
  },
  {
    id: "help.apiDocs",
    label: "API Documentation",
    run: () => window.open("/docs", "_blank", "noopener"),
  },
  {
    id: "help.about",
    label: "About",
    run: () => useUiStore.getState().openModal("about"),
  },
];

const byId = new Map(commands.map((c) => [c.id, c]));

export function getCommand(id: string): Command | undefined {
  return byId.get(id);
}

export function runCommand(id: string): void {
  const command = byId.get(id);
  if (command && (command.isEnabled?.() ?? true)) command.run();
}

export function isCommandEnabled(id: string): boolean {
  const command = byId.get(id);
  if (!command) return false;
  return command.isEnabled?.() ?? true;
}

/** The complete menu tree (design §3.2). Every command id above appears here. */
export const menus: Menu[] = [
  {
    label: "File",
    items: [
      { kind: "command", commandId: "file.new" },
      { kind: "command", commandId: "file.open" },
      { kind: "separator" },
      { kind: "command", commandId: "file.save" },
      { kind: "command", commandId: "file.saveAs" },
      { kind: "separator" },
      {
        kind: "submenu",
        label: "Export",
        items: [
          { kind: "command", commandId: "file.exportRanking" },
          { kind: "command", commandId: "file.exportSnapshot" },
        ],
      },
    ],
  },
  {
    label: "Edit",
    items: [
      { kind: "command", commandId: "edit.undo" },
      { kind: "command", commandId: "edit.redo" },
      { kind: "separator" },
      { kind: "command", commandId: "edit.find" },
      { kind: "command", commandId: "edit.preferences" },
    ],
  },
  {
    label: "View",
    items: [
      { kind: "command", commandId: "view.toggleViewport" },
      { kind: "command", commandId: "view.resetCamera" },
      { kind: "command", commandId: "view.frameSelection" },
      { kind: "separator" },
      {
        kind: "submenu",
        label: "Panels",
        items: [
          { kind: "command", commandId: "view.togglePanelTree" },
          { kind: "command", commandId: "view.togglePanelInspector" },
          { kind: "command", commandId: "view.togglePanelDashboard" },
        ],
      },
      {
        kind: "submenu",
        label: "Color By",
        items: CELL_FIELDS.map((f) => ({
          kind: "command" as const,
          commandId: `view.colorBy.${f.field}`,
        })),
      },
      {
        kind: "submenu",
        label: "Height By",
        items: CELL_FIELDS.map((f) => ({
          kind: "command" as const,
          commandId: `view.heightBy.${f.field}`,
        })),
      },
      {
        kind: "submenu",
        label: "Vertical Exaggeration",
        items: [
          { kind: "command", commandId: "view.exaggUp" },
          { kind: "command", commandId: "view.exaggDown" },
        ],
      },
    ],
  },
  {
    label: "Study",
    items: [
      { kind: "command", commandId: "study.validate" },
      { kind: "command", commandId: "study.screen" },
      { kind: "command", commandId: "study.cancel" },
      { kind: "separator" },
      { kind: "command", commandId: "study.recompose" },
      { kind: "command", commandId: "study.compare" },
    ],
  },
  {
    label: "Tools",
    items: [
      { kind: "command", commandId: "tools.probe" },
      { kind: "command", commandId: "tools.measure" },
      { kind: "command", commandId: "tools.elevationProfile" },
    ],
  },
  {
    label: "Help",
    items: [
      { kind: "command", commandId: "help.shortcuts" },
      { kind: "command", commandId: "help.apiDocs" },
      { kind: "separator" },
      { kind: "command", commandId: "help.about" },
    ],
  },
];

/** Commands promoted to the toolbar, in registry order. */
export const toolbarCommandIds = commands
  .filter((c) => c.toolbar)
  .map((c) => c.id);
