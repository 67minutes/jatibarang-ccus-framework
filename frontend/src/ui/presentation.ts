const PRESET_LABELS: Record<string, string> = {
  jatibarang_demo_v1: "Demonstration launch-pad bank",
  jatibarang_full_v1: "Full launch-pad bank",
};

const QUANTITY_LABELS: Record<string, string> = {
  seed_pressure_psi: "warm-start pressure (psi)",
  seed_gas_saturation: "warm-start gas saturation (fraction)",
  seed_z_co2: "warm-start CO2 composition (fraction)",
  injection_rate_m3_day: "injection rate (m3/day)",
  injection_duration_days: "injection duration (days)",
  soak_duration_days: "soak duration (days)",
  production_duration_days: "production duration (days)",
  production_bhp_psi: "production BHP (psi)",
};

/** Keep wire identifiers internal while preserving their scientific meaning. */
export function presetDisplayName(presetId: string): string {
  return PRESET_LABELS[presetId] ?? scientificDisplayText(presetId.replaceAll("_", " "));
}

/** Humanize backend quantity identifiers without changing the API contract. */
export function quantityDisplayName(quantity: string): string {
  return (
    QUANTITY_LABELS[quantity] ??
    scientificDisplayText(quantity.replaceAll("_", " "))
  );
}

/** Apply the UI vocabulary contract to backend-authored prose and labels. */
export function scientificDisplayText(value: string): string {
  return value
    .replace(/\bjatibarang_demo_v1\b/gi, "demonstration launch-pad bank")
    .replace(/\bjatibarang_full_v1\b/gi, "full launch-pad bank")
    .replace(/\bjatibarang_[a-z0-9_]+\b/gi, "configured case-study basis")
    .replace(/\bjatibarang\b/gi, "case-study")
    .replace(
      /\bwarm-start history is a derived seed\b/gi,
      "warm-start history is reconstructed from engineering inputs",
    )
    .replace(/\bderived seed\b/gi, "derived warm-start history")
    .replace(/\bseed coverage\b/gi, "launch-pad coverage")
    .replace(/\bseed banks?\b/gi, "launch-pad bank")
    .replace(/\bseeds\b/gi, "launch pads")
    .replace(/\bseed_([a-z0-9_]+)\b/gi, (_, suffix: string) =>
      `warm-start ${suffix.replaceAll("_", " ")}`,
    )
    .replace(/\bseed\b/gi, "warm start");
}

/** Presentation-only JSON key alias; persisted/request keys remain untouched. */
export function displayWireKey(key: string): string {
  return key.replace(/seed/gi, "launch_pad");
}
