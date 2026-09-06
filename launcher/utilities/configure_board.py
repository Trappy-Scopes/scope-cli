"""
"Configure board" menu item: pull the device's current board.py, let the
user edit it in their own editor, push it back. Deliberately not "prompt
for name/circuit_id and build the file" -- the user edits the real file
directly (same pattern as edit_config.py's config.terminal_editor), so
nothing about board.py's own format has to be reproduced or kept in sync
here.

Prints the known circuit list as a reference (files under
config.micropython.firmware_dir's circuits/, plus the two circuit_ids
hardcoded inline in pico_firmware/main.py rather than backed by a file) --
but circuit_id is never validated against it. Get it wrong and the device
will say so on boot ("Undefined circuit!"), same as it always did.
"""

import os
import tempfile

from rich.columns import Columns
from rich.console import Console
from rich.prompt import Confirm
from rich.text import Text

from core.external import pyboard
from core.installer import mpyfirmware
from core.permaconfig.config import TrappyConfig
from .edit_config import pick_editor

## Not backed by a file in circuits/ -- handled inline in pico_firmware/main.py
## itself (see core/installer/mpyfirmware.py's own docstring for the same note).
_INLINE_CIRCUIT_IDS = ("idle_device_that_blinks", "4_clustcontrol_v1_proto")


def _known_circuits():
    """(circuit_id, is_inline) pairs -- file-backed ones (in circuits/) first,
    then the two hardcoded-in-main.py ones, each sorted within its own group."""
    cfg = (TrappyConfig().get().get("config") or {}).get("micropython") or {}
    firmware_dir = cfg.get("firmware_dir")
    file_backed = []
    if firmware_dir:
        circuits_dir = os.path.join(os.path.expanduser(firmware_dir), "pico_firmware", "circuits")
        if os.path.isdir(circuits_dir):
            file_backed = sorted(
                name[:-3] for name in os.listdir(circuits_dir)
                if name.endswith(".py")
            )
    return [(c, False) for c in file_backed] + [(c, True) for c in sorted(_INLINE_CIRCUIT_IDS)]


def _print_known_circuits(console, circuits):
    if not circuits:
        return
    console.print("[bold]Known circuit_ids:[/bold]")
    entries = [
        Text(f"• {name}" + (" (inline)" if inline else ""), style="dim" if inline else None)
        for name, inline in circuits
    ]
    console.print(Columns(entries, padding=(0, 3), equal=False))


def configure(console=None):
    console = console or Console()

    chosen = mpyfirmware.pick_device(console)
    if chosen is None:
        return

    _print_known_circuits(console, _known_circuits())

    board_ = None
    local_path = None
    try:
        board_ = pyboard.Pyboard(chosen.device, 115200)
        board_.enter_raw_repl()

        with tempfile.NamedTemporaryFile(mode="w", suffix="_board.py", delete=False) as f:
            local_path = f.name

        if board_.fs_exists("board.py"):
            board_.fs_get("board.py", local_path)
        else:
            console.print("[yellow]No board.py on the device yet.[/yellow]")

        with open(local_path) as f:
            is_empty = not f.read().strip()

        if is_empty:
            console.print("[yellow]board.py is empty.[/yellow]")
            ## pico_firmware/main.py itself writes a real default (name,
            ## circuit_id="idle_device_that_blinks", the wifi/dt-sync flags)
            ## the first time it finds no board.py -- re-running it gets that
            ## same default without us having to reproduce its format here.
            ## This also re-triggers whatever circuit_id ends up set, same as
            ## a normal reboot would -- not a side-effect-free operation.
            if Confirm.ask("Execute pico_firmware/main.py to generate a default?", default=True):
                try:
                    board_.exec_("exec(open('pico_firmware/main.py').read())")
                except Exception as e:
                    console.print(f"[red]Running main.py failed: {e}[/red]")
                if board_.fs_exists("board.py"):
                    board_.fs_get("board.py", local_path)

        if not Confirm.ask("Edit board.py now?", default=True):
            return

        os.system(f'{pick_editor()} "{local_path}"')

        board_.fs_put(local_path, "board.py")
        console.print(f"[green]board.py updated on {chosen.device}.[/green]")
    except Exception as e:
        console.print(f"[red]Configure board failed: {e}[/red]")
    finally:
        if board_ is not None:
            try:
                board_.exit_raw_repl()
            except Exception:
                pass
            try:
                board_.close()
            except Exception:
                pass
        if local_path and os.path.exists(local_path):
            os.remove(local_path)


if __name__ == "__main__":
    configure()
