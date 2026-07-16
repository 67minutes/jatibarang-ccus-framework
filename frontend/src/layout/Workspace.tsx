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

  return (
    <div className="workspace">
      <MenuBar />
      <Toolbar />
      <BannerStack />
      <div className="workspace-middle">
        {panels.tree && (
          <aside className="region region-tree">
            <ErrorBoundary label="Project tree">
              <ProjectTree />
            </ErrorBoundary>
          </aside>
        )}
        <main className="region region-center">
          <div className="region-viewport">
            <ErrorBoundary label="Viewport">
              <ViewportRegion />
            </ErrorBoundary>
          </div>
          {panels.dashboard && (
            <div className="region-dashboard">
              <ErrorBoundary label="Dashboard">
                <DashboardTabs />
              </ErrorBoundary>
            </div>
          )}
        </main>
        {panels.inspector && (
          <aside className="region region-inspector">
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
