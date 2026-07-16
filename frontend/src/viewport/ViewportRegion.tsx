import { useWorkspaceStore } from "../state/workspace.store";
import { ErrorBoundary } from "../ui/ErrorBoundary";
import { Viewport2D } from "./Viewport2D";
import { Viewport3D } from "./Viewport3D";

/**
 * The center viewport region. In 3D mode it renders the field-twin scene behind
 * an error boundary whose fallback is the 2D map — so a GPU/driver failure (or a
 * missing terrain asset) degrades automatically to a fully working 2D view
 * rather than a blank screen (design §5.2).
 */
export function ViewportRegion() {
  const viewport = useWorkspaceStore((s) => s.viewport);
  if (viewport === "3d") {
    return (
      <ErrorBoundary label="3D viewport" fallback={() => <Viewport2D degraded />}>
        <Viewport3D />
      </ErrorBoundary>
    );
  }
  return <Viewport2D />;
}
