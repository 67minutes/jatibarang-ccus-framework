import { useMemo } from "react";
import { useComposeStore } from "./compose.store";
import { requestForDisplay } from "./requestPresentation";

/**
 * The request-JSON drawer (design §7.2 — "the payload is the deck"). The full
 * request carries multi-megabyte 64×64 geology/launch-pad grids, so those blocks are
 * elided to a summary; the decision-relevant fields are shown verbatim.
 */
export function RequestDrawer() {
  const draft = useComposeStore((s) => s.draft);
  const text = useMemo(
    () => (draft ? JSON.stringify(requestForDisplay(draft), null, 2) : ""),
    [draft],
  );
  if (!draft) return null;
  return (
    <div className="request-drawer">
      <div className="request-drawer-note">
        Editable decision request. At Screen time, current wells, sources, and
        launch-pad coverage are applied; 64×64 geology and warm-history grids are elided
        here for readability.
      </div>
      <pre className="request-json mono">{text}</pre>
    </div>
  );
}
