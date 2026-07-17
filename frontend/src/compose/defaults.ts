import type {
  CarbonPriceScenario,
  InlineScreenRequest,
  OperationalGrid,
} from "../api/types";

export type StudyRequestBase = Pick<
  InlineScreenRequest,
  | "carbon_prices"
  | "fiscal_cases"
  | "economic_assumptions"
  | "annual_co2_budget_tonnes"
  | "operational_grid"
  | "cost_case"
  | "supply_scenarios"
  | "project_life_years"
  | "selection_fiscal_case_id"
  | "shortlist_top_k"
  | "detailed_top_k"
>;

/**
 * API-ready materialization of economic_basis.json::carbon_price_scenarios.
 * Provenance is shaped exactly like carbon_prices_from_basis in the backend.
 */
export const DEFAULT_CARBON_PRICES: CarbonPriceScenario[] = [
  {
    scenario_id: "current_idx",
    carbon_price_usd_per_tonne: 4.027689327945084,
    source_type: "market_observation",
    provenance: [
      {
        source_class: "market_observation",
        source_id: "carbon-price-current_idx",
        url: "https://idxcarbon.co.id/id/data-monthly",
        notes:
          "IDXCarbon June 2026 all-market value 47722800 IDR / volume 656 tCO2e",
        metadata: {
          native_price_idr_per_tonne: 72748.17073170732,
          native_calculation:
            "IDXCarbon June 2026 all-market value 47722800 IDR / volume 656 tCO2e",
          market_observation_month: "2026-06",
          usd_idr: 18064.0,
          fx_observation_date: "2026-07-15",
          fx_source_url:
            "https://www.bi.go.id/en/statistik/informasi-kurs/jisdor/Default.aspx",
          international_context_url:
            "https://ojk.go.id/en/berita-dan-kegiatan/siaran-pers/Documents/Pages/Inauguration-of-Indonesia-International-Carbon-Trading/12%20%5BJoint%20Press%20Release%5D%20Peresmian%20Perdagangan%20Karbon%20Luar%20Negeri_EN.pdf",
        },
      },
    ],
  },
  {
    scenario_id: "domestic_maturing",
    carbon_price_usd_per_tonne: 20.0,
    source_type: "economic_assumption",
    provenance: [
      {
        source_class: "economic_assumption",
        source_id: "carbon-price-domestic_maturing",
        url: "",
        notes: "Domestic-market sensitivity, not an observed price.",
        metadata: {},
      },
    ],
  },
  {
    scenario_id: "article6_jcm",
    carbon_price_usd_per_tonne: 40.0,
    source_type: "economic_assumption",
    provenance: [
      {
        source_class: "economic_assumption",
        source_id: "carbon-price-article6_jcm",
        url: "",
        notes:
          "Article-6/JCM bilateral sensitivity, not an observed transaction price.",
        metadata: {},
      },
    ],
  },
  {
    scenario_id: "aspirational",
    carbon_price_usd_per_tonne: 50.0,
    source_type: "economic_assumption",
    provenance: [
      {
        source_class: "economic_assumption",
        source_id: "carbon-price-aspirational",
        url: "",
        notes: "Aspirational policy sensitivity, not an observed price.",
        metadata: {},
      },
    ],
  },
];

const REGULATORY_SOURCES = [
  {
    title: "MEMR Regulation 2/2023 on CCS and CCUS",
    url: "https://jdih.esdm.go.id/storage/document/Permen%20ESDM%20Nomor%202%20Tahun%202023.pdf",
  },
  {
    title: "MEMR Regulation 13/2024 on Gross Split PSC",
    url: "https://jdih.esdm.go.id/dokumen/view?id=2476",
  },
  {
    title: "DJP 2026 tax-status note",
    url: "https://www.pajak.go.id/id/artikel/tak-ada-kenaikan-dan-pungutan-pajak-baru-pada-2026",
  },
];

const RECOVERABLE_COST_CATEGORIES = [
  "supply",
  "facility_capex",
  "facility_opex",
  "pipeline_capex",
  "pipeline_opex",
  "lifting",
  "workover",
  "mrv",
];

const FISCAL_PROVENANCE = [
  {
    source_class: "regulatory_source",
    source_id: "parametric-fiscal-screening",
    url: "",
    notes: "Screening sensitivity only; not an exact PSC replica.",
    metadata: { sources: REGULATORY_SOURCES },
  },
];

/** API-ready materialization of economic_basis.json::fiscal_cases. */
export const DEFAULT_FISCAL_CASES: unknown[] = [
  {
    case_id: "pre_tax",
    mode: "pre_tax",
    government_take_fraction: 0.0,
    cost_recovery_ceiling_fraction: 0.0,
    recoverable_cost_categories: RECOVERABLE_COST_CATEGORIES,
    carbon_revenue_tax_fraction: 0.0,
    carbon_tax_enabled: false,
    carbon_tax_usd_per_tonne: 0.0,
    provenance: FISCAL_PROVENANCE,
  },
  {
    case_id: "cost_recovery_screening",
    mode: "cost_recovery",
    government_take_fraction: 0.4,
    cost_recovery_ceiling_fraction: 0.8,
    recoverable_cost_categories: RECOVERABLE_COST_CATEGORIES,
    carbon_revenue_tax_fraction: 0.0,
    carbon_tax_enabled: false,
    carbon_tax_usd_per_tonne: 0.0,
    provenance: FISCAL_PROVENANCE,
  },
  {
    case_id: "gross_split_screening",
    mode: "gross_split",
    government_take_fraction: 0.43,
    cost_recovery_ceiling_fraction: 0.0,
    recoverable_cost_categories: RECOVERABLE_COST_CATEGORIES,
    carbon_revenue_tax_fraction: 0.0,
    carbon_tax_enabled: false,
    carbon_tax_usd_per_tonne: 0.0,
    provenance: FISCAL_PROVENANCE,
  },
];

/** Mirrors assumptions_from_basis(data/jatibarang/economic_basis.json). */
export const DEFAULT_ECONOMIC_ASSUMPTIONS: Record<string, unknown> = {
  version: "1.0.0",
  currency_basis: "constant_2025_usd",
  discount_rate: 0.1,
  oil_price_usd_per_bbl: 73.0,
  gas_price_usd_per_mmbtu: 6.0,
  gas_heating_value_mmbtu_per_std_m3: 0.0353,
  lifting_cost_usd_per_bbl: 18.0,
  workover_cost_usd_per_cycle: 50000.0,
  mrv_cost_usd_per_tonne: 1.0,
  certification_haircut: 0.85,
  storage_divergence_threshold_fraction_of_injected: 0.15,
  usd_reconciliation_tolerance: 0.01,
  mass_reconciliation_tolerance_tonnes: 0.000001,
  irr_min: -0.99,
  irr_max: 10.0,
  carbon_price_max_usd_per_tonne: 1000.0,
  oil_price_max_usd_per_bbl: 500.0,
  root_iterations: 80,
};

/** The 3 x 3 x 3 x 3 x 2 Feature 005 launch-pad design (162 schedules). */
export const DEFAULT_OPERATIONAL_GRID: OperationalGrid = {
  injection_rate_m3_day: [8000.0, 9000.0, 10000.0],
  injection_duration_days: [45.0],
  soak_duration_days: [25.0, 30.0, 35.0],
  production_duration_days: [170.0, 190.0, 210.0],
  production_bhp_psi: [650.0, 675.0, 700.0],
  cycles: [3, 4],
};

/**
 * Generic editable screening defaults. Budget and project life come from
 * case_study_assumptions.json; the remaining options mirror CommonScreenOptions.
 */
export const DEFAULT_STUDY_REQUEST_BASE: StudyRequestBase = {
  carbon_prices: DEFAULT_CARBON_PRICES,
  fiscal_cases: DEFAULT_FISCAL_CASES,
  economic_assumptions: DEFAULT_ECONOMIC_ASSUMPTIONS,
  annual_co2_budget_tonnes: 320000.0,
  operational_grid: DEFAULT_OPERATIONAL_GRID,
  cost_case: "base",
  supply_scenarios: ["optimized_pipeline", "trucking_counterfactual"],
  project_life_years: 8,
  selection_fiscal_case_id: "pre_tax",
  shortlist_top_k: 5,
  detailed_top_k: 5,
};

/** Return an editable copy so composer mutations never alter module defaults. */
export function createDefaultStudyRequestBase(): StudyRequestBase {
  return structuredClone(DEFAULT_STUDY_REQUEST_BASE);
}
