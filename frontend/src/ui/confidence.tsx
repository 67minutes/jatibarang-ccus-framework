import type { ScreenFlag } from "../api/types";
import { scientificDisplayText } from "./presentation";
import "./confidence.css";

/**
 * Confidence chrome (design §8): the UI never claims more than the backend
 * evidence does. Flags, low-confidence markers, and cost-basis caveats render
 * wherever the affected numbers appear, worded to be quotable.
 */

export function Badge({
  tone,
  children,
  title,
}: {
  tone: "info" | "warning" | "danger" | "ok" | "neutral";
  children: React.ReactNode;
  title?: string;
}) {
  return (
    <span className={`badge badge-${tone}`} title={title}>
      {children}
    </span>
  );
}

export function FlagList({ flags }: { flags: ScreenFlag[] }) {
  if (flags.length === 0) return null;
  return (
    <ul className="flag-list">
      {flags.map((f, i) => (
        <li key={`${f.code}-${i}`} className={`flag flag-${f.severity}`}>
          <span className="flag-code">
            {scientificDisplayText(f.code.replace(/_/g, " "))}
          </span>
          <span className="flag-msg">{scientificDisplayText(f.message)}</span>
          {f.scenario_ids.length > 0 && (
            <span className="flag-scope mono" title={f.scenario_ids.join(", ")}>
              {f.scenario_ids.length} cell{f.scenario_ids.length > 1 ? "s" : ""}
            </span>
          )}
        </li>
      ))}
    </ul>
  );
}

/** Standing caveat that costs are screening-grade, not FEED/PSC/vendor. */
export function CostBasisBanner({ what }: { what: string }) {
  return (
    <p className="cost-basis-note">
      {what} are literature-aligned screening correlations — not FEED, vendor
      quotations, or final-paper economics.
    </p>
  );
}

export function ConfidenceNote({ reasons }: { reasons: string[] }) {
  if (reasons.length === 0) return null;
  return (
    <div className="confidence-note">
      <Badge tone="warning">low confidence</Badge>
      <ul>
        {reasons.map((r, i) => (
          <li key={i}>{scientificDisplayText(r)}</li>
        ))}
      </ul>
    </div>
  );
}
