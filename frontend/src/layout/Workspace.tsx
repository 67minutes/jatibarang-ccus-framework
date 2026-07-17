import { useEffect, useRef } from "react";
import { MenuBar } from "../chrome/MenuBar";
import { Toolbar } from "../chrome/Toolbar";
import { StatusBar } from "../chrome/StatusBar";
import { useGlobalShortcuts } from "../chrome/shortcuts";
import { useWorkbench } from "../run/useWorkbench";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { ProjectTree } from "./ProjectTree";
import { Inspector } from "./Inspector";
import { DashboardTabs } from "./DashboardTabs";
import { ViewportRegion } from "../viewport/ViewportRegion";
import { Modals } from "../chrome/Modals";
import { BannerStack } from "../ui/BannerStack";
import { useWorkspaceStore } from "../state/workspace.store";
import { useSplitPaneStore } from "../state/splitPane.store";
import { SplitHandle } from "./SplitHandle";
import "./workspace.css";

/**
 * The workbench shell: fixed regions around a persistent workspace (design §4).
 * Menu bar and toolbar on top, status bar on the bottom, and a
 * tree | (viewport / dashboard) | inspector middle. Every region is isolated
 * behind an error boundary.
 */
export function Workspace() {
  useGlobalShortcuts();
  useWorkbench();
  const panels = useWorkspaceStore((s) => s.panels);
  const togglePanel = useWorkspaceStore((s) => s.togglePanel);
  const sizes = useSplitPaneStore((s) => s.sizes);
  const centerRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const element = centerRef.current;
    if (!element || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver((entries) => {
      const height = entries[0]?.contentRect.height;
      if (!height) return;
      const state = useSplitPaneStore.getState();
      state.setSize("bottom", state.sizes.bottom, height);
    });
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <div className="workspace">
      <MenuBar />
      <Toolbar />
      <BannerStack />
      <div className="workspace-middle">
        {panels.tree && (
          <aside id="study-objects-panel" className="region region-tree" style={{ width: sizes.left }}>
            <ErrorBoundary label="Project tree">
              <ProjectTree />
            </ErrorBoundary>
          </aside>
        )}
        <SplitHandle
          panel="left"
          controls="study-objects-panel"
          collapsed={!panels.tree}
          onToggle={() => togglePanel("tree")}
        />
        <main ref={centerRef} className="region region-center">
          <div className="region-viewport">
            <ErrorBoundary label="Viewport">
              <ViewportRegion />
            </ErrorBoundary>
          </div>
          <SplitHandle
            panel="bottom"
            controls="dashboard-panel"
            collapsed={!panels.dashboard}
            onToggle={() => togglePanel("dashboard")}
            availableSize={() => centerRef.current?.clientHeight}
          />
          {panels.dashboard && (
            <div
              id="dashboard-panel"
              className="region-dashboard"
              style={{ height: sizes.bottom, maxHeight: "70%" }}
            >
              <ErrorBoundary label="Dashboard">
                <DashboardTabs />
              </ErrorBoundary>
            </div>
          )}
        </main>
        <SplitHandle
          panel="right"
          controls="inspector-panel"
          collapsed={!panels.inspector}
          onToggle={() => togglePanel("inspector")}
        />
        {panels.inspector && (
          <aside id="inspector-panel" className="region region-inspector" style={{ width: sizes.right }}>
            <ErrorBoundary label="Inspector">
              <Inspector />
            </ErrorBoundary>
          </aside>
        )}
      </div>
      <StatusBar />
      <Modals />
    </div>
  );
}
