import { describe, expect, it } from "vitest";
import type {
  CarbonPricePlan,
  Coordinate,
  ScreenResult,
} from "../api/types";
import type { PlacedWell } from "../state/field.store";
import {
  influenceEntries,
  projectInfluenceEntry,
  type InfluenceEntry,
} from "./InfluenceZones";
import type { TerrainProjector } from "./terrain";

function strategy(candidateId: string, radius: number) {
  return {
    candidate_id: candidateId,
    prediction: { plume: { influence_radius_m: radius } },
  };
}

function fixturePlan(): CarbonPricePlan {
  return {
    carbon_price_scenario_id: "price-40",
    selected_wells: ["W02", "W01", "W01"],
    well_strategies: [strategy("W01", 420), strategy("W02", 260)],
    interference: {
      flagged_pairs: [
        {
          first_well_id: "W01",
          second_well_id: "W03",
          overlap: true,
        },
        {
          first_well_id: "W02",
          second_well_id: "W03",
          overlap: false,
        },
      ],
    },
  } as CarbonPricePlan;
}

const wells: PlacedWell[] = [
  { id: "W01", name: "Alpha", kind: "placed", lat: -6.53, lon: 108.39 },
  { id: "W02", name: "Bravo", kind: "placed", lat: -6.54, lon: 108.4 },
  { id: "W03", name: "Charlie", kind: "placed", lat: -6.55, lon: 108.41 },
];

describe("influenceEntries", () => {
  it("uses selected-well plume radii and only true overlap pairs for flags", () => {
    const plan = fixturePlan();
    const result = { plans: [plan] } as ScreenResult;

    expect(influenceEntries(result, plan, wells)).toEqual([
      {
        candidate_id: "W01",
        lat: -6.53,
        lon: 108.39,
        radius_m: 420,
        flagged: true,
      },
      {
        candidate_id: "W02",
        lat: -6.54,
        lon: 108.4,
        radius_m: 260,
        flagged: false,
      },
    ]);
  });

  it("omits detached plans and missing or invalid runtime values", () => {
    const plan = fixturePlan();
    const detached = {
      ...plan,
      carbon_price_scenario_id: "detached",
    } as CarbonPricePlan;
    expect(influenceEntries({ plans: [plan] } as ScreenResult, detached, wells)).toEqual([]);

    const invalidPlan = {
      ...plan,
      selected_wells: ["W01", "W02", "W04"],
      well_strategies: [strategy("W01", Number.NaN), strategy("W02", -1)],
    } as CarbonPricePlan;
    const result = { plans: [invalidPlan] } as ScreenResult;
    const invalidWells = [
      ...wells,
      { id: "W04", name: "Invalid", kind: "placed", lat: 120, lon: 108.4 },
    ] as PlacedWell[];
    expect(influenceEntries(result, invalidPlan, invalidWells)).toEqual([]);
  });
});

describe("projectInfluenceEntry", () => {
  it("projects east and north metric offsets independently", () => {
    const projector = {
      toXZ: ({ latitude, longitude }: Coordinate) => [
        longitude * 2,
        -latitude * 3,
      ],
      elevationAt: () => 100,
      heightOf: (elevation: number, exaggeration: number) =>
        (elevation / 50) * exaggeration,
      metresPerSceneUnit: 50,
      data: {},
    } as unknown as TerrainProjector;
    const entry: InfluenceEntry = {
      candidate_id: "W01",
      lat: 0,
      lon: 0,
      radius_m: 111_320,
      flagged: false,
    };

    const projected = projectInfluenceEntry(projector, entry, 2);
    expect(projected).toMatchObject({
      x: 0,
      y: 4,
      radius_x: 2,
      radius_z: 3,
    });
    expect(projected?.z).toBeCloseTo(0);
  });

  it("omits invalid metric radii", () => {
    const projector = {
      toXZ: () => [0, 0],
      elevationAt: () => 0,
      heightOf: () => 0,
    } as unknown as TerrainProjector;
    expect(
      projectInfluenceEntry(projector, {
        candidate_id: "bad",
        lat: 0,
        lon: 0,
        radius_m: Number.NaN,
        flagged: false,
      }),
    ).toBeNull();
  });
});
