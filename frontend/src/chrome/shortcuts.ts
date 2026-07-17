import { useEffect } from "react";
import { runCommand } from "./commands";
import { useWorkspaceStore } from "../state/workspace.store";

/**
 * The global keyboard layer (design §3.5). Shortcuts dispatch into the command
 * registry so the menu, toolbar, and keyboard all drive the same commands.
 *
 * Text inputs keep their native behavior: single-key shortcuts (Space, arrows,
 * digits, F) are suppressed while typing, but chorded ones (Ctrl+…) still fire.
 */

function isTypingTarget(el: EventTarget | null): boolean {
  if (!(el instanceof HTMLElement)) return false;
  const tag = el.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || el.isContentEditable;
}

export function useGlobalShortcuts(): void {
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const typing = isTypingTarget(e.target);
      const ctrl = e.ctrlKey || e.metaKey;

      // Chorded (Ctrl/Cmd) shortcuts fire everywhere.
      if (ctrl) {
        const key = e.key.toLowerCase();
        if (key === "z" && !e.shiftKey) return dispatch(e, "edit.undo");
        if (key === "y" || (key === "z" && e.shiftKey)) return dispatch(e, "edit.redo");
        if (key === "o") return dispatch(e, "file.open");
        if (key === "s" && !e.shiftKey) return dispatch(e, "file.save");
        if (key === "s" && e.shiftKey) return dispatch(e, "file.saveAs");
        if (key === "n") return dispatch(e, "file.new");
        if (key === "f") return dispatch(e, "edit.find");
        if (key === "enter") return dispatch(e, "study.screen");
        return;
      }

      // Escape is a global cancel/close and fires even while typing.
      if (e.key === "Escape") {
        useWorkspaceStore.getState().setActiveTool("select");
        return dispatch(e, "study.cancel");
      }

      if (typing) return;

      switch (e.key) {
        case " ":
          e.preventDefault();
          useWorkspaceStore.getState().toggleTimelinePlaying();
          return;
        case "ArrowLeft":
          return stepTimeline(-1);
        case "ArrowRight":
          return stepTimeline(1);
        case "f":
        case "F":
          return dispatch(e, "view.frameSelection");
        case "v":
        case "V":
          return dispatch(e, "view.toggleViewport");
        case "1":
          return dispatch(e, "view.colorBy.gas_saturation");
        case "2":
          return dispatch(e, "view.colorBy.pressure_bar");
        case "3":
          return dispatch(e, "view.colorBy.z_co2");
        case "4":
          return dispatch(e, "view.colorBy.oil_saturation");
        default:
          return;
      }
    }

    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);
}

function dispatch(e: KeyboardEvent, commandId: string): void {
  e.preventDefault();
  runCommand(commandId);
}

function stepTimeline(delta: number): void {
  const ws = useWorkspaceStore.getState();
  ws.setTimelineStep(Math.max(0, ws.timelineStep + delta));
}
