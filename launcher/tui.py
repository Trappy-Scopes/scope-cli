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
	("repos", "Repository utility >"),
	("devicetree", "Device tree"),
	("register", "Register device"),
	("configuration", "Configuration >"),
	("micropython", "MicroPython >"),
	## Restored: core/installer/installer.py now uses `pip install -e .`,
	## the bug that broke a dev's editable install is fixed.
	("install", "Install / setup >"),
	("intro", "Show the introduction"),
	("exit", "Exit"),
]

CONFIGURATION_MENU_ITEMS = [
	("check", "Check configuration file"),
	("sync", "Sync configuration file"),
	("edit", "Edit the configuration file"),
	("back", "< Back"),
]

INSTALL_MENU_ITEMS = [
	("check_venv", "Check virtual environment"),
	("check_config", "Check configuration file"),
	("install_packages", "Install packages + hardware profiles"),
	("check_scripts", "Check scripts' dependencies"),
	("back", "< Back"),
]

MICROPYTHON_MENU_ITEMS = [
	("select_device", "Select device"),
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


def _renderable_to_text(renderable, width):
	"""
	Render any Rich renderable (e.g. a Table) to a plain multi-line Text --
	the left-padding trick _render() uses to centre the chlamy animation
	only works on a Text (split("\\n") + append_text), not an arbitrary
	renderable, so this is the conversion step for anything passed as
	_show_menu()'s `content` in place of the animation. force_terminal=True
	is what makes capture() actually emit ANSI codes instead of stripping
	them (verified directly: without it, a captured Table's own styling --
	e.g. a colored column -- is lost).
	"""
	capture_console = Console(width=width, force_terminal=True, no_color=False)
	with capture_console.capture() as cap:
		capture_console.print(renderable)
	return Text.from_ansi(cap.get().rstrip("\n"))


def _render(menu, elapsed, console_width, version=None, venv_line=None, extra_line=None, content=None):
	if content is not None:
		## Replaces the animation entirely -- e.g. the repository picker's
		## status table -- rather than showing both. Centred the same way,
		## by the same code below; only where the block's own width comes
		## from differs.
		animation = content
	else:
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
	## The animation's own width is computed rather than assumed as
	## dance.W, so an arbitrary `content` (a table, say) centres by
	## exactly the same rule -- its own widest rendered line -- with no
	## special-casing needed here for which one is actually showing.
	animation_width = max((len(line) for line in animation.plain.split("\n")), default=0)
	content_width = max(animation_width, row_width)
	pad = max(0, (console_width - content_width) // 2)

	animation = _left_pad_lines(animation, pad)
	menu_lines = _left_pad_lines(menu_lines, pad)

	body = [animation, Text(), *header, Text(), menu_lines]
	if scroll_hints:
		body.append(Text("   ".join(scroll_hints), style="dim", justify="center"))
	body.append(Text())
	body.append(Text("↑/↓ move   enter select   Esc/q quit", style="dim", justify="center"))

	return Group(*body)


def _show_menu(items=None, extra_line=None, content=None):
	"""
	Run the animated menu until a selection is made ('enter') or the user
	quits ('q'/bare Escape). Returns the chosen key, or None if quit.

	`items` defaults to the top-level MENU_ITEMS; passing MICROPYTHON_MENU_ITEMS
	(or any other list) renders the exact same animated menu one level deeper --
	this is the whole submenu mechanism, no separate rendering path needed.
	`extra_line` is an optional Text shown under the version/venv lines --
	the MicroPython submenu uses it to show the currently selected device.
	`content`, if given, replaces the chlamy animation entirely -- the
	repository picker uses this to show its status table centred in the
	same place the animation would otherwise be, rather than printing it
	separately above an unrelated animation (see _renderable_to_text()).

	Recomputes the version line fresh on every call rather than once for
	the whole launcher session: a micro-utility run in between (repository
	sync in particular) can change this repo's HEAD, and a stale cached
	commit would then be wrong the next time the menu shows.
	"""
	menu = Menu(items if items is not None else MENU_ITEMS)
	console = Console()
	choice = None
	start = time.monotonic()
	version = _version_line()
	venv_line = _venv_line()

	fd = sys.stdin.fileno()
	old_settings = termios.tcgetattr(fd)
	try:
		tty.setcbreak(fd)
		with Live(_render(menu, 0, console.width, version, venv_line, extra_line, content), console=console, screen=False,
				  auto_refresh=False, transient=True) as live:
			while True:
				## console.width read fresh every frame, not cached from
				## before the loop started -- a resized terminal window
				## must recentre on the next frame, not stay centered for
				## whatever size the window happened to be at launch.
				live.update(_render(menu, time.monotonic() - start, console.width, version, venv_line, extra_line, content),
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
				elif key == "enter":
					choice = menu.selected_key
					break
				elif key == "quit":
					break
	finally:
		termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)

	return choice


def _select_device():
	"""
	Pick a MicroPython-looking device via the same animated menu UI as
	everything else -- reuses _show_menu() with a synthesized item list,
	rather than a plain numbered prompt or a special-cased shortcut.
	Returns a port string, or None if there's nothing to pick from, or the
	user backs out.

	One common menu regardless of how many candidates there are: with
	just one, it's simply the only (and already-highlighted) item in an
	otherwise ordinary menu -- one Enter press away -- not a second code
	path that skips rendering it altogether.
	"""
	from core.idioms import devicetree

	candidates = devicetree.micropython_candidates()
	if not candidates:
		Console().print("[dim]No MicroPython-looking serial devices found.[/dim]")
		return None
	items = [(p.device, p.device + (f" ({p.serial_number})" if p.serial_number else ""))
			 for p in candidates]
	items.append(("_cancel", "< Cancel"))
	choice = _show_menu(items)
	return None if choice in (None, "_cancel") else choice


def _device_line(port):
	line = Text("Device: ", justify="center")
	line.append(port if port else "(none selected -- each action will prompt)",
				style="green" if port else "yellow")
	return line


def _show_micropython_menu():
	"""
	The "MicroPython >" submenu -- Select device / Flash MicroPython /
	Flash firmware / Configure board / Wipe device. Runs its own loop
	(same return-to-menu-or-leave prompt as the top-level one) until the
	user picks "< Back" or quits, at which point control returns to
	run_launcher()'s own loop, redrawing the top menu -- not the whole
	launcher exiting.

	The selected device (a port string, or None) is picked once on entry
	via _select_device() -- the same common picker "Select device" uses
	later too, whether there's one candidate (the only, already-
	highlighted item -- one Enter press away) or several -- and remembered
	for as long as this submenu stays open, passed to every action below,
	so picking it once covers a whole run of actions instead of being
	asked again each time. Each action still falls back to its own picker
	if nothing was selected here, or if the selected port is no longer
	connected (core.installer.mpyfirmware.pick_device()'s `preselected`
	handling covers that).
	"""
	from .utilities import configure_board, flash_firmware, flash_micropython, wipe_device
	from rich.prompt import Confirm

	MICROPYTHON_UTILITIES = {
		"flash_mpy": flash_micropython.flash,
		"flash_firmware": flash_firmware.flash,
		"configure_board": configure_board.configure,
		"wipe_device": wipe_device.wipe,
	}

	selected_port = _select_device()

	while True:
		choice = _show_menu(MICROPYTHON_MENU_ITEMS, extra_line=_device_line(selected_port))

		if choice is None or choice == "back":
			return

		if choice == "select_device":
			selected_port = _select_device()
			continue

		MICROPYTHON_UTILITIES[choice](port=selected_port)

		if not Confirm.ask("\nReturn to the MicroPython menu?", default=True):
			return


def _show_configuration_menu():
	"""
	The "Configuration >" submenu -- Check configuration file / Sync
	configuration file / Edit the configuration file. Same submenu
	mechanism as "MicroPython >" (_show_menu() one level deeper, its own
	return-to-menu-or-leave loop) -- no device axis needed here, so it's
	the simpler shape _show_micropython_menu() itself used before device
	selection was added.
	"""
	from .utilities import check_config, edit_config, sync_config
	from rich.prompt import Confirm

	CONFIGURATION_UTILITIES = {
		"check": check_config.check,
		"sync": sync_config.sync_trappyverse,
		"edit": edit_config.edit,
	}

	while True:
		choice = _show_menu(CONFIGURATION_MENU_ITEMS)

		if choice is None or choice == "back":
			return

		CONFIGURATION_UTILITIES[choice]()

		if not Confirm.ask("\nReturn to the Configuration menu?", default=True):
			return


def _show_install_menu():
	"""
	The "Install / setup >" submenu -- Check virtual environment / Check
	configuration file / Install packages + hardware profiles / Check
	scripts' dependencies. Same submenu mechanism as Configuration/
	MicroPython/Repository utility -- each item independent, run in any
	order, any number of times, rather than a linear wizard.

	This is the actual fix for "Install / setup" going straight into
	`pip install -e .` with no way to back out or check anything first:
	that's now its own explicit item (install_packages), and the three
	pre-flight checks that used to not exist at all -- does the declared
	config.venv actually exist, does trappyconfig.yaml exist, do the
	scripts under Experiment.scripts_dirs have their imports satisfied --
	are separate items here instead.
	"""
	from .utilities import check_config, check_scripts, check_venv, installer
	from rich.prompt import Confirm

	INSTALL_UTILITIES = {
		"check_venv": check_venv.check,
		"check_config": check_config.check,
		"install_packages": installer.install,
		"check_scripts": check_scripts.check,
	}

	while True:
		choice = _show_menu(INSTALL_MENU_ITEMS)

		if choice is None or choice == "back":
			return

		INSTALL_UTILITIES[choice]()

		if not Confirm.ask("\nReturn to the Install/setup menu?", default=True):
			return


def _show_repo_menu():
	"""
	The "Repository utility >" submenu -- shows the status table centred
	in place of the animation (see _render()'s `content` parameter and
	_renderable_to_text()), with a menu below it to pick ONE repo to
	pull -- no separate animation, and no disconnected plain-printed
	table above an unrelated menu. Repos come from repo_sync.all_repos()
	every time this redraws (not a static item list, unlike MicroPython/
	Configuration's fixed menus), which now includes trappyscopes' own
	repo alongside config.git_dependencies -- previously the one repo
	this tool had no update option for at all.

	Pulling redraws with a freshly rebuilt table before the menu appears
	again, rather than pulling everything behind at once with no way to
	see what actually changed afterward.
	"""
	from .utilities import repo_sync
	from rich.console import Console
	from rich.prompt import Confirm

	console = Console()

	while True:
		repos = repo_sync.all_repos()
		if not repos:
			console.print("[yellow]No repositories declared in config.git_dependencies.[/yellow]")
			return
		table, statuses = repo_sync.status_table(repos)
		table_text = _renderable_to_text(table, console.width)

		items = [(label, label) for label in repos] + [("back", "< Back")]
		choice = _show_menu(items, content=table_text)

		if choice is None or choice == "back":
			return

		dirty, ahead, behind, error = statuses.get(choice, (None, None, None, None))
		if error:
			console.print(f"[red]Cannot sync {choice}: {error}[/red]")
		elif not behind:
			console.print(f"[dim]{choice} is already up to date.[/dim]")
		elif Confirm.ask(f"Pull {choice}?", default=True):
			repo_sync.pull(choice, repos[choice], console)


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
	until the user explicitly does one or the other. "Repository utility >",
	"Configuration >", "Install / setup >" and "MicroPython >" are the
	exceptions: they open their own submenus and, on return, go straight
	back to this loop -- no extra "return to menu?" prompt on top of the
	submenu's own.
	"""
	from .utilities import device_tree, intro, launch_normally, register_device

	MICRO_UTILITIES = {
		"devicetree": device_tree.show,
		"register": register_device.register,
		"intro": intro.show,
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
		if choice == "configuration":
			_show_configuration_menu()
			continue
		if choice == "install":
			_show_install_menu()
			continue
		if choice == "repos":
			_show_repo_menu()
			continue

		MICRO_UTILITIES[choice]()

		from rich.prompt import Confirm
		if not Confirm.ask("\nReturn to the launcher menu?", default=True):
			return
