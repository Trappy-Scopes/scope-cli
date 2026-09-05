"""
"Device tree" menu item: what's physically attached to this machine --
serial ports, USB devices, keyboard/mouse, and displays. Thin on
purpose -- the actual collection logic lives in core.idioms.devicetree,
same pattern as environment.py wrapping core.installer.environment.

The tree's root line is the machine's own state, not a generic label --
reads core.idioms.platform's os/board facts (the same facts
core.installer.environment feeds into hardware-profile selection) so
whoever's looking at this tree knows what OS/board it was collected on
without cross-referencing anything else.
"""

from rich.console import Console
from rich.tree import Tree

from core.idioms import devicetree
from core.idioms import platform as platform_facts

_LABELS = {
    "serial": "Serial",
    "usb": "USB",
    "input": "Keyboard / mouse",
    "display": "Display",
}

_COLORS = {
    "serial": "cyan",
    "usb": "magenta",
    "input": "yellow",
    "display": "blue",
}


def _system_state():
    facts = platform_facts.collect("os", "board")
    os_facts = facts.get("os")
    if not isinstance(os_facts, dict):
        os_facts = {}
    system = os_facts.get("system", "unknown")
    release = os_facts.get("release", "")
    machine = os_facts.get("machine", "")
    board = facts.get("board", "unknown")
    if isinstance(board, dict):
        board = "unknown"
    return f"{system} {release} ({machine}) · board: {board}"


def show(console=None, categories=None):
    console = console or Console()
    found = devicetree.collect(categories)

    tree = Tree(f"[bold]•[/bold] Note: {_system_state()}")
    any_found = False
    for name, devices in found.items():
        if not devices:
            continue
        any_found = True
        color = _COLORS.get(name, "white")
        branch = tree.add(f"[bold {color}]{_LABELS.get(name, name)}[/bold {color}]")
        for device in devices:
            label = f"[{color}]{device['label']}[/{color}]"
            if device.get("detail"):
                label += f" [dim]({device['detail']})[/dim]"
            branch.add(label)

    console.print(tree)
    if not any_found:
        console.print("[dim]No devices found in the categories checked.[/dim]")


if __name__ == "__main__":
    show()
