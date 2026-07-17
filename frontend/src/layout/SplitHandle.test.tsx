import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useSplitPaneStore } from "../state/splitPane.store";
import { SplitHandle } from "./SplitHandle";

describe("SplitHandle", () => {
  beforeEach(() => useSplitPaneStore.getState().resetAll());

  it("supports arrow, large-step, limit, and reset keyboard behavior", () => {
    render(
      <SplitHandle panel="left" controls="left-panel" collapsed={false} onToggle={vi.fn()} />,
    );
    const separator = screen.getByRole("separator", { name: /resize study objects/i });

    fireEvent.keyDown(separator, { key: "ArrowRight" });
    expect(useSplitPaneStore.getState().sizes.left).toBe(256);
    fireEvent.keyDown(separator, { key: "ArrowRight", shiftKey: true });
    expect(useSplitPaneStore.getState().sizes.left).toBe(288);
    fireEvent.keyDown(separator, { key: "End" });
    expect(useSplitPaneStore.getState().sizes.left).toBe(420);
    fireEvent.doubleClick(separator);
    expect(useSplitPaneStore.getState().sizes.left).toBe(248);
  });

  it("uses upward growth and a dynamic 70 percent maximum for the bottom panel", () => {
    render(
      <SplitHandle
        panel="bottom"
        controls="bottom-panel"
        collapsed={false}
        onToggle={vi.fn()}
        availableSize={() => 600}
      />,
    );
    const separator = screen.getByRole("separator", { name: /resize dashboard/i });
    fireEvent.keyDown(separator, { key: "End" });
    expect(useSplitPaneStore.getState().sizes.bottom).toBe(420);
    fireEvent.keyDown(separator, { key: "ArrowDown" });
    expect(useSplitPaneStore.getState().sizes.bottom).toBe(412);
  });

  it("keeps restore accessible while disabling a collapsed divider", () => {
    const onToggle = vi.fn();
    render(
      <SplitHandle panel="right" controls="right-panel" collapsed onToggle={onToggle} />,
    );
    const separator = screen.getByRole("separator", { name: /resize inspector/i });
    expect(separator).toHaveAttribute("aria-disabled", "true");
    expect(separator).toHaveAttribute("tabindex", "-1");
    fireEvent.click(screen.getByRole("button", { name: /restore inspector/i }));
    expect(onToggle).toHaveBeenCalledOnce();
  });
});

