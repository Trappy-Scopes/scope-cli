"""
The interactive launcher: `trappyscope --launcher`.

A small block in the middle of the screen -- the animation, a title line,
then the menu -- not a full-screen app. Built on `rich.live.Live` with
`screen=False` rather than prompt_toolkit's full-screen `Application`: Live
just repaints in place and has no minimum-terminal-size gate, which is what
made the previous, prompt_toolkit-based version unusable ("window too
small") on an ordinary terminal window. Keystrokes are read in POSIX
non-canonical ("cbreak") mode via stdlib `tty`/`termios` -- one key at a
time, no waiting for Enter, no terminal echo -- polled with `select()` on a
short timeout so the animation keeps looping between keystrokes rather than
blocking on input. The animation loops for as long as the menu is open --
until a selection is made or the user quits.

chlamy_dance.render() already emits raw 24-bit ANSI escapes, which
rich.text.Text.from_ansi() parses directly (verified), so embedding the
animation needed no changes to it at all.
"""

import select
import sys
import termios
import time
import tty

from rich.align import Align
from rich.console import Console, Group
from rich.live import Live
from rich.text import Text

from . import chlamy_dance as dance

FPS = 20
ESCAPE_TIMEOUT = 0.02  # seconds to wait for the rest of an arrow-key sequence

MENU_ITEMS = [
	("launch", "Launch normally"),
	("check", "Check configuration file"),
	("sync", "Sync configuration file"),
	("repos", "Repository utility"),
	("install", "Install / setup"),
	("intro", "Show the introduction"),
	("edit", "Edit the configuration file"),
]


class Menu:
	"""Selection state for a simple up/down/enter menu. No widget, no magic."""

	def __init__(self, items):
		self.items = items
		self.index = 0

	@property
	def selected_key(self):
		return self.items[self.index][0]

	def up(self):
		self.index = (self.index - 1) % len(self.items)

	def down(self):
		self.index = (self.index + 1) % len(self.items)


def _decode_key(first, read_byte):
	"""
	Turn a single already-read byte (plus, for escape sequences, a callback
	to read the following bytes) into one of 'up', 'down', 'enter', 'quit',
	or None (unrecognised). Pure logic, no terminal I/O -- `read_byte` is
	injected so this can be tested without a real tty.
	"""
	if first in ("\r", "\n"):
		return "enter"
	if first in ("q", "Q"):
		return "quit"
	if first == "\x1b":
		second = read_byte()
		if second != "[":
			return "quit"  # a bare Escape, not the start of a sequence
		third = read_byte()
		if third == "A":
			return "up"
		if third == "B":
			return "down"
		return None
	return None


def _render(menu, elapsed):
	t = elapsed % dance.DURATION
	animation = Text.from_ansi(dance.render(dance.frame(t)), no_wrap=True)

	title = Text("Trappy-Scopes launcher", style="bold", justify="center")

	menu_lines = Text()
	for i, (_, label) in enumerate(menu.items):
		prefix = "> " if i == menu.index else "  "
		style = "reverse" if i == menu.index else ""
		menu_lines.append(f"{prefix}{label}\n", style=style)

	return Align.center(Group(animation, Text(), title, Text(), menu_lines))


def run_launcher():
	"""
	Show the animated menu and run whichever action was chosen (or nothing,
	if cancelled). Each action is responsible for its own exit/handoff.
	"""
	menu = Menu(MENU_ITEMS)
	console = Console(width=dance.W)
	choice = None
	start = time.monotonic()

	fd = sys.stdin.fileno()
	old_settings = termios.tcgetattr(fd)
	try:
		tty.setcbreak(fd)
		with Live(_render(menu, 0), console=console, screen=False,
				  auto_refresh=False, transient=True) as live:
			while True:
				live.update(_render(menu, time.monotonic() - start), refresh=True)

				ready, _, _ = select.select([sys.stdin], [], [], 1 / FPS)
				if not ready:
					continue

				def read_byte(_timeout=ESCAPE_TIMEOUT):
					r, _, _ = select.select([sys.stdin], [], [], _timeout)
					return sys.stdin.read(1) if r else ""

				key = _decode_key(sys.stdin.read(1), read_byte)
				if key == "up":
					menu.up()
				elif key == "down":
					menu.down()
				elif key == "enter":
					choice = menu.selected_key
					break
				elif key == "quit":
					break
	finally:
		termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

	if choice is None:
		return

	from .utilities import (check_config, edit_config, installer, intro,
							 launch_normally, repo_sync, sync_config)
	{
		"launch": launch_normally.run,
		"check": check_config.check,
		"sync": sync_config.sync_trappyverse,
		"repos": repo_sync.check_and_sync,
		"install": installer.install,
		"intro": intro.show,
		"edit": edit_config.edit,
	}[choice]()
