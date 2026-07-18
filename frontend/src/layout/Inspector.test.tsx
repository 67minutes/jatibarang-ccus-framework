import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { CarbonPricePlan, InterferencePair } from "../api/types";
import {
  TruckingDistanceProvenance,
  WellInterferenceWarnings,
} from "./Inspector";

function planWithPairs(flaggedPairs: InterferencePair[]): CarbonPricePlan {
  return {
    interference: {
      well_ids: ["W01", "W02", "W03"],
      matrix: [],
      flagged_pairs: flaggedPairs,
    },
  } as unknown as CarbonPricePlan;
}

describe("WellInterferenceWarnings", () => {
  it("renders backend-confirmed overlap evidence and humanized recommendations", () => {
    render(
      <WellInterferenceWarnings
        wellId="W01"
        plan={planWithPairs([
          {
            first_well_id: "W01",
            second_well_id: "W02",
            distance_m: 742,
            radius_sum_m: 1_350,
            overlap: true,
            recommendations: ["increase_spacing", "validate_with_full_simulation"],
          },
        ])}
      />,
    );

    expect(screen.getByText("interference overlap")).toBeInTheDocument();
    expect(screen.getByLabelText("Interference warnings")).toHaveTextContent(
      "W02: 742 m spacing vs 1,350 m combined influence radius",
    );
    expect(screen.getByText("increase spacing")).toBeInTheDocument();
    expect(screen.getByText("validate with full simulation")).toBeInTheDocument();
  });

  it("does not infer warnings for non-overlap pairs or pairs outside the inspected well", () => {
    const { container } = render(
      <WellInterferenceWarnings
        wellId="W01"
        plan={planWithPairs([
          {
            first_well_id: "W01",
            second_well_id: "W02",
            distance_m: 500,
            radius_sum_m: 1_000,
            overlap: false,
            recommendations: ["increase_spacing"],
          },
          {
            first_well_id: "W02",
            second_well_id: "W03",
            distance_m: 400,
            radius_sum_m: 900,
            overlap: true,
            recommendations: ["stagger_timing"],
          },
        ])}
      />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});

describe("TruckingDistanceProvenance", () => {
  it("explains great-circle estimates and prompts for a road import", () => {
    render(
      <TruckingDistanceProvenance provenance="greatcircle_detour_estimate" />,
    );

    expect(
      screen.getByText(
        "Estimated from great-circle distance × 1.4 — import a road network for road-accurate routing.",
      ),
    ).toBeInTheDocument();
  });

  it("identifies routes computed over an imported road graph", () => {
    render(
      <TruckingDistanceProvenance provenance="osm_road_network:roads-abc123" />,
    );

    expect(
      screen.getByText("Routed over the imported road network."),
    ).toBeInTheDocument();
  });

  it("stays hidden for unrelated provenance", () => {
    const { container } = render(
      <TruckingDistanceProvenance provenance="declared_distance" />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});
