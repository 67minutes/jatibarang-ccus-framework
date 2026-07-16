import * as Tabs from "@radix-ui/react-tabs";
import { useWorkspaceStore, type DashboardTab } from "../state/workspace.store";
import { useRunStore } from "../state/run.store";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { Composer } from "../compose/Composer";
import { RunConsole } from "../run/RunConsole";
import { RankingTable } from "../results/RankingTable";
import { Economics } from "../results/Economics";
import { Production } from "../results/Production";

/**
 * The bottom dashboard tab strip (design §4): sibling tabs, each fully
 * functional independent of the viewport. Compose is the entry tab; the run
 * console carries a live warning badge.
 */
export function DashboardTabs() {
  const activeTab = useWorkspaceStore((s) => s.activeTab);
  const setActiveTab = useWorkspaceStore((s) => s.setActiveTab);
  const warnings = useRunStore((s) => s.warnings.length);

  return (
    <Tabs.Root
      className="tabs-root"
      value={activeTab}
      onValueChange={(v) => setActiveTab(v as DashboardTab)}
    >
      <Tabs.List className="tabs-list" aria-label="Workbench panels">
        <Trigger value="ranking" label="Ranking" />
        <Trigger value="economics" label="Economics" />
        <Trigger value="production" label="Production" />
        <Trigger value="run" label="Run console" badge={warnings || undefined} />
        <Trigger value="compose" label="Compose" />
      </Tabs.List>

      <TabBody value="ranking" label="Ranking">
        <RankingTable />
      </TabBody>
      <TabBody value="economics" label="Economics">
        <Economics />
      </TabBody>
      <TabBody value="production" label="Production">
        <Production />
      </TabBody>
      <TabBody value="run" label="Run console">
        <RunConsole />
      </TabBody>
      <TabBody value="compose" label="Compose">
        <Composer />
      </TabBody>
    </Tabs.Root>
  );
}

function Trigger({
  value,
  label,
  badge,
}: {
  value: string;
  label: string;
  badge?: number;
}) {
  return (
    <Tabs.Trigger className="tab-trigger" value={value}>
      {label}
      {badge != null && <span className="tab-badge">{badge}</span>}
    </Tabs.Trigger>
  );
}

function TabBody({
  value,
  label,
  children,
}: {
  value: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <Tabs.Content className="tab-content" value={value}>
      <ErrorBoundary label={`${label} panel`}>{children}</ErrorBoundary>
    </Tabs.Content>
  );
}
