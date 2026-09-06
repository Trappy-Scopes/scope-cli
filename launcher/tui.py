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
	("register", "Register device"),
	("micropython", "MicroPython >"),
	## Restored: core/installer/installer.py now uses `pip install -e .`,
	## the bug that broke a dev's editable install is fixed.
	("install", "Install / setup"),
	("intro", "Show the introduction"),
	("edit", "Edit the configuration file"),
	("exit", "Exit"),
]

MICROPYTHON_MENU_ITEMS = [
	("flash_mpy", "Flash MicroPython"),
	("flash_firmware", "Flash firmware"),
	("configure_board", "Configure board"),
	("wipe_device", "Wipe device"),
	("back", "< Back"),
]


class Menu:
	"""
	Selection state for a simple up/down/enter menu. No widget, no magic.

	Scrolls once there are more items than WINDOW_SIZE: the visible window
	tracks the selected index, and wrapping past either end (top -> bottom,
	bottom -> top) resets the window to that end rather than leaving it
	stranded mid-list. Added once "Device tree" pushed the menu to 9 items
	-- past the point where every item fit on screen at once next to the
	animation.
	"""

	## 12, not 6: the visible window is now laid out two columns wide (see
	## _render()), so this covers two 6-row columns -- enough for all 9
	## current items with room to grow before scrolling kicks in at all.
	WINDOW_SIZE = 12

	def __init__(self, items):
		self.items = items
		self.index = 0
		self.offset = 0

	@property
	def selected_key(self):
		return self.items[self.index][0]

	def _clamp_offset(self):
		window = min(self.WINDOW_SIZE, len(self.items))
		if self.index < self.offset:
			self.offset = self.index
		elif self.index >= self.offset + window:
			self.offset = self.index - window + 1

	def up(self):
		self.index = (self.index - 1) % len(self.items)
		self._clamp_offset()

	def down(self):
		self.index = (self.index + 1) % len(self.items)
		self._clamp_offset()

	def visible(self):
		"""(visible_items, offset, more_above, more_below) for rendering."""
		window = min(self.WINDOW_SIZE, len(self.items))
		end = self.offset + window
		return self.items[self.offset:end], self.offset, self.offset > 0, end < len(self.items)


def _decode_key(first, read_byte):
	"""
	Turn a single already-read byte (plus, for escape sequences, a callback
	to read the following bytes) into one of 'up', 'down', 'left', 'right',
	'enter', 'quit', or None (unrecognised). Pure logic, no terminal I/O --
	`read_byte` is injected so this can be tested without a real tty.
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
		if third == "C":
			return "right"
		if third == "D":
			return "left"
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


def _left_pad_lines(text, pad):
	"""Prepend `pad` spaces to every line of a (possibly multi-line,
	possibly styled) Text, preserving each line's own style spans."""
	if pad <= 0:
		return text
	padded = Text()
	for i, line in enumerate(text.split("\n")):
		if i > 0:
			padded.append("\n")
		padded.append(" " * pad)
		padded.append_text(line)
	return padded


def _render(menu, elapsed, console_width, version=None, venv_line=None, extra_line=None):
	t = elapsed % dance.DURATION
	animation = Text.from_ansi(dance.render(dance.frame(t, border=False)), no_wrap=True)

	title = Text("Trappy-Scopes launcher", style="bold", justify="center")
	header = [title]
	if version:
		header.append(Text(version, style="dim", justify="center"))
	if venv_line is not None:
		header.append(venv_line)
	if extra_line is not None:
		header.append(extra_line)

	visible_items, scroll_offset, more_above, more_below = menu.visible()

	## Two columns, column-major: the first half of the visible window down
	## the left column, the rest down the right -- reads the same order the
	## flat item list is already in, so up()/down() (index-based, unaware of
	## columns) still lands where you'd expect.
	entries = list(enumerate(visible_items, start=scroll_offset))
	split = (len(entries) + 1) // 2
	left, right = entries[:split], entries[split:]

	## Fixed widths, computed from the *whole* item list rather than just
	## the visible window, so the column boundaries don't shift as the menu
	## scrolls.
	col_width = max(len(label) for _, label in menu.items) + 2  # +2: the "> "/"  " prefix
	row_width = col_width + 4 + col_width  # 4: the gap between columns

	def entry_style(key, i):
		if i == menu.index:
			return "bold black on bright_green"
		if key == "exit":
			return "grey58"
		return "green"

	menu_lines = Text()
	for row in range(len(left)):
		i, (key, label) = left[row]
		prefix = "> " if i == menu.index else "  "
		menu_lines.append(f"{prefix}{label}".ljust(col_width), style=entry_style(key, i))
		menu_lines.append("    ")
		if row < len(right):
			ri, (rkey, rlabel) = right[row]
			rprefix = "> " if ri == menu.index else "  "
			menu_lines.append(f"{rprefix}{rlabel}", style=entry_style(rkey, ri))
		menu_lines.append("\n")

	scroll_hints = []
	if more_above:
		scroll_hints.append("↑ more above")
	if more_below:
		scroll_hints.append("↓ more below")

	## Align.center does NOT reliably centre this composition: it centres
	## each rendered *line* independently, based on that line's own visible
	## width -- and, verified directly, that measurement strips trailing
	## whitespace first. A menu row right-padded to a uniform total length
	## (the previous attempt at this fix) therefore still measures as
	## whatever text precedes the padding, which differs row to row, so
	## Align lands each row at a different offset regardless. The animation
	## (every row a fixed 39 characters, no trailing-whitespace ambiguity)
	## and the header/hint Texts (self-centering via their own justify=
	## "center", independent of Align) happened to look right before the
	## menu had rows of very different lengths -- which is exactly why this
	## surfaced only once the menu went two columns wide.
	##
	## Fixed here by computing the centering offset once, from the actual
	## live terminal width, and left-padding the animation and menu block
	## ourselves -- no Align involved for either. The header/hint Texts
	## keep their own justify="center" (self-centering against the full
	## console width, verified to work with no Align wrapper at all): since
	## the manually-centered block's own midpoint is put at console_width/2
	## by construction, both approaches land on the same centerline.
	content_width = max(dance.W, row_width)
	pad = max(0, (console_width - content_width) // 2)

	animation = _left_pad_lines(animation, pad)
	menu_lines = _left_pad_lines(menu_lines, pad)

	body = [animation, Text(), *header, Text(), menu_lines]
	if scroll_hints:
		body.append(Text("   ".join(scroll_hints), style="dim", justify="center"))
	body.append(Text())
	body.append(Text("↑/↓ move   enter select   Esc/q quit", style="dim", justify="center"))

	return Group(*body)


def _show_menu(items=None, extra_line=None, device_options=None, device_index=0):
	"""
	Run the animated menu until a selection is made ('enter') or the user
	quits ('q'/bare Escape). Returns the chosen key, or None if quit --
	unless `device_options` is given (see below), in which case it returns
	(chosen_key_or_None, current_device_or_None) instead.

	`items` defaults to the top-level MENU_ITEMS; passing MICROPYTHON_MENU_ITEMS
	(or any other list) renders the exact same animated menu one level deeper --
	this is the whole submenu mechanism, no separate rendering path needed.
	`extra_line` is an optional Text shown under the version/venv lines.

	`device_options` (a list of strings, e.g. connected device ports) turns
	on Left/Right cycling through them, live, on this same screen -- no
	separate picker page. Up/Down still move between menu items as normal.
	The current one is shown via _device_line(), overriding `extra_line`
	while cycling is active. Passing `device_options=None` (the default)
	leaves this off entirely and keeps the plain single-value return, so
	every caller that doesn't need it is unaffected.

	Recomputes the version line fresh on every call rather than once for
	the whole launcher session: a micro-utility run in between (repository
	sync in particular) can change this repo's HEAD, and a stale cached
	commit would then be wrong the next time the menu shows.
	"""
	menu = Menu(items if items is not None else MENU_ITEMS)
	console = Console()
	choice = None
	idx = device_index
	start = time.monotonic()
	version = _version_line()
	venv_line = _venv_line()

	def current_extra_line():
		if device_options:
			return _device_line(device_options[idx])
		return extra_line

	fd = sys.stdin.fileno()
	old_settings = termios.tcgetattr(fd)
	try:
		tty.setcbreak(fd)
		with Live(_render(menu, 0, console.width, version, venv_line, current_extra_line()), console=console, screen=False,
				  auto_refresh=False, transient=True) as live:
			while True:
				## console.width read fresh every frame, not cached from
				## before the loop started -- a resized terminal window
				## must recentre on the next frame, not stay centered for
				## whatever size the window happened to be at launch.
				live.update(_render(menu, time.monotonic() - start, console.width, version, venv_line, current_extra_line()),
							refresh=True)

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
				elif key == "left" and device_options:
					idx = (idx - 1) % len(device_options)
				elif key == "right" and device_options:
					idx = (idx + 1) % len(device_options)
				elif key == "enter":
					choice = menu.selected_key
					break
				elif key == "quit":
					break
	finally:
		termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

	if device_options is not None:
		return choice, (device_options[idx] if device_options else None)
	return choice


def _device_line(port):
	line = Text("Device: ", justify="center")
	if port:
		line.append(port, style="green")
	else:
		line.append("(no devices found)", style="yellow")
	return line


def _show_micropython_menu():
	"""
	The "MicroPython >" submenu -- Flash MicroPython / Flash firmware /
	Configure board / Wipe device. Runs its own loop (same return-to-menu-
	or-leave prompt as the top-level one) until the user picks "< Back" or
	quits, at which point control returns to run_launcher()'s own loop,
	redrawing the top menu -- not the whole launcher exiting.

	Which device an action targets is picked inline, on this same screen,
	via Left/Right (see _show_menu()'s device_options) -- Up/Down still
	move between the actions themselves. No separate picker page at all:
	with one device connected, it's simply the only thing Left/Right can
	land on; with several, cycling through them updates the "Device: ..."
	line live. Candidates are re-read fresh every time this menu redraws,
	so a device plugged in or unplugged between actions is picked up; the
	current selection (by port string, not index -- devices can enumerate
	in a different order after a re-scan) carries across actions run back
	to back.
	"""
	from core.idioms import devicetree
	from .utilities import configure_board, flash_firmware, flash_micropython, wipe_device
	from rich.prompt import Confirm

	MICROPYTHON_UTILITIES = {
		"flash_mpy": flash_micropython.flash,
		"flash_firmware": flash_firmware.flash,
		"configure_board": configure_board.configure,
		"wipe_device": wipe_device.wipe,
	}

	selected_port = None

	while True:
		device_ports = [p.device for p in devicetree.micropython_candidates()]
		device_index = device_ports.index(selected_port) if selected_port in device_ports else 0

		choice, selected_port = _show_menu(MICROPYTHON_MENU_ITEMS,
											device_options=device_ports,
											device_index=device_index)

		if choice is None or choice == "back":
			return

		MICROPYTHON_UTILITIES[choice](port=selected_port)

		if not Confirm.ask("\nReturn to the MicroPython menu?", default=True):
			return


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
	until the user explicitly does one or the other. "MicroPython >" is the
	one exception: it opens its own submenu (_show_micropython_menu()) and,
	on return, goes straight back to this loop -- no extra "return to menu?"
	prompt on top of the submenu's own.
	"""
	from .utilities import (check_config, device_tree, edit_config, installer,
							 intro, launch_normally, register_device, repo_sync,
							 sync_config)

	MICRO_UTILITIES = {
		"check": check_config.check,
		"sync": sync_config.sync_trappyverse,
		"repos": repo_sync.check_and_sync,
		"devicetree": device_tree.show,
		"register": register_device.register,
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
		if choice == "micropython":
			_show_micropython_menu()
			continue

		MICRO_UTILITIES[choice]()

		from rich.prompt import Confirm
		if not Confirm.ask("\nReturn to the launcher menu?", default=True):
			return
