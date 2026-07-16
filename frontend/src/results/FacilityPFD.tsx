import type { FacilityWellResult } from "../api/types";
import { Badge, CostBasisBanner } from "../ui/confidence";
import { num, usd } from "../util/format";
import "./facility-pfd.css";

/**
 * Static process-flow-diagram panel (design "DWSIM in the UI"): DWSIM is never
 * run live. Key numbers bind from Feature 003's correlations for the selected
 * well's dedicated skid.
 */
export function FacilityPFD({ well }: { well: FacilityWellResult }) {
  const blocks = [
    { key: "sep", label: "3-phase\nseparator", tone: "neutral" as const },
    { key: "comp", label: "Recycle\ncompressor", tone: "neutral" as const },
    { key: "cool", label: "Inter-\ncooler", tone: "neutral" as const },
    { key: "dehy", label: "Dehy-\ndration", tone: "neutral" as const },
    { key: "pump", label: "Injection\npump", tone: "neutral" as const },
  ];
  const calibrationTone =
    well.calibration_status === "validated"
      ? "ok"
      : well.calibration_status === "outside_calibration_envelope"
        ? "warning"
        : "neutral";

  return (
    <div className="pfd">
      <div className="pfd-flow">
        {blocks.map((b, i) => (
          <div key={b.key} className="pfd-stage">
            <div className="pfd-block">{b.label}</div>
            {i < blocks.length - 1 && <span className="pfd-arrow">→</span>}
          </div>
        ))}
      </div>

      <dl className="kv pfd-kv">
        <dt>Compression power</dt>
        <dd>{num(well.compression_power_kw)} kW</dd>
        <dt>Pump power</dt>
        <dd>{num(well.pump_power_kw)} kW</dd>
        <dt>Total power</dt>
        <dd>{num(well.total_power_kw)} kW</dd>
        <dt>Separator capacity</dt>
        <dd>{num(well.separator_capacity_m3_day)} m³/day</dd>
        <dt>Facility CAPEX</dt>
        <dd>{usd(well.capex_usd)}</dd>
        <dt>Facility OPEX / yr</dt>
        <dd>{usd(well.annual_opex_usd)}</dd>
        <dt>Surface loss</dt>
        <dd>{num(well.surface_loss_fraction * 100, 2)}%</dd>
      </dl>

      <div className="pfd-calibration">
        <Badge tone={calibrationTone}>{well.calibration_status.replace(/_/g, " ")}</Badge>
        {well.calibration_flags.map((f, i) => (
          <span key={i} className="pfd-cal-flag">
            {f}
          </span>
        ))}
      </div>
      <CostBasisBanner what="Facility equipment costs" />
    </div>
  );
}
