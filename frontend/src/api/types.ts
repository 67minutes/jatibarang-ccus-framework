/**
 * Domain API types for the CCUS screening workbench.
 *
 * The OpenAPI contract (`specs/005-screening-api/contracts/openapi.yaml`) is a
 * *summary* — `openapi-typescript` emits it into `types.gen.ts` for path /
 * method / status-code verification, but the domain schemas there are stubs.
 * This file is the faithful, hand-authored mirror of the backend Pydantic
 * models and is the single source of truth for request/response shapes:
 *
 *   - `src/jatibarang_ccus/contracts.py`
 *   - `src/jatibarang_ccus/screening/schemas.py`
 *   - `src/jatibarang_ccus/surrogate/schemas.py`
 *
 * Keep it in lockstep with those models. The pivot/rendering fields the UI
 * depends on are covered by Vitest fixtures so drift surfaces as a test failure.
 */

// ----------------------------------------------------------------------------
// Shared primitives (contracts.py)
// ----------------------------------------------------------------------------

export interface Coordinate {
  latitude: number;
  longitude: number;
}

export interface CO2Source {
  id: string;
  name: string;
  location: Coordinate;
  capacity_tonnes_per_year: number;
  max_mass_flow_kg_s: number;
  outlet_pressure_bar: number;
  outlet_temperature_c: number;
  co2_purity: number;
}

export type CostCase = "low" | "base" | "high";
export type FiscalMode = "pre_tax" | "cost_recovery" | "gross_split";
export type FlagSeverity = "info" | "warning" | "blocking";

// ----------------------------------------------------------------------------
// Surrogate prediction (surrogate/schemas.py)
// ----------------------------------------------------------------------------

export interface Grid2D {
  /** Always (64, 64). */
  shape: [number, number];
  /** Row-major flat array of 4096 finite values. */
  values: number[];
}

export interface ReservoirGridGeometry {
  nx: 64;
  ny: 64;
  nz: 1;
  length_x_m: number;
  length_y_m: number;
  thickness_m: number;
}

export interface ReservoirStaticFields {
  permeability_md: Grid2D;
  porosity_fraction: Grid2D;
  structure_m: Grid2D;
  fracture_proxy: Grid2D;
  barrier: Grid2D;
  facies: Grid2D;
  well_mask: Grid2D;
  completion_mask: Grid2D;
}

export interface ReservoirBaselineState {
  pressure_bar: Grid2D;
  gas_saturation: Grid2D;
  z_co2: Grid2D;
  oil_saturation: Grid2D | null;
}

export interface ReservoirFieldMetadata {
  label: string;
  unit: string;
  minimum: number;
  maximum: number;
  scale: "linear" | "log10" | "categorical" | "binary";
  source_class: string;
}

/** Static simulator-style geometry aligned with one detailed prediction. */
export interface ReservoirVisualization {
  scenario_id: string;
  geology_id: string;
  grid: ReservoirGridGeometry;
  static_fields: ReservoirStaticFields;
  baseline_state: ReservoirBaselineState | null;
  field_metadata: Record<string, ReservoirFieldMetadata>;
  provenance: Record<string, unknown>;
}

export type PlumeStage = "inject" | "soak" | "produce";
export type FrameOrigin = "seed" | "surrogate";

export interface TimelineStep {
  index: number;
  dt_days: number;
  elapsed_days: number;
  stage: PlumeStage;
  cycle: number;
  origin: FrameOrigin;
}

/** Per-cell fields for one timeline step. Only present for detailed scenarios. */
export interface SpatialFrame {
  step_index: number;
  pressure_bar: Grid2D;
  gas_saturation: Grid2D;
  z_co2: Grid2D;
  oil_saturation: Grid2D | null;
  origin: FrameOrigin;
}

/** The four per-cell fields the viewport can encode as height or color. */
export type CellField = "z_co2" | "gas_saturation" | "pressure_bar" | "oil_saturation";

export interface ProductionSeries {
  delta_oil_m3: number[];
  delta_gas_m3: number[];
  cumulative_oil_m3: number[];
  cumulative_gas_m3: number[];
}

export interface InventorySeries {
  status: "available" | "unavailable";
  /** Per timeline step (NOT per cell). */
  co2_inventory_tonnes: (number | null)[];
  injected_co2_tonnes: number[];
  produced_back_co2_tonnes: (number | null)[];
  reconciliation_residual_tonnes: (number | null)[];
  method: string;
  caveat: string;
}

export interface PlumeSummary {
  maximum_z_co2_area_m2: number;
  maximum_gas_area_m2: number;
  influence_radius_m: number;
  z_co2_threshold: number;
  gas_saturation_threshold: number;
}

export interface ExtrapolationFlag {
  quantity: string;
  observed_min: number;
  observed_max: number;
  trained_min: number;
  trained_max: number;
  is_extrapolation: boolean;
  evaluated: boolean;
}

export interface ConfidenceMetadata {
  band: string;
  horizon_steps: number;
  metrics: Record<string, number | string | null>;
  extended_horizon: boolean;
  low_confidence_reasons: string[];
}

export interface PredictionResult {
  scenario_id: string;
  timeline: TimelineStep[];
  production: ProductionSeries;
  inventory: InventorySeries;
  plume: PlumeSummary;
  extrapolation_flags: ExtrapolationFlag[];
  confidence: ConfidenceMetadata;
  provenance: Record<string, string | number | boolean>;
  /** Present only when this scenario was requested as a detailed prediction. */
  fields: SpatialFrame[] | null;
}

// ----------------------------------------------------------------------------
// Pipeline / routing geometry (contracts.py)
// ----------------------------------------------------------------------------

export interface PressureProfilePoint {
  distance_km: number;
  elevation_m: number;
  pressure_bar: number;
  hydraulic_head_bar: number;
  density_kg_m3: number;
  velocity_m_s: number;
}

export interface BuiltSegment {
  segment_id: string;
  from_node: string;
  to_node: string;
  diameter_in: number;
  maop_bar: number;
  length_km: number;
  flow_tonnes_per_year: number;
  peak_mass_flow_kg_s: number;
  velocity_m_s: number;
  inlet_pressure_bar: number;
  outlet_pressure_bar: number;
  pressure_drop_bar: number;
  dense_phase_ok: boolean;
  maop_ok: boolean;
  continuous_profile: PressureProfilePoint[];
  allocated_lifecycle_cost_usd: number;
}

export interface BoosterStation {
  node_id: string;
  suction_pressure_bar: number;
  discharge_pressure_bar: number;
  lift_bar: number;
  mass_flow_kg_s: number;
  power_kw: number;
  capex_usd: number;
  annual_energy_cost_usd: number;
}

export type PipelineDomainStatus =
  | "accepted"
  | "no_viable_network"
  | "infeasible"
  | "not_solved_to_tolerance"
  | "hydraulic_verification_failed";

export interface NetworkCostBreakdown {
  cost_case: CostCase;
  currency: string;
  cost_year: number;
  pipeline_capex_usd: number;
  booster_capex_usd: number;
  annual_maintenance_usd: number;
  annual_booster_energy_usd: number;
  annual_opex_usd: number;
  commodity_supply_usd_per_tonne: number;
  present_value_lifecycle_cost_usd: number;
  levelized_transport_usd_per_tonne: number;
  levelized_delivered_usd_per_tonne: number;
  provenance: Record<string, unknown>;
}

export interface PipelineDesignResult {
  domain_status: PipelineDomainStatus;
  solver: string;
  solver_status: string;
  termination_condition: string;
  objective_mode: "max_net_value" | "min_lifecycle_cost";
  objective_value_usd: number | null;
  optimality_gap: number | null;
  selected_wells: string[];
  built_segments: BuiltSegment[];
  boosters: BoosterStation[];
  node_pressures_bar: Record<string, number>;
  source_annual_flows_tonnes: Record<string, number>;
  delivered_cost_usd_per_tonne: Record<string, number>;
  per_well_allocated_cost_usd: Record<string, number>;
  supply_mode_by_well?: Record<string, "pipeline" | "trucking">;
  costs: NetworkCostBreakdown;
  solve_time_seconds: number;
  /** May carry route node geometry for the map overlay. */
  route_provenance: Record<string, unknown>;
  pipeline_capex_usd: number;
  booster_capex_usd: number;
  annual_opex_usd: number;
  total_network_cost_usd: number;
}

export interface TruckingLeg {
  candidate_id: string;
  distance_km: number;
  annual_mass_tonnes: number;
  route: [number, number][] | null;
}

export interface TruckingSupplyResult {
  scenario_id: string;
  mode: "trucking";
  cost_case: CostCase;
  annual_mass_tonnes: number;
  distance_km: number;
  commodity_supply_usd_per_tonne: number;
  levelized_delivered_usd_per_tonne: number;
  annual_cost_usd: number;
  present_value_lifecycle_cost_usd: number;
  distance_provenance: string;
  legs: TruckingLeg[] | null;
  provenance: Record<string, unknown>;
}

// ----------------------------------------------------------------------------
// Facility (contracts.py)
// ----------------------------------------------------------------------------

export type FacilityCalibrationStatus =
  | "validated"
  | "outside_calibration_envelope"
  | "unvalidated";

export interface FacilityEquipmentItem {
  equipment_id: string;
  candidate_id: string;
  equipment_type:
    | "injection_pump"
    | "recycle_compressor"
    | "intercooler"
    | "dehydration"
    | "three_phase_separator"
    | "balance_of_plant";
  duty_value: number;
  duty_unit: string;
  power_kw: number;
  capex_usd: number;
  annual_opex_usd: number;
  specifications: Record<string, unknown>;
}

export interface FacilityWellResult {
  candidate_id: string;
  input_fingerprint: string;
  equipment: FacilityEquipmentItem[];
  compression_power_kw: number;
  pump_power_kw: number;
  total_power_kw: number;
  separator_capacity_m3_day: number;
  capex_usd: number;
  annual_opex_usd: number;
  surface_loss_tonnes_per_year: number;
  surface_loss_fraction: number;
  calibration_status: FacilityCalibrationStatus;
  calibration_flags: string[];
}

export interface FacilityPortfolioResult {
  portfolio_id: string;
  validation_status: FacilityCalibrationStatus;
  well_results: FacilityWellResult[];
  total_capex_usd: number;
  total_annual_opex_usd: number;
  total_surface_loss_tonnes_per_year: number;
}

// ----------------------------------------------------------------------------
// Economics (contracts.py)
// ----------------------------------------------------------------------------

export type MetricStatus =
  | "computed"
  | "already_profitable"
  | "zero_storage"
  | "not_bracketed"
  | "no_root"
  | "multiple_roots"
  | "never_paid_back";

export interface EconomicMetric {
  value: number | null;
  status: MetricStatus;
  method: string;
}

export interface AnnualCashFlow {
  year: number;
  oil_revenue_usd: number;
  gas_revenue_usd: number;
  carbon_revenue_usd: number;
  supply_cost_usd: number;
  pipeline_opex_usd: number;
  facility_opex_usd: number;
  capex_usd: number;
  pre_tax_cashflow_usd: number;
  post_fiscal_cashflow_usd: number;
  discounted_post_fiscal_cashflow_usd: number;
}

export interface EconomicBreakdown {
  oil_revenue_usd: number;
  gas_revenue_usd: number;
  carbon_revenue_usd: number;
  lifting_cost_usd: number;
  workover_cost_usd: number;
  mrv_cost_usd: number;
  co2_supply_and_transport_usd: number;
  pipeline_capex_usd: number;
  booster_capex_usd: number;
  pipeline_opex_usd: number;
  facility_capex_usd: number;
  facility_opex_usd: number;
  carbon_tax_usd: number;
  total_revenue_usd: number;
  total_cost_usd: number;
}

export interface StorageReconciliation {
  injected_co2_tonnes: number;
  primary_net_stored_co2_tonnes: number;
  divergence_fraction_of_injected: number;
  mass_balance_passed: boolean;
  low_confidence: boolean;
  reasons: string[];
}

export interface EconomicScenarioResult {
  portfolio_id: string;
  carbon_price_scenario_id: string;
  fiscal_case_id: string;
  fiscal_mode: FiscalMode;
  annual_cashflows: AnnualCashFlow[];
  storage: StorageReconciliation;
  breakdown: EconomicBreakdown;
  pre_tax_npv_usd: number;
  npv_usd: number;
  npv_low_usd: number;
  npv_high_usd: number;
  irr: EconomicMetric;
  discounted_payback: EconomicMetric;
  break_even_carbon_price: EconomicMetric;
  break_even_oil_price: EconomicMetric;
  low_confidence: boolean;
  confidence_reasons: string[];
}

export interface EconomicBatchResult {
  economic_basis_version: string;
  currency_basis: string;
  scenario_count: number;
  results: EconomicScenarioResult[];
  elapsed_seconds: number;
  accounting_verdict: "PASS" | "FAIL";
  qualification: string;
}

// ----------------------------------------------------------------------------
// Screening result (screening/schemas.py)
// ----------------------------------------------------------------------------

export interface ScreenFlag {
  code: string;
  severity: FlagSeverity;
  source_module: string;
  /** Ties a warning to specific well x price cells (cell-addressable). */
  scenario_ids: string[];
  message: string;
}

export interface InterferencePair {
  first_well_id: string;
  second_well_id: string;
  distance_m: number;
  radius_sum_m: number;
  overlap: boolean;
  recommendations: string[];
}

export interface InterferenceReport {
  well_ids: string[];
  matrix: boolean[][];
  flagged_pairs: InterferencePair[];
}

export interface SelectionDiscrepancyAudit {
  original_selected_wells: string[];
  audit_selected_wells: string[];
  entrants: string[];
  exits: string[];
  changed: boolean;
  original_objective_usd: number | null;
  audit_objective_usd: number | null;
  value_deltas_usd: Record<string, number>;
}

export interface WellStrategyResult {
  candidate_id: string;
  scenario_id: string;
  schedule: Record<string, number>;
  selected: boolean;
  annual_demand_tonnes: number;
  peak_mass_flow_kg_s: number;
  preliminary_npv_usd: number;
  pre_logistics_value_usd: number;
  prediction: PredictionResult;
  facility: Record<string, unknown> | null;
  designated_economics: Record<string, unknown> | null;
  flags: ScreenFlag[];
}

export interface TruckingCounterfactual {
  supply: TruckingSupplyResult;
  economics: EconomicBatchResult;
}

/** Geometry-only candidate routes; never a selected development/economic claim. */
export interface TruckingRoutePreview {
  distance_provenance: string;
  legs: TruckingLeg[];
}

/** One plan per carbon price. The scrubber selects among these client-side. */
export interface CarbonPricePlan {
  carbon_price_scenario_id: string;
  carbon_price_usd_per_tonne: number;
  domain_status: string;
  selected_wells: string[];
  pipeline: PipelineDesignResult;
  facility: FacilityPortfolioResult | null;
  economics: EconomicBatchResult | null;
  trucking_counterfactual: TruckingCounterfactual | null;
  trucking_route_preview: TruckingRoutePreview | null;
  well_strategies: WellStrategyResult[];
  interference: InterferenceReport;
  discrepancy_audit: SelectionDiscrepancyAudit | null;
  flags: ScreenFlag[];
  logistics_mode?: "pipeline" | "trucking" | "hybrid" | "none";
}

export interface CrossPriceTransition {
  from_scenario_id: string;
  to_scenario_id: string;
  entrants: string[];
  exits: string[];
}

export interface CrossPriceComparison {
  selection_by_carbon_price: Record<string, string[]>;
  transitions: CrossPriceTransition[];
  pivot_observed: boolean;
}

export interface ValidationShortlistItem {
  rank: number;
  candidate_id: string;
  scenario_id: string;
  carbon_price_scenario_ids: string[];
  designated_npv_usd: number | null;
  reasons: string[];
}

export interface RunTimings {
  total_seconds: number;
  stages_seconds: Record<string, number>;
  milp_solve_seconds: number;
}

export interface ScreenResult {
  run_id: string;
  request_fingerprint: string;
  status: "completed" | "completed_with_failures";
  logical_scenario_count: number;
  unique_inference_count: number;
  inference_cache_hits: number;
  plans: CarbonPricePlan[];
  cross_price_comparison: CrossPriceComparison;
  shortlist: ValidationShortlistItem[];
  detailed_predictions: Record<string, PredictionResult>;
  detailed_reservoirs: Record<string, ReservoirVisualization>;
  timings: RunTimings;
  warnings: string[];
  provenance_catalog: Record<string, unknown>;
}

// ----------------------------------------------------------------------------
// Progress events (screening/schemas.py + progress.py wire format)
// ----------------------------------------------------------------------------

export type ProgressEventType =
  | "run_started"
  | "stage_started"
  | "progress"
  | "stage_completed"
  | "warning"
  | "result"
  | "error"
  | "cancelled"
  | "heartbeat";

export interface ProgressEvent {
  run_id: string;
  sequence: number;
  timestamp: string;
  event: ProgressEventType;
  stage: string;
  completed: number;
  total: number;
  message: string;
  payload: Record<string, unknown>;
}

// Real orchestrator stage names, in order (screening/orchestrator.py). The
// per-price portfolio stages are emitted as `portfolio:{carbon_price_id}`.
export const STAGE_ORDER = [
  "resolve",
  "surrogate",
  "preliminary_economics",
  "routing",
] as const;
export const PORTFOLIO_STAGE_PREFIX = "portfolio:";

// ----------------------------------------------------------------------------
// Health / presets (screening/schemas.py)
// ----------------------------------------------------------------------------

export interface PresetInfo {
  preset_id: "jatibarang_demo_v1" | "jatibarang_full_v1";
  logical_scenarios: number;
  geology_count: number;
  schedule_count: number;
  ready: boolean;
  manifest_path: string;
  payload_sha256: string;
  reason: string;
  component_catalog: Record<string, unknown>;
}

export interface HealthResponse {
  status: "ready" | "degraded";
  surrogate_loaded: boolean;
  solver_available: boolean;
  active_runs: number;
  presets: PresetInfo[];
  details: Record<string, unknown>;
}

// ----------------------------------------------------------------------------
// Request shapes (screening/schemas.py). The composer builds InlineScreenRequest.
// ----------------------------------------------------------------------------

export type SupplyScenario = "optimized_pipeline" | "trucking_counterfactual";

/** Editable carbon-price entry (contracts.py CarbonPriceScenario). */
export interface CarbonPriceScenario {
  scenario_id: string;
  carbon_price_usd_per_tonne: number;
  source_type: "market_observation" | "economic_assumption";
  provenance: unknown[];
}

/** Minimal fiscal-case view for the composer's selection control. */
export interface FiscalCaseLite {
  case_id: string;
  mode: FiscalMode;
}

export interface OperationalGrid {
  injection_rate_m3_day: number[];
  injection_duration_days: number[];
  soak_duration_days: number[];
  production_duration_days: number[];
  production_bhp_psi: number[];
  cycles: number[];
}

export interface PresetScreenRequest {
  mode: "preset";
  preset_id: "jatibarang_demo_v1" | "jatibarang_full_v1";
  run_id?: string | null;
  carbon_price_scenario_ids?: string[] | null;
  fiscal_case_ids?: string[] | null;
  supply_scenarios?: SupplyScenario[];
  cost_case?: CostCase;
  selection_fiscal_case_id?: string;
  shortlist_top_k?: number;
  detailed_top_k?: number;
  scenario_limit?: number;
}

/**
 * The full inline request. `geologies`, `seeds`, `candidates`, `sources`,
 * `carbon_prices`, `fiscal_cases`, and `economic_assumptions` mirror large
 * nested Pydantic models; the composer treats them as opaque JSON blocks that
 * originate from a preset/seed design or an imported study, so they are typed
 * loosely here and validated by the backend (422) plus the client mirror.
 */
export interface InlineScreenRequest {
  mode: "inline";
  geologies: Record<string, unknown>;
  seeds: Record<string, unknown>;
  candidates: unknown[];
  sources: CO2Source[];
  operational_grid?: OperationalGrid | null;
  schedules?: unknown[] | null;
  annual_co2_budget_tonnes: number;
  carbon_prices: unknown[];
  fiscal_cases: unknown[];
  economic_assumptions: Record<string, unknown>;
  project_life_years?: number;
  supply_scenarios?: SupplyScenario[];
  cost_case?: CostCase;
  selection_fiscal_case_id?: string;
  shortlist_top_k?: number;
  detailed_top_k?: number;
  scenario_limit?: number;
  terrain_id?: string;
  road_network_id?: string | null;
  routing_basis_id?: string;
  pipeline_basis_id?: string;
  run_id?: string | null;
}

export type ScreenRequest = PresetScreenRequest | InlineScreenRequest;

// ----------------------------------------------------------------------------
// Validation error shape (custom handler in api/app.py)
// ----------------------------------------------------------------------------

export interface ValidationErrorItem {
  type: string;
  loc: (string | number)[];
  msg: string;
  ctx?: Record<string, unknown>;
}

export interface ValidationErrorResponse {
  detail: ValidationErrorItem[] | string;
}
