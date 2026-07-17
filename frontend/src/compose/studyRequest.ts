import type { ReservoirImportResponse } from "../api/client";
import type { InlineScreenRequest, OperationalGrid } from "../api/types";
import type { FieldSetupMemo } from "../memo/studyMemo";
import {
  coveredGridSchedules,
  nativeScheduleAvailability,
  type GridScheduleCoverage,
  type NativeScheduleAvailability,
  type OperatingScheduleInput,
} from "./coverage";
import type { StudyRequestBase } from "./defaults";

const FINGERPRINT_PATTERN = /^[0-9A-F]{64}$/;

export class NoCoveredSchedulesError extends Error {
  constructor() {
    super("No screened schedules: none of the grid combinations have launch pads.");
    this.name = "NoCoveredSchedulesError";
  }
}

export interface StudySchedulePlan {
  coverage: GridScheduleCoverage;
  native: NativeScheduleAvailability;
  /** Schedules submitted when coverage limiting is active. */
  schedules: OperatingScheduleInput[];
  usesNativeFallback: boolean;
}

export interface BuildStudyRequestOptions {
  field: FieldSetupMemo;
  imported: ReservoirImportResponse;
  base: StudyRequestBase;
  /** Keep the editable grid for a draft, or limit a submitted request. */
  scheduleMode?: "grid" | "covered";
}

/** Mirror the CO2Source bounds that cannot be represented by the field store type. */
export function sourceValidationIssue(
  sources: FieldSetupMemo["sources"],
): string | null {
  for (const source of sources) {
    if (
      !Number.isFinite(source.annual_capacity_t) ||
      source.annual_capacity_t <= 0 ||
      !Number.isFinite(source.max_mass_flow_kg_s) ||
      source.max_mass_flow_kg_s <= 0 ||
      !Number.isFinite(source.outlet_pressure_bar) ||
      source.outlet_pressure_bar < 80 ||
      !Number.isFinite(source.outlet_temperature_c) ||
      !Number.isFinite(source.co2_purity) ||
      source.co2_purity < 0.95 ||
      source.co2_purity > 1
    ) {
      return `${source.name || source.id} has invalid capacity, flow, pressure, temperature, or CO2 purity.`;
    }
  }
  return null;
}

interface SeedCatalog {
  seeds: Record<string, Record<string, unknown>>;
  seedByFingerprint: Record<string, string>;
  fingerprints: string[];
}

function normalizedFingerprint(value: string): string {
  const fingerprint = value.toUpperCase();
  if (!FINGERPRINT_PATTERN.test(fingerprint)) {
    throw new Error(`Invalid launch-pad fingerprint: ${value}`);
  }
  return fingerprint;
}

function seedCatalog(imported: ReservoirImportResponse): SeedCatalog {
  const seeds: Record<string, Record<string, unknown>> = {};
  const seedByFingerprint: Record<string, string> = {};

  const add = (
    declaredFingerprint: string,
    seed: Record<string, unknown>,
  ) => {
    const fingerprint = normalizedFingerprint(declaredFingerprint);
    const payloadFingerprint = seed.schedule_fingerprint;
    if (
      typeof payloadFingerprint === "string" &&
      normalizedFingerprint(payloadFingerprint) !== fingerprint
    ) {
      throw new Error(
        `Launch-pad payload fingerprint does not match ${fingerprint}.`,
      );
    }
    const seedId = `launchpad:${imported.model_id}:${fingerprint}`;
    seeds[seedId] = seed;
    seedByFingerprint[fingerprint] = seedId;
  };

  add(imported.native_fingerprint, imported.native_seed);
  for (const [fingerprint, seed] of Object.entries(imported.bank_seeds).sort(
    ([left], [right]) => left.localeCompare(right),
  )) {
    add(fingerprint, seed);
  }

  return {
    seeds,
    seedByFingerprint,
    fingerprints: Object.keys(seedByFingerprint).sort(),
  };
}

function nativeSchedule(imported: ReservoirImportResponse): OperatingScheduleInput {
  const source = imported.native_schedule;
  const number = (key: keyof OperatingScheduleInput): number => {
    const value = source[key];
    if (typeof value !== "number" || !Number.isFinite(value)) {
      throw new Error(`Imported native schedule is missing ${key}.`);
    }
    return value;
  };
  const cycles = number("cycles");
  if (!Number.isInteger(cycles)) {
    throw new Error("Imported native schedule cycles must be an integer.");
  }
  return {
    injection_rate_m3_day: number("injection_rate_m3_day"),
    injection_reference_pressure_bar: number(
      "injection_reference_pressure_bar",
    ),
    injection_reference_temperature_c: number(
      "injection_reference_temperature_c",
    ),
    injection_duration_days: number("injection_duration_days"),
    soak_duration_days: number("soak_duration_days"),
    production_duration_days: number("production_duration_days"),
    production_bhp_psi: number("production_bhp_psi"),
    cycles,
  };
}

export function studySchedulePlan(
  grid: OperationalGrid,
  imported: ReservoirImportResponse,
): StudySchedulePlan {
  const catalog = seedCatalog(imported);
  const coverage = coveredGridSchedules(grid, catalog.fingerprints);
  const injectionDuration = imported.native_schedule.injection_duration_days;
  if (typeof injectionDuration !== "number" || !Number.isFinite(injectionDuration)) {
    throw new Error("Imported native schedule has no injection duration.");
  }
  const native = nativeScheduleAvailability(
    grid,
    injectionDuration,
    imported.native_fingerprint,
    catalog.fingerprints,
  );
  if (coverage.covered > 0) {
    return {
      coverage,
      native,
      schedules: coverage.enabled,
      usesNativeFallback: false,
    };
  }
  return {
    coverage,
    native,
    schedules: native.available ? [nativeSchedule(imported)] : [],
    usesNativeFallback: native.available,
  };
}

const PRODUCED_CO2 = {
  mole_fraction: 0.65,
  provenance: {
    source_class: "engineering_assumption",
    source_id: "feature005-produced-gas-co2-v1",
    notes:
      "Explicit screening composition assumption; independent of storage inventory.",
    metadata: { basis: "provenance_tagged_candidate_input" },
  },
};

/** Build the inline request from the live field and its imported MRST model. */
export function buildStudyRequest({
  field,
  imported,
  base,
  scheduleMode = "covered",
}: BuildStudyRequestOptions): InlineScreenRequest {
  if (
    field.reservoir.model_id !== imported.model_id ||
    field.reservoir.sha256 !== imported.sha256
  ) {
    throw new Error("The runtime reservoir payload does not match this study.");
  }

  const catalog = seedCatalog(imported);
  const grid = base.operational_grid;
  if (!grid) throw new Error("An operational grid is required for this study.");
  const plan = studySchedulePlan(grid, imported);
  if (scheduleMode === "covered" && plan.schedules.length === 0) {
    throw new NoCoveredSchedulesError();
  }

  const useGrid =
    scheduleMode === "grid" || plan.coverage.covered === plan.coverage.total;
  const candidates = field.wells.map((well) => ({
    candidate_id: well.id,
    location: { latitude: well.lat, longitude: well.lon },
    geology_id: imported.model_id,
    seed_by_schedule_fingerprint: { ...catalog.seedByFingerprint },
    produced_co2: structuredClone(PRODUCED_CO2),
  }));
  const sources = field.sources.map((source) => ({
    id: source.id,
    name: source.name,
    location: { latitude: source.lat, longitude: source.lon },
    capacity_tonnes_per_year: source.annual_capacity_t,
    max_mass_flow_kg_s: source.max_mass_flow_kg_s,
    outlet_pressure_bar: source.outlet_pressure_bar,
    outlet_temperature_c: source.outlet_temperature_c,
    co2_purity: source.co2_purity,
  }));

  return {
    mode: "inline",
    run_id: null,
    geologies: { [imported.model_id]: imported.geology },
    seeds: catalog.seeds,
    candidates,
    sources,
    operational_grid: useGrid ? structuredClone(grid) : null,
    schedules: useGrid ? null : plan.schedules.map((schedule) => ({ ...schedule })),
    annual_co2_budget_tonnes: base.annual_co2_budget_tonnes,
    carbon_prices: structuredClone(base.carbon_prices),
    fiscal_cases: structuredClone(base.fiscal_cases),
    economic_assumptions: structuredClone(base.economic_assumptions),
    project_life_years: base.project_life_years,
    supply_scenarios: base.supply_scenarios,
    cost_case: base.cost_case,
    selection_fiscal_case_id: base.selection_fiscal_case_id,
    shortlist_top_k: base.shortlist_top_k,
    detailed_top_k: base.detailed_top_k,
    scenario_limit: 4096,
    terrain_id: field.terrain.terrain_id,
    routing_basis_id: "jatibarang_case_study_v1",
    pipeline_basis_id: "jatibarang_case_study_v1",
  };
}
