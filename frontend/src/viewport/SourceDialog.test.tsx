import { fireEvent, render, screen } from "@testing-library/react";
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

  it("exposes the backend pressure and purity bounds to browser validation", () => {
    render(
      <SourceDialog
        lat={-6.5}
        lon={108}
        onSave={() => undefined}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByLabelText("Latitude")).toHaveAttribute("min", "-90");
    expect(screen.getByLabelText("Latitude")).toHaveAttribute("max", "90");
    expect(screen.getByLabelText("Longitude")).toHaveAttribute("min", "-180");
    expect(screen.getByLabelText("Longitude")).toHaveAttribute("max", "180");
    expect(screen.getByLabelText("Outlet pressure (bar)")).toHaveAttribute("min", "80");
    expect(screen.getByLabelText("CO₂ purity (fraction)")).toHaveAttribute("min", "0.95");
    expect(screen.getByLabelText("CO₂ purity (fraction)")).toHaveAttribute("max", "1");
  });

  it.each([
    ["outlet pressure", "Outlet pressure (bar)", "79.9"],
    ["CO₂ purity", "CO₂ purity (fraction)", "0.94"],
    ["CO₂ purity above one", "CO₂ purity (fraction)", "1.01"],
  ])("does not submit an invalid %s", async (_case, label, value) => {
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
    const input = screen.getByLabelText(label);
    await user.clear(input);
    await user.type(input, value);

    const submit = screen.getByRole("button", { name: "Add source" });
    const form = submit.closest("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form!);

    expect(onSave).not.toHaveBeenCalled();
  });

  it("lets an existing source be corrected to exact coordinates", async () => {
    const user = userEvent.setup();
    const onSave = vi.fn();
    render(
      <SourceDialog
        initial={{
          id: "S01",
          name: "Subang proxy source",
          lat: -6.57,
          lon: 107.76,
          annual_capacity_t: 500_000,
          outlet_pressure_bar: 120,
          outlet_temperature_c: 27,
          co2_purity: 0.95,
          max_mass_flow_kg_s: 600,
        }}
        lat={0}
        lon={0}
        onSave={onSave}
        onClose={() => undefined}
      />,
    );

    expect(screen.getByLabelText("Latitude")).toHaveValue(-6.57);
    expect(screen.getByLabelText("Longitude")).toHaveValue(107.76);
    await user.clear(screen.getByLabelText("Latitude"));
    await user.type(screen.getByLabelText("Latitude"), "-6.571");
    await user.clear(screen.getByLabelText("Longitude"));
    await user.type(screen.getByLabelText("Longitude"), "107.759");
    await user.click(screen.getByRole("button", { name: "Save changes" }));

    expect(onSave).toHaveBeenCalledWith(
      expect.objectContaining({ lat: -6.571, lon: 107.759 }),
    );
  });

  it.each([
    ["latitude below range", "Latitude", "-90.01"],
    ["latitude above range", "Latitude", "90.01"],
    ["longitude below range", "Longitude", "-180.01"],
    ["longitude above range", "Longitude", "180.01"],
  ])("does not submit a source with %s", async (_case, label, value) => {
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
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
    const form = screen.getByRole("button", { name: "Add source" }).closest("form");
    expect(form).not.toBeNull();
    fireEvent.submit(form!);

    expect(onSave).not.toHaveBeenCalled();
  });

  it.each(["Latitude", "Longitude"])(
    "does not coerce an empty %s to zero",
    async (label) => {
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
      await user.clear(screen.getByLabelText(label));
      const form = screen.getByRole("button", { name: "Add source" }).closest("form");
      expect(form).not.toBeNull();
      fireEvent.submit(form!);

      expect(onSave).not.toHaveBeenCalled();
    },
  );
});
