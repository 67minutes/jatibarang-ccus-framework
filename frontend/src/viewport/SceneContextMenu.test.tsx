import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { SceneContextMenu, type SceneContextTarget } from "./SceneContextMenu";

function handlers() {
  return {
    onAddSource: vi.fn(),
    onAddWell: vi.fn(),
    onRenameWell: vi.fn(),
    onRemoveWell: vi.fn(),
    onEditSource: vi.fn(),
    onRemoveSource: vi.fn(),
    onEnterField: vi.fn(),
    onClose: vi.fn(),
  };
}

function target(kind: SceneContextTarget["kind"]): SceneContextTarget {
  return { x: 20, y: 20, kind, targetId: "object-1", lat: -6.5, lon: 108 };
}

describe("SceneContextMenu", () => {
  it("runs terrain placement actions and closes", async () => {
    const user = userEvent.setup();
    const actions = handlers();
    render(
      <SceneContextMenu
        target={target("terrain")}
        canAddCandidateWell
        canRemoveWell={false}
        {...actions}
      />,
    );

    await user.click(screen.getByRole("menuitem", { name: /add co₂ source/i }));
    expect(actions.onAddSource).toHaveBeenCalledOnce();
    expect(actions.onClose).toHaveBeenCalledOnce();
  });

  it("allows native-well rename but does not offer removal", async () => {
    const user = userEvent.setup();
    const actions = handlers();
    render(
      <SceneContextMenu
        target={target("well")}
        canAddCandidateWell={false}
        canRemoveWell={false}
        wellName="W01"
        {...actions}
      />,
    );

    expect(screen.queryByRole("menuitem", { name: /remove well/i })).toBeNull();
    await user.click(screen.getByRole("menuitem", { name: /rename well/i }));
    const input = screen.getByLabelText("Well name");
    await user.clear(input);
    await user.type(input, "Native producer");
    await user.click(screen.getByRole("button", { name: "Save" }));
    expect(actions.onRenameWell).toHaveBeenCalledWith("Native producer");
  });

  it("offers edit and remove for sources", () => {
    const actions = handlers();
    render(
      <SceneContextMenu
        target={target("source")}
        canAddCandidateWell={false}
        canRemoveWell={false}
        {...actions}
      />,
    );

    expect(screen.getByRole("menuitem", { name: /edit source/i })).toBeVisible();
    expect(screen.getByRole("menuitem", { name: /remove source/i })).toBeVisible();
  });
});
