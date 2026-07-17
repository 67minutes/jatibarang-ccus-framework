import { describe, expect, it } from "vitest";
import { useWorkspaceStore } from "./workspace.store";

describe("workspace influence layer", () => {
  it("is visible by default and toggles independently", () => {
    const before = useWorkspaceStore.getState().layers;
    expect(before.influence).toBe(true);

    useWorkspaceStore.getState().toggleLayer("influence");
    expect(useWorkspaceStore.getState().layers).toEqual({
      ...before,
      influence: false,
    });

    useWorkspaceStore.getState().toggleLayer("influence");
    expect(useWorkspaceStore.getState().layers.influence).toBe(true);
  });
});
