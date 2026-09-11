"""
"Device tree" menu item: what's physically attached to this machine --
serial ports, USB devices, keyboard/mouse, displays, and storage. Thin on
purpose -- the actual collection logic lives in core.idioms.devicetree,
same pattern as environment.py wrapping core.installer.environment.

The tree's root line is the machine's own state, not a generic label --
reads core.idioms.platform's os/board/cpu/memory facts (the same os/board
facts core.installer.environment feeds into hardware-profile selection)
so whoever's looking at this tree knows what machine it was collected on
without cross-referencing anything else. Storage is deliberately NOT
folded into this one-line summary -- a machine can have more than one
disk attached, so it gets its own tree branch below instead, same as
serial/usb/input/display.

The storage branch cross-references config.Experiment.exp_dir (read the
same way tui.py's _venv_line() reads config.venv -- straight from the
raw YAML, not via TrappyConfig(), which has side effects not wanted on a
menu redraw): whichever mounted disk that directory actually lives on is
marked, since "how much room is left where my experiment data lands" is
the answer this is actually for. Every other mounted disk still shows,
unmarked -- so plugging in a new SSD to store data on shows up here too,
matching every other category's "what's attached" contract.
"""

import os

from rich.console import Console
from rich.tree import Tree

from core.idioms import devicetree
from core.idioms import platform as platform_facts

_LABELS = {
    "serial": "Serial",
    "usb": "USB",
    "input": "Keyboard / mouse",
    "display": "Display",
    "storage": "Storage",
}

_COLORS = {
    "serial": "cyan",
    "usb": "magenta",
    "input": "yellow",
    "display": "blue",
    "storage": "green",
}

_DEFAULT_EXP_DIR = "~/experiments"


def _gb(num_bytes):
    return num_bytes / (1024 ** 3)


def _system_state():
    facts = platform_facts.collect("os", "board", "cpu", "memory")

    os_facts = facts.get("os")
    if not isinstance(os_facts, dict):
        os_facts = {}
    system = os_facts.get("system", "unknown")
    release = os_facts.get("release", "")
    machine = os_facts.get("machine", "")

    board = facts.get("board", "unknown")
    if isinstance(board, dict):
        board = "unknown"

    cpu = facts.get("cpu")
    cores = cpu.get("logical", "?") if isinstance(cpu, dict) else "?"

    memory = facts.get("memory")
    ram = f"{_gb(memory['total']):.1f} GB RAM" if isinstance(memory, dict) else "RAM: unknown"

    return f"{system} {release} ({machine}) · board: {board} · {cores} cores · {ram}"


def _experiment_dir():
    """config.Experiment.exp_dir, read straight from the raw config file --
    or _DEFAULT_EXP_DIR if there is no config file yet, or it doesn't set one."""
    from core.permaconfig.config import TrappyConfig

    for candidate in TrappyConfig.default_paths:
        if not os.path.exists(candidate):
            continue
        try:
            import yaml
            with open(candidate) as f:
                config = yaml.safe_load(f) or {}
            exp_dir = (config.get("Experiment") or {}).get("exp_dir")
        except Exception:
            exp_dir = None
        break
    else:
        exp_dir = None

    return os.path.realpath(os.path.expanduser(exp_dir or _DEFAULT_EXP_DIR))


def _mount_for_path(path, mountpoints):
    """Which of `mountpoints` `path` actually lives on -- the longest one
    that's a prefix of it, the same logic `df` uses, without needing to
    shell out to `df` or run as root."""
    candidates = [m for m in mountpoints
                  if path == m or path.startswith(m.rstrip("/") + "/")]
    return max(candidates, key=len) if candidates else None


def show(console=None, categories=None):
    console = console or Console()
    found = devicetree.collect(categories)

    exp_dir = _experiment_dir()
    exp_mount = _mount_for_path(exp_dir, [d["label"] for d in found.get("storage") or []])

    tree = Tree(f"[bold]•[/bold] {_system_state()}")
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
            if name == "storage" and device["label"] == exp_mount:
                label += f" [bold yellow]← experiments ({exp_dir})[/bold yellow]"
            branch.add(label)

    console.print(tree)
    if not any_found:
        console.print("[dim]No devices found in the categories checked.[/dim]")


if __name__ == "__main__":
    show()
