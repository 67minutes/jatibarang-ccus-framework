# Abstract Numbers

| Key | Value | Units | Source | Method |
|---|---:|---|---|---|
| `geological_realization_count` | 177 | count | boreyes2026 promoted split + final manifest | Count accepted train/validation/test realizations used by the promoted checkpoint. |
| `porosity_min` | 0.17 | fraction | boreyes2026 final manifest | Minimum poro_mean across accepted promoted-split realizations. |
| `porosity_max` | 0.22 | fraction | boreyes2026 final manifest | Maximum poro_mean across accepted promoted-split realizations. |
| `matrix_permeability_min_md` | 10.0 | mD | data/jatibarang/case_study_assumptions.json | Literature-anchored matrix permeability lower bound before fracture multiplier. |
| `matrix_permeability_max_md` | 114.0 | mD | data/jatibarang/case_study_assumptions.json | Literature-anchored matrix permeability upper bound before fracture multiplier. |
| `one_step_pressure_r2` | 0.9999 | R2 | C:\Users\mauli\Documents\boreyes2026\outputs\model_b_hnp_prod_v2_boundary_replay_k3_polish_v1_fold0_metrics.json | Read promoted production_v2 one-step metric and round for abstract reporting. |
| `one_step_gas_plume_iou` | 0.9756 | IoU | C:\Users\mauli\Documents\boreyes2026\outputs\model_b_hnp_prod_v2_boundary_replay_k3_polish_v1_fold0_metrics.json | Read promoted production_v2 one-step gas saturation plume IoU. |
| `cumulative_production_error_pct` | 1.84 | percent | C:\Users\mauli\Documents\boreyes2026\outputs\model_b_hnp_prod_v2_boundary_replay_k3_polish_v1_fold0_metrics.json | Use last-rollout cumulative raw oil relative MAE as the abstract production error bound. |
| `end_sequence_co2_mass_error_pct` | 3.35 | percent | C:\Users\mauli\Documents\boreyes2026\outputs\model_b_hnp_prod_v2_boundary_replay_k3_polish_v1_fold0_metrics.json | Use last-rollout z_co2 mass error from the promoted metrics. |
| `integrated_scenario_count` | 3240 | count | data/jatibarang/case_study_assumptions.json | Candidate count multiplied by operational-grid combinations. |
| `screening_runtime_minutes` | 0.6351 | minutes | Phase 1 screening CLI | Measured wall-clock time for A* route build, CoolProp precompute/facility, Pyomo/CBC MILP, and economics. |
| `equivalent_compositional_coverage_weeks` | 2.38 | weeks | C:\Users\mauli\Documents\boreyes2026\exports_hnp_expressive\final\manifest.json | Scenario count multiplied by mean MRST manifest runtime; Phase 1 runs only curated validation subset. |
| `current_carbon_price_npv_usd` | -8299986.64 | USD | Phase 1 real infrastructure economics model | Final portfolio NPV using A* routes, CoolProp facility costs, Pyomo/CBC well selection, and delivered costs. |
| `jcm_bilateral_price_npv_usd` | -2617155.56 | USD | Phase 1 real infrastructure economics model | Final portfolio NPV using A* routes, CoolProp facility costs, Pyomo/CBC well selection, and delivered costs. |
| `changed_priority_candidate_count` | 18 | count | Phase 1 MILP/economics ranking comparison | Count candidates whose integrated MILP/economics ranking shifts by at least the configured rank-delta threshold. |
| `total_candidate_count` | 20 | count | data/jatibarang/case_study_assumptions.json | Candidate well count in the Phase 1 case-study assumptions. |
| `break_even_carbon_price_usd_per_tonne` | 54.52 | USD/tonne CO2 | Phase 1 real infrastructure economics model | Carbon price required to bring the current-price Pyomo/CBC-selected portfolio to zero NPV before carbon revenue. |

## Filled Excerpt

Applied to a Jatibarang-anchored case study with 177 geological realizations spanning porosity 0.17 to 0.22 and matrix permeability 10.0 to 114.0 mD, the surrogate achieves one-step pressure R2 of 0.9999, gas plume IoU of 0.9756, and cumulative production error below 1.84%, with end-of-sequence CO2 mass error of 3.35%. The framework screens 3240 integrated scenarios in 0.6351 minutes versus 2.38 weeks for equivalent compositional coverage. Under current carbon pricing the optimal plan yields NPV of $-8.30 million; under JCM bilateral pricing NPV rises to $-2.62 million and well selection shifts, with 18 of 20 candidates changing priority. The break-even carbon price is $54.52 per tonne. These results demonstrate that surrogate-enabled integrated screening materially improves CO2 HnP-CCUS planning and that Indonesian carbon pricing, even at nascent levels, alters which development strategies are optimal.
