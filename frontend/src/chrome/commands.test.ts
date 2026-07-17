import { beforeEach, describe, expect, it } from "vitest";
import {
  commands,
  isCommandEnabled,
  menus,
  toolbarCommandIds,
  type MenuNode,
} from "./commands";
import { useLedgerStore } from "../state/ledger.store";
import { useSelectionStore } from "../state/selection.store";

function commandIds(nodes: MenuNode[]): string[] {
  return nodes.flatMap((node) => {
    if (node.kind === "command") return [node.commandId];
    if (node.kind === "submenu") return commandIds(node.items);
    return [];
  });
}

describe("command inventory", () => {
  beforeEach(() => {
    useLedgerStore.setState({ entries: [], activeEntryId: null, compareIds: [null, null] });
    useSelectionStore.getState().clear();
  });

  it("places every command in exactly one menu and keeps the toolbar a subset", () => {
    const menuIds = menus.flatMap((menu) => commandIds(menu.items));
    expect(menuIds).toHaveLength(commands.length);
    expect(new Set(menuIds)).toEqual(new Set(commands.map((command) => command.id)));
    expect(toolbarCommandIds.every((id) => menuIds.includes(id))).toBe(true);
  });

  it("disables every scientific field command without a matching detailed case", () => {
    const fieldCommands = commands
      .map((command) => command.id)
      .filter((id) => id.startsWith("view.colorBy.") || id.startsWith("view.heightBy."));
    expect(fieldCommands).toHaveLength(8);
    expect(fieldCommands.every((id) => !isCommandEnabled(id))).toBe(true);
  });
});
