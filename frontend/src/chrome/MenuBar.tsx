import * as Menubar from "@radix-ui/react-menubar";
import {
  getCommand,
  isCommandEnabled,
  type Menu,
  type MenuNode,
  menus,
  runCommand,
} from "./commands";
import "./chrome.css";

/**
 * The menu bar: the complete command inventory (design §3 clause 1). Rendered
 * entirely from the command registry, so it is provably complete.
 */
export function MenuBar() {
  return (
    <Menubar.Root className="menubar">
      {menus.map((menu) => (
        <MenuRoot key={menu.label} menu={menu} />
      ))}
    </Menubar.Root>
  );
}

function MenuRoot({ menu }: { menu: Menu }) {
  return (
    <Menubar.Menu>
      <Menubar.Trigger className="menubar-trigger">{menu.label}</Menubar.Trigger>
      <Menubar.Portal>
        <Menubar.Content className="menu-content" align="start" sideOffset={2}>
          {menu.items.map((node, i) => (
            <MenuItem key={i} node={node} />
          ))}
        </Menubar.Content>
      </Menubar.Portal>
    </Menubar.Menu>
  );
}

function MenuItem({ node }: { node: MenuNode }) {
  if (node.kind === "separator") {
    return <Menubar.Separator className="menu-separator" />;
  }
  if (node.kind === "submenu") {
    return (
      <Menubar.Sub>
        <Menubar.SubTrigger className="menu-item menu-subtrigger">
          {node.label}
          <span className="menu-caret">▸</span>
        </Menubar.SubTrigger>
        <Menubar.Portal>
          <Menubar.SubContent className="menu-content" sideOffset={2} alignOffset={-4}>
            {node.items.map((child, i) => (
              <MenuItem key={i} node={child} />
            ))}
          </Menubar.SubContent>
        </Menubar.Portal>
      </Menubar.Sub>
    );
  }
  const command = getCommand(node.commandId);
  if (!command) return null;
  return (
    <Menubar.Item
      className="menu-item"
      disabled={!isCommandEnabled(command.id)}
      onSelect={() => runCommand(command.id)}
    >
      <span className="menu-label">{command.label}</span>
      {command.shortcut && <span className="menu-shortcut">{command.shortcut}</span>}
    </Menubar.Item>
  );
}
