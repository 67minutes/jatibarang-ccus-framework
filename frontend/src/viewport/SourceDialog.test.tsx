import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SourceDialog } from "./SourceDialog";

describe("SourceDialog", () => {
  it("submits required values with the declared screening defaults", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <SourceDialog
        lat={-6.5}
        lon={108}
        onSave={onSave}
        onClose={() => undefined}
      />,
    );

    await user.type(screen.getByLabelText("Source name"), "Capture plant");
    await user.type(screen.getByLabelText("Annual capacity (t/y)"), "500000");
    await user.click(screen.getByRole("button", { name: "Add source" }));

    expect(onSave).toHaveBeenCalledWith({
      name: "Capture plant",
      lat: -6.5,
      lon: 108,
      annual_capacity_t: 500000,
      outlet_pressure_bar: 120,
      outlet_temperature_c: 27,
      co2_purity: 0.95,
      max_mass_flow_kg_s: 600,
    });
  });
});
