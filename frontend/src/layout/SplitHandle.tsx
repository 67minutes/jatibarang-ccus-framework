import { useEffect, useRef, type KeyboardEvent, type PointerEvent } from "react";
import {
  SPLIT_PANE_SIZES,
  splitPaneLimits,
  useSplitPaneStore,
  type SplitPaneId,
} from "../state/splitPane.store";

interface SplitHandleProps {
  panel: SplitPaneId;
  controls: string;
  collapsed: boolean;
  onToggle: () => void;
  availableSize?: () => number | undefined;
}

const KEYBOARD_STEP = 8;
const KEYBOARD_LARGE_STEP = 32;

/** Accessible pointer/keyboard divider with an adjacent collapse affordance. */
export function SplitHandle({
  panel,
  controls,
  collapsed,
  onToggle,
  availableSize,
}: SplitHandleProps) {
  const size = useSplitPaneStore((state) => state.sizes[panel]);
  const setSize = useSplitPaneStore((state) => state.setSize);
  const resetSize = useSplitPaneStore((state) => state.resetSize);
  const drag = useRef<{ pointerId: number; origin: number; size: number } | null>(null);
  const orientation = panel === "bottom" ? "horizontal" : "vertical";
  const available = () => availableSize?.();
  const limits = splitPaneLimits(panel, available());

  useEffect(
    () => () => {
      document.body.classList.remove("workspace-resizing");
    },
    [],
  );

  const resizeFromPointer = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag.current || drag.current.pointerId !== event.pointerId) return;
    const coordinate = panel === "bottom" ? event.clientY : event.clientX;
    const direction = panel === "left" ? 1 : -1;
    setSize(panel, drag.current.size + direction * (coordinate - drag.current.origin), available());
  };

  const stopPointerResize = (event: PointerEvent<HTMLDivElement>) => {
    if (!drag.current || drag.current.pointerId !== event.pointerId) return;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    drag.current = null;
    document.body.classList.remove("workspace-resizing");
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    if (collapsed) return;
    const step = event.shiftKey ? KEYBOARD_LARGE_STEP : KEYBOARD_STEP;
    let next: number | null = null;

    if (event.key === "Home") next = limits.min;
    if (event.key === "End" && Number.isFinite(limits.max)) next = limits.max;
    if (orientation === "vertical" && event.key === "ArrowLeft") next = size - step;
    if (orientation === "vertical" && event.key === "ArrowRight") next = size + step;
    // The bottom panel grows upward, so ArrowUp increases its value.
    if (orientation === "horizontal" && event.key === "ArrowUp") next = size + step;
    if (orientation === "horizontal" && event.key === "ArrowDown") next = size - step;

    if (next == null) return;
    event.preventDefault();
    setSize(panel, next, available());
  };

  const label = panel === "left" ? "Study objects" : panel === "right" ? "Inspector" : "Dashboard";
  const toggleGlyph =
    panel === "left"
      ? collapsed
        ? "→"
        : "←"
      : panel === "right"
        ? collapsed
          ? "←"
          : "→"
        : collapsed
          ? "↑"
          : "↓";

  return (
    <div
      className={`workspace-splitter-shell ${orientation}${collapsed ? " collapsed" : ""}`}
      data-panel={panel}
    >
      <div
        className="workspace-splitter-grip"
        role="separator"
        aria-label={`Resize ${label.toLowerCase()} panel`}
        aria-controls={controls}
        aria-orientation={orientation}
        aria-valuemin={Number.isFinite(limits.min) ? Math.round(limits.min) : undefined}
        aria-valuemax={Number.isFinite(limits.max) ? Math.round(limits.max) : undefined}
        aria-valuenow={!collapsed ? Math.round(size) : undefined}
        aria-valuetext={!collapsed ? `${Math.round(size)} pixels` : "Panel collapsed"}
        aria-disabled={collapsed}
        tabIndex={collapsed ? -1 : 0}
        title={`Drag to resize ${label.toLowerCase()}; double-click to reset`}
        onDoubleClick={() => resetSize(panel, available())}
        onKeyDown={onKeyDown}
        onPointerDown={(event) => {
          if (collapsed || event.button !== 0) return;
          const origin = panel === "bottom" ? event.clientY : event.clientX;
          drag.current = { pointerId: event.pointerId, origin, size };
          event.currentTarget.setPointerCapture(event.pointerId);
          document.body.classList.add("workspace-resizing");
          event.preventDefault();
        }}
        onPointerMove={resizeFromPointer}
        onPointerUp={stopPointerResize}
        onPointerCancel={stopPointerResize}
      />
      <button
        type="button"
        className="workspace-splitter-toggle"
        aria-controls={controls}
        aria-expanded={!collapsed}
        aria-label={`${collapsed ? "Restore" : "Collapse"} ${label.toLowerCase()} panel`}
        title={`${collapsed ? "Restore" : "Collapse"} ${label.toLowerCase()} panel`}
        onClick={onToggle}
      >
        <span aria-hidden="true">{toggleGlyph}</span>
      </button>
    </div>
  );
}

export const SPLIT_HANDLE_DEFAULTS = SPLIT_PANE_SIZES;
