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

The menu itself keeps running: choosing a "micro-utility" (check/sync/repos/
intro/edit) runs it, shows its output, then asks whether to return to the
menu or leave -- see run_launcher(). "Launch normally" and "Exit" are the
only terminal choices.
"""

import os
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
	("devicetree", "Device tree"),
	## Restored: core/installer/installer.py now uses `pip install -e .`,
	## the bug that broke a dev's editable install is fixed.
	("install", "Install / setup"),
	("intro", "Show the introduction"),
	("edit", "Edit the configuration file"),
	("exit", "Exit"),
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


def _version_line():
	"""
	"<short commit> · <date of that commit>", or None if this isn't a git
	checkout (e.g. installed from a wheel) or has no commits yet. Computed
	once by the caller, not per frame -- git.Repo() plus a commit lookup is
	too slow to redo twenty times a second.

	Uses GitPython, not subprocess -- the established pattern in this
	codebase (core/bookkeeping/session.py already does exactly this to
	record a commit id per session).
	"""
	try:
		import git
		from core.permaconfig.sharing import Share
		commit = git.Repo(Share.scopecli_fullpath).head.commit
		return f"{commit.hexsha[:7]} · {commit.committed_datetime:%Y-%m-%d}"
	except Exception:
		return None


def _venv_line():
	"""
	"venv: <actual running environment>  (set in TrappyConfig)" or
	"(not set)" -- the two can disagree (e.g. you're standing in the right
	conda env by habit, but config.venv was never declared, so a *different*
	machine relying on it to auto-activate would get nothing). Reads the
	raw config file directly rather than instantiating TrappyConfig, which
	has side effects (logging setup, a "config set" printout) not wanted on
	every menu redraw.
	"""
	import sys
	env_name = (os.environ.get("CONDA_DEFAULT_ENV")
				or os.environ.get("VIRTUAL_ENV")
				or sys.prefix)

	from core.permaconfig.config import TrappyConfig
	declared = False
	for candidate in TrappyConfig.default_paths:
		if os.path.exists(candidate):
			try:
				import yaml
				with open(candidate) as f:
					config = yaml.safe_load(f) or {}
				declared = TrappyConfig.optional_block(config, "config", "venv") is not None
			except Exception:
				pass
			break

	line = Text(f"venv: {env_name}  ", justify="center")
	line.append("(set in TrappyConfig)" if declared else "(not set)",
				style="green" if declared else "red")
	return line


def _render(menu, elapsed, version=None, venv_line=None):
	t = elapsed % dance.DURATION
	animation = Text.from_ansi(dance.render(dance.frame(t, border=False)), no_wrap=True)

	title = Text("Trappy-Scopes launcher", style="bold", justify="center")
	header = [title]
	if version:
		header.append(Text(version, style="dim", justify="center"))
	if venv_line is not None:
		header.append(venv_line)

	menu_lines = Text()
	for i, (key, label) in enumerate(menu.items):
		selected = i == menu.index
		prefix = "> " if selected else "  "
		if selected:
			style = "bold black on bright_green"
		elif key == "exit":
			style = "grey58"
		else:
			style = "green"
		menu_lines.append(f"{prefix}{label}\n", style=style)

	return Align.center(Group(animation, Text(), *header, Text(), menu_lines))


def _show_menu():
	"""
	Run the animated menu until a selection is made ('enter') or the user
	quits ('q'/bare Escape). Returns the chosen key, or None if quit.

	Recomputes the version line fresh on every call rather than once for
	the whole launcher session: a micro-utility run in between (repository
	sync in particular) can change this repo's HEAD, and a stale cached
	commit would then be wrong the next time the menu shows.
	"""
	menu = Menu(MENU_ITEMS)
	console = Console()
	choice = None
	start = time.monotonic()
	version = _version_line()
	venv_line = _venv_line()

	fd = sys.stdin.fileno()
	old_settings = termios.tcgetattr(fd)
	try:
		tty.setcbreak(fd)
		with Live(_render(menu, 0, version, venv_line), console=console, screen=False,
				  auto_refresh=False, transient=True) as live:
			while True:
				live.update(_render(menu, time.monotonic() - start, version, venv_line), refresh=True)

				ready, _, _ = select.select([fd], [], [], 1 / FPS)
				if not ready:
					continue

				## os.read, not sys.stdin.read: select() reports readiness on
				## the raw fd, and a buffered TextIOWrapper read can silently
				## read ahead past what was asked for -- the next select()
				## check on the same fd then finds nothing waiting even
				## though the rest of an escape sequence already arrived, just
				## stuck in Python's buffer instead of the kernel's. os.read
				## never buffers ahead, so select() and it agree about what's
				## actually available.
				def read_byte(_timeout=ESCAPE_TIMEOUT):
					r, _, _ = select.select([fd], [], [], _timeout)
					return os.read(fd, 1).decode() if r else ""

				key = _decode_key(os.read(fd, 1).decode(), read_byte)
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

	return choice


def run_launcher():
	"""
	Show the animated menu and run whichever action was chosen, looping
	back to the menu afterward -- except for "Launch normally" and "Exit",
	which are terminal: the former hands off to a real interactive scope
	CLI session (there is no "back" from that), the latter is exactly a
	request to stop.

	For every other ("micro-utility") action, the utility runs to
	completion showing its own output, then a plain yes/no prompt asks
	whether to return to the menu or leave -- the launcher keeps running
	until the user explicitly does one or the other.
	"""
	from .utilities import (check_config, device_tree, edit_config, installer,
							 intro, launch_normally, repo_sync, sync_config)

	MICRO_UTILITIES = {
		"check": check_config.check,
		"sync": sync_config.sync_trappyverse,
		"repos": repo_sync.check_and_sync,
		"devicetree": device_tree.show,
		"install": installer.install,
		"intro": intro.show,
		"edit": edit_config.edit,
	}

	while True:
		choice = _show_menu()

		if choice is None or choice == "exit":
			return
		if choice == "launch":
			launch_normally.run()
			return

		MICRO_UTILITIES[choice]()

		from rich.prompt import Confirm
		if not Confirm.ask("\nReturn to the launcher menu?", default=True):
			return
