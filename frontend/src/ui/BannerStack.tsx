import { useUiStore } from "../state/ui.store";
import { scientificDisplayText } from "./presentation";

/** Dismissable banner stack (e.g. 503 dependency banners) below the toolbar. */
export function BannerStack() {
  const banners = useUiStore((s) => s.banners);
  const dismiss = useUiStore((s) => s.dismissBanner);
  if (banners.length === 0) return null;
  return (
    <div className="banner-stack">
      {banners.map((b) => (
        <div key={b.id} className={`banner banner-${b.severity}`} role="status">
          <span>{scientificDisplayText(b.message)}</span>
          <button
            type="button"
            className="banner-dismiss"
            aria-label="Dismiss"
            onClick={() => dismiss(b.id)}
          >
            ✕
          </button>
        </div>
      ))}
    </div>
  );
}
