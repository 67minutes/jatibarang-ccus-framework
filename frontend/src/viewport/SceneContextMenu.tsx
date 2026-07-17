import { useEffect, useLayoutEffect, useRef, useState } from "react";

export type SceneContextKind = "terrain" | "outline" | "well" | "source";

export interface SceneContextTarget {
  x: number;
  y: number;
  kind: SceneContextKind;
  targetId?: string;
  lat: number;
  lon: number;
}

interface SceneContextMenuProps {
  target: SceneContextTarget;
  canAddCandidateWell: boolean;
  wellName?: string;
  canRemoveWell: boolean;
  onAddSource: () => void;
  onAddWell: () => void;
  onRenameWell: (name: string) => void;
  onRemoveWell: () => void;
  onEditSource: () => void;
  onRemoveSource: () => void;
  onEnterField: () => void;
  onClose: () => void;
}

/** Compact scene action menu positioned relative to the viewport canvas. */
export function SceneContextMenu({
  target,
  canAddCandidateWell,
  wellName,
  canRemoveWell,
  onAddSource,
  onAddWell,
  onRenameWell,
  onRemoveWell,
  onEditSource,
  onRemoveSource,
  onEnterField,
  onClose,
}: SceneContextMenuProps) {
  const menuRef = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ x: target.x, y: target.y });
  const [renaming, setRenaming] = useState(false);
  const [name, setName] = useState(wellName ?? "");

  useLayoutEffect(() => {
    const menu = menuRef.current;
    const parent = menu?.parentElement;
    if (!menu || !parent) return;
    const inset = 6;
    setPosition({
      x: Math.max(
        inset,
        Math.min(target.x, parent.clientWidth - menu.offsetWidth - inset),
      ),
      y: Math.max(
        inset,
        Math.min(target.y, parent.clientHeight - menu.offsetHeight - inset),
      ),
    });
  }, [renaming, target.x, target.y]);

  useEffect(() => {
    const menu = menuRef.current;
    const firstButton = menu?.querySelector<HTMLButtonElement>("button");
    firstButton?.focus({ preventScroll: true });

    const clickAway = (event: PointerEvent) => {
      if (!menuRef.current?.contains(event.target as Node)) onClose();
    };
    const handleKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose();
        return;
      }
      if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return;
      const buttons = Array.from(
        menuRef.current?.querySelectorAll<HTMLButtonElement>("button:not(:disabled)") ?? [],
      );
      if (buttons.length === 0) return;
      event.preventDefault();
      const current = Math.max(0, buttons.indexOf(document.activeElement as HTMLButtonElement));
      const next =
        event.key === "Home"
          ? 0
          : event.key === "End"
            ? buttons.length - 1
            : (current + (event.key === "ArrowDown" ? 1 : -1) + buttons.length) %
              buttons.length;
      buttons[next].focus();
    };
    document.addEventListener("pointerdown", clickAway, true);
    window.addEventListener("keydown", handleKey, true);
    return () => {
      document.removeEventListener("pointerdown", clickAway, true);
      window.removeEventListener("keydown", handleKey, true);
    };
  }, [onClose]);

  const run = (action: () => void) => {
    action();
    onClose();
  };

  return (
    <div
      ref={menuRef}
      className="scene-context-menu"
      role="menu"
      aria-label="Scene actions"
      style={{ left: position.x, top: position.y }}
      onPointerDown={(event) => event.stopPropagation()}
      onContextMenu={(event) => event.preventDefault()}
    >
      <div className="scene-context-position" aria-hidden="true">
        {Math.abs(target.lat).toFixed(5)}°{target.lat < 0 ? "S" : "N"} ·{" "}
        {Math.abs(target.lon).toFixed(5)}°{target.lon < 0 ? "W" : "E"}
      </div>
      {target.kind === "terrain" && (
        <>
          <button type="button" role="menuitem" onClick={() => run(onAddSource)}>
            Add CO₂ source here
          </button>
          {canAddCandidateWell && (
            <button type="button" role="menuitem" onClick={() => run(onAddWell)}>
              Add candidate well
            </button>
          )}
        </>
      )}
      {target.kind === "outline" && (
        <button type="button" role="menuitem" onClick={() => run(onEnterField)}>
          Enter field
        </button>
      )}
      {target.kind === "well" &&
        (renaming ? (
          <form
            className="scene-context-rename"
            onSubmit={(event) => {
              event.preventDefault();
              const nextName = name.trim();
              if (!nextName) return;
              onRenameWell(nextName);
              onClose();
            }}
          >
            <label htmlFor="scene-well-name">Well name</label>
            <input
              id="scene-well-name"
              value={name}
              onChange={(event) => setName(event.target.value)}
              required
              autoFocus
            />
            <div>
              <button type="submit">Save</button>
              <button type="button" onClick={() => setRenaming(false)}>
                Cancel
              </button>
            </div>
          </form>
        ) : (
          <>
            <button type="button" role="menuitem" onClick={() => setRenaming(true)}>
              Rename well
            </button>
            {canRemoveWell ? (
              <button
                type="button"
                role="menuitem"
                className="scene-context-danger"
                onClick={() => run(onRemoveWell)}
              >
                Remove well
              </button>
            ) : null}
          </>
        ))}
      {target.kind === "source" && (
        <>
          <button type="button" role="menuitem" onClick={() => run(onEditSource)}>
            Edit source
          </button>
          <button
            type="button"
            role="menuitem"
            className="scene-context-danger"
            onClick={() => run(onRemoveSource)}
          >
            Remove source
          </button>
        </>
      )}
    </div>
  );
}
