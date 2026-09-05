"""
"Device tree" menu item: what's physically attached to this machine --
serial ports, USB devices, keyboard/mouse, and displays. Thin on
purpose -- the actual collection logic lives in core.idioms.devicetree,
same pattern as environment.py wrapping core.installer.environment.
"""

from rich.console import Console
from rich.tree import Tree

from core.idioms import devicetree

_LABELS = {
    "serial": "Serial",
    "usb": "USB",
    "input": "Keyboard / mouse",
    "display": "Display",
}


def show(console=None, categories=None):
    console = console or Console()
    found = devicetree.collect(categories)

    tree = Tree("Attached devices")
    any_found = False
    for name, devices in found.items():
        if not devices:
            continue
        any_found = True
        branch = tree.add(f"[bold]{_LABELS.get(name, name)}[/bold]")
        for device in devices:
            label = device["label"]
            if device.get("detail"):
                label += f" [dim]({device['detail']})[/dim]"
            branch.add(label)

    if not any_found:
        console.print("[dim]No devices found in the categories checked.[/dim]")
        return

    console.print(tree)


if __name__ == "__main__":
    show()
