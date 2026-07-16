import { type ReactNode, useState } from "react";

/**
 * A titled, optionally collapsible panel — the docked-region primitive. Fixed
 * regions with collapse/tabs, deliberately not a floating docking framework
 * (design §4).
 */
export function Panel({
  title,
  right,
  collapsible = false,
  children,
}: {
  title: string;
  right?: ReactNode;
  collapsible?: boolean;
  children: ReactNode;
}) {
  const [collapsed, setCollapsed] = useState(false);
  return (
    <section className="panel">
      <header className="panel-head">
        <button
          type="button"
          className="panel-title"
          onClick={() => collapsible && setCollapsed((c) => !c)}
          style={{ cursor: collapsible ? "pointer" : "default" }}
        >
          {collapsible && <span className="panel-caret">{collapsed ? "▸" : "▾"}</span>}
          {title}
        </button>
        {right && <div className="panel-head-right">{right}</div>}
      </header>
      {!collapsed && <div className="panel-body">{children}</div>}
    </section>
  );
}
