import { describe, expect, it } from "vitest";
import type { CarbonPricePlan, InlineScreenRequest } from "../api/types";
import { collectSceneObjects, nodeCoordinateMap, projectToView } from "./scene";

function request(): InlineScreenRequest {
  return {
    mode: "inline",
    geologies: {},
    seeds: {},
    candidates: [
      { candidate_id: "W01", location: { latitude: -6.48, longitude: 108.31 } },
      { candidate_id: "W02", location: { latitude: -6.49, longitude: 108.33 } },
    ],
    sources: [
      {
        id: "SRC",
        name: "s",
        location: { latitude: -6.5, longitude: 108.32 },
        capacity_tonnes_per_year: 1,
        max_mass_flow_kg_s: 1,
        outlet_pressure_bar: 120,
        outlet_temperature_c: 27,
        co2_purity: 0.95,
      },
    ],
    annual_co2_budget_tonnes: 1,
    carbon_prices: [],
    fiscal_cases: [],
    economic_assumptions: {},
  };
}

const noNetworkPlan = {
  carbon_price_scenario_id: "cp",
  carbon_price_usd_per_tonne: 20,
  selected_wells: [],
  pipeline: { domain_status: "no_viable_network", built_segments: [], boosters: [] },
  trucking_counterfactual: null,
} as unknown as CarbonPricePlan;

describe("scene", () => {
  it("maps sources and candidate wells to coordinates", () => {
    const coords = nodeCoordinateMap(request());
    expect(coords.get("SRC")).toBeDefined();
    expect(coords.get("W01")).toBeDefined();
    expect(coords.size).toBe(3);
  });

  it("draws trucking supply lines to all wells when no pipeline is viable", () => {
    const scene = collectSceneObjects(request(), noNetworkPlan);
    expect(scene.nodes).toHaveLength(3);
    expect(scene.routes.every((r) => r.mode === "trucking")).toBe(true);
    expect(scene.routes).toHaveLength(2); // SRC -> each well
  });

  it("uses a routed trucking leg when the result carries one", () => {
    const routedPlan = {
      ...noNetworkPlan,
      selected_wells: ["W02"],
      trucking_counterfactual: {
        supply: {
          legs: [
            {
              candidate_id: "W02",
              distance_km: 30,
              annual_mass_tonnes: 100_000,
              route: [
                [-6.5, 108.32],
                [-6.47, 108.34],
                [-6.49, 108.33],
              ],
            },
          ],
        },
      },
    } as unknown as CarbonPricePlan;

    const scene = collectSceneObjects(request(), routedPlan);

    expect(scene.routes).toHaveLength(1);
    expect(scene.routes[0].path).toEqual([
      { latitude: -6.5, longitude: 108.32 },
      { latitude: -6.47, longitude: 108.34 },
      { latitude: -6.49, longitude: 108.33 },
    ]);
  });

  it("draws a dashed trucking route for a trucked well on an accepted plan", () => {
    const acceptedTruckedPlan = {
      carbon_price_scenario_id: "cp",
      carbon_price_usd_per_tonne: 20,
      domain_status: "accepted",
      selected_wells: ["W02"],
      logistics_mode: "trucking",
      pipeline: {
        domain_status: "accepted",
        selected_wells: ["W02"],
        supply_mode_by_well: { W02: "trucking" },
        built_segments: [],
        boosters: [],
      },
      trucking_counterfactual: null,
      trucking_route_preview: {
        distance_provenance: "osm_road_network:roads-test",
        legs: [
          {
            candidate_id: "W02",
            distance_km: 78,
            annual_mass_tonnes: 1516,
            route: [
              [-6.5, 107.0],
              [-6.4, 107.1],
              [-6.5, 107.2],
            ],
          },
        ],
      },
    } as unknown as CarbonPricePlan;

    const scene = collectSceneObjects(request(), acceptedTruckedPlan);

    expect(scene.routes).toHaveLength(1);
    expect(scene.routes[0].mode).toBe("trucking");
    expect(scene.routes[0].path).toEqual([
      { latitude: -6.5, longitude: 107.0 },
      { latitude: -6.4, longitude: 107.1 },
      { latitude: -6.5, longitude: 107.2 },
    ]);
  });

  it("uses road-routed preview legs without inventing a selected portfolio", () => {
    const previewPlan = {
      ...noNetworkPlan,
      trucking_route_preview: {
        distance_provenance: "osm_road_network:roads-test",
        legs: [
          {
            candidate_id: "W01",
            distance_km: 24,
            annual_mass_tonnes: 50_000,
            route: [
              [-6.5, 108.32],
              [-6.51, 108.3],
              [-6.48, 108.31],
            ],
          },
          {
            candidate_id: "W02",
            distance_km: 30,
            annual_mass_tonnes: 50_000,
            route: [
              [-6.5, 108.32],
              [-6.52, 108.34],
              [-6.49, 108.33],
            ],
          },
        ],
      },
    } as unknown as CarbonPricePlan;

    const scene = collectSceneObjects(request(), previewPlan);

    expect(scene.routes).toHaveLength(2);
    expect(scene.routes[0].path).toHaveLength(3);
    expect(scene.routes[1].path).toHaveLength(3);
    expect(previewPlan.selected_wells).toEqual([]);
    expect(previewPlan.trucking_counterfactual).toBeNull();
  });

  it("projects to a view box with equal-aspect scaling and north-up", () => {
    const scene = collectSceneObjects(request(), noNetworkPlan);
    const view = projectToView(scene, 800, 600, 20);
    for (const n of view.nodes) {
      expect(n.x).toBeGreaterThanOrEqual(0);
      expect(n.x).toBeLessThanOrEqual(800);
      expect(n.y).toBeGreaterThanOrEqual(0);
      expect(n.y).toBeLessThanOrEqual(600);
    }
    // The southernmost source has the largest y (north is up).
    const src = view.nodes.find((n) => n.id === "SRC")!;
    const w01 = view.nodes.find((n) => n.id === "W01")!;
    expect(src.y).toBeGreaterThan(w01.y);
  });
});
