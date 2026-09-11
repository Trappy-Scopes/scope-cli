"""
AI Generated -- formalized/rewritten by Claude (Anthropic), 2026-09, into
the source-tagged registry described below (register()/clear()/bind_all()).

Extensible keyboard shortcuts for the interactive REPL.

Two prefixes, both under Esc (see git history / commit notes for why Esc and
not a Ctrl-chord -- keeps Ctrl+S free, works identically on Mac Terminal,
Linux, and a headless Raspberry Pi console with zero configuration):

  Esc, s            -> scope.draw_tree()      (device tree)
  Esc, s, Space     -> scope                  (the bare assembly object)
  Esc, s, <letter>  -> scope.<device>.        (trailing dot, NOT executed --
                                                Tab from here to see/complete
                                                whatever that device actually
                                                exposes, then finish the line
                                                and hit Enter yourself)

  Esc, e            -> exp                    (the current Experiment)
  Esc, e, s         -> exp.__save__()         (flush experiment.yaml)
  Esc, e, w         -> exp.write()            (open the user-note prompt)
  Esc, e, n         -> exp.note(              (left open -- type the note
                                                text and close it yourself)
  Esc, e, m         -> exp.mstreams           (measurement streams dict)
  Esc, e, o         -> exp = findexp()        (Experiment has no .open() --
                                                this is the closest real
                                                equivalent, see useractions.py)
  Esc, e, c         -> exp.close()            (close the current experiment)
  Esc, e, h         -> exp.schedule           (the ExpScheduler instance)
  Esc, e, l         -> enable_history_logging()  (start REPL history logging,
                                                see utilities.repl_history)

Why the scope devices insert-and-stop instead of executing immediately:
CPython's `site` module already wires real Tab-completion for any
interactive session (`rlcompleter`, driven by `readline`), and it completes
on the object's *actual* live attributes -- `ScopeAssembly.add_device` does
`setattr(self, name, device)`, so every mounted device really is an
attribute of `scope`. Landing on "scope.<device>." and letting Tab reveal
what's really there means new device methods show up for free, with no
hand-maintained action table to keep in sync.

`exp`'s members don't need that: they're a small, stable, curated set on
the `Experiment` class itself (expframework/experiment.py), and some of
them need an argument, so those are left open with an unclosed paren
rather than auto-executed with nothing to log.

---

Formalized this session into a small registry, following the same
"module self-registers into a dict" convention already used elsewhere in
this codebase (core/idioms/platform.py's @category decorator), rather
than inventing a new pattern. Three channels feed the one registry, each
tagged by a `source` string so a channel's bindings can be replaced or
cleared independently of the others:

  - "config"     -- config.keyboard_shortcuts.bindings (inline) and/or a
                    separate YAML file at config.keyboard_shortcuts.file,
                    loaded once at boot by bind_config_shortcuts().
  - "scope"      -- auto-generated from ScopeAssembly.devices by
                    bind_scope_shortcuts(scope) -- the per-device-letter
                    logic this module always had, now going through
                    register() like everything else.
  - "experiment" -- the curated Experiment member table, bound by
                    bind_experiment_shortcuts().

register()/clear() are the extension point other code can call directly
to add or remove shortcuts at any point during a session -- e.g. (not
done in this pass -- deliberately deferred) a running Protocol could call
register(..., source=f"protocol:{name}") when it starts and
clear(f"protocol:{name}") when it ends, so a protocol's shortcuts don't
outlive it.

Usage (called from expenv/recipes/freestyle.py once `scope` is open):

	from core.utilities.keyboard_shortcuts import bind_all
	bind_all(scope)
"""

try:
	import readline
except ImportError:
	readline = None

import os

import yaml
from rich import print
from rich.table import Table

from core.permaconfig.config import TrappyConfig

LEADER = r"\e"      # Esc, pressed and released.
SCOPE_KEY = "s"     # Esc, s -> "talking about scope"
EXP_KEY = "e"       # Esc, e -> "talking about the experiment"
BARE_KEY = " "      # ..., Space -> the bare object (scope prefix only)

SCOPE_TREE_CODE = "scope.draw_tree()"

# letter -> (code, submit). submit=True auto-executes; False leaves the
# chord open for you to keep typing (e.g. an argument) and hit Enter yourself.
EXP_MEMBERS = {
	"s": ("exp.__save__()", True),
	"w": ("exp.write()", True),
	"n": ("exp.note(", False),
	"m": ("exp.mstreams", True),
	"o": ("exp = findexp()", True),  # no exp.open() exists; closest real equivalent
	"c": ("exp.close()", True),
	"h": ("exp.schedule", True),
	"l": ("enable_history_logging()", True),
}

# Force a specific letter for a scope device, bypassing the automatic
# assignment below, e.g. {"trappyframe": "f"}.
CUSTOM_KEYS = {}

# {source: {"esc s x": (code, submit, description)}} -- everything
# currently bound, grouped by which channel registered it. The single
# source of truth for show_shortcuts() and for clear(source)'s bookkeeping.
_REGISTRY = {}


def _readline_seq(keys):
	"""Turn a "esc s" style chord string into the literal escape sequence
	readline's parse_and_bind expects ("\\es"). "esc"/"escape" -> \\e;
	"space"/"spc" -> a literal space; anything else is used verbatim, so a
	single character just chords normally."""
	seq = ""
	for part in keys.split():
		low = part.lower()
		if low in ("esc", "escape"):
			seq += "\\e"
		elif low in ("space", "spc"):
			seq += " "
		else:
			seq += part
	return seq


def register(keys, code, submit=True, description=None, source="config"):
	"""Bind `keys` (a chord string, e.g. "esc s") to insert `code` into the
	REPL's input line, auto-running it if `submit`. Binds immediately, via
	readline -- there's no separate "commit" step. Tracked under `source`
	so clear(source) can remove just this channel's bindings later without
	disturbing bindings registered under a different source."""
	if readline is None:
		print("[red]keyboard_shortcuts: readline is unavailable, skipping.[/red]")
		return
	seq = _readline_seq(keys)
	suffix = "\\n" if submit else ""
	try:
		readline.parse_and_bind(f'"{seq}": "{code}{suffix}"')
	except Exception as e:
		print(f"[red]keyboard_shortcuts: failed to bind '{keys}': {e}[/red]")
		return
	_REGISTRY.setdefault(source, {})[keys] = (code, submit, description)


def clear(source):
	"""Un-bind every shortcut currently registered under `source`.
	Best-effort: readline has no query API for "what was this bound to
	before you touched it", so a cleared chord goes back to inserting
	nothing rather than restoring some prior behavior -- in practice not a
	real loss, since these are all Esc-prefixed chords no default readline
	config binds to anything."""
	if readline is None:
		return
	for keys in _REGISTRY.pop(source, {}):
		seq = _readline_seq(keys)
		try:
			readline.parse_and_bind(f'"{seq}":')
		except Exception:
			pass


def _assign_letters(device_names, reserved=()):
	"""
	Deterministically map each device to an unused letter, preferring the
	device's own initials so bindings stay mnemonic. Falls back to later
	letters in the name, then a-z/0-9, when initials collide. `reserved`
	(letters explicitly claimed by a config-declared "esc s <letter>"
	binding -- see _reserved_scope_letters()) are treated as already
	taken, so a device is never offered a letter you've deliberately
	bound yourself; without this, whichever of the "scope"/"config"
	channels happened to register last would silently win the chord,
	possibly overwriting an explicit binding with an auto-assigned one.
	"""
	used = set(CUSTOM_KEYS.values()) | {r.lower() for r in reserved}
	mapping = dict(CUSTOM_KEYS)

	for name in device_names:
		if name in mapping:
			continue
		letter = next((c for c in name.lower() if c.isalnum() and c not in used), None)
		if letter is None:
			letter = next((c for c in "abcdefghijklmnopqrstuvwxyz0123456789" if c not in used), None)
		if letter is None:
			print(f"[yellow]keyboard_shortcuts: ran out of letters, skipping device '{name}'[/yellow]")
			continue
		used.add(letter)
		mapping[name] = letter
	return mapping


def _reserved_scope_letters(config_bindings):
	"""Single-letter "esc s <letter>" chords already claimed by
	config-declared bindings -- fed into _assign_letters() as already
	taken, so an explicit binding is never at risk of being silently
	overwritten by an auto-assigned device letter landing on the same
	chord. Only exact "esc s X" (3 parts, single-char suffix) counts as a
	claim -- "esc s" and "esc s space" are the scope-tree/bare-scope
	chords themselves, not a device slot."""
	reserved = set()
	for entry in config_bindings:
		parts = entry["keys"].split()
		if len(parts) == 3 and parts[0].lower() in ("esc", "escape") \
				and parts[1] == SCOPE_KEY and len(parts[2]) == 1:
			reserved.add(parts[2].lower())
	return reserved


def bind_scope_shortcuts(scope, reserved=()):
	"""The Esc,s prefix -- device tree, bare scope, and one auto-assigned
	letter per mounted device. Re-running this (e.g. after devices change)
	first clears the old "scope" bindings so a device that's gone doesn't
	leave a stale chord behind. `reserved`: letters to skip when
	auto-assigning (see _reserved_scope_letters) -- bind_all() passes in
	whatever config.keyboard_shortcuts.bindings already claimed under
	this same "esc s" prefix."""
	clear("scope")
	scope_prefix = "esc s"
	register(scope_prefix, SCOPE_TREE_CODE, True, "Show the scope's device tree", source="scope")
	register(f"{scope_prefix} space", "scope", True, "The bare ScopeAssembly object", source="scope")

	device_names = list(scope.devices.keys())
	letter_of = _assign_letters(device_names, reserved=reserved)
	for name, letter in letter_of.items():
		if name not in device_names:
			continue  # a stale CUSTOM_KEYS entry for a device that isn't mounted
		register(f"{scope_prefix} {letter}", f"scope.{name}.", False, f"-> scope.{name}", source="scope")


def bind_experiment_shortcuts():
	"""The Esc,e prefix -- the curated Experiment member table."""
	clear("experiment")
	exp_prefix = "esc e"
	register(exp_prefix, "exp", True, "The current Experiment", source="experiment")
	for letter, (code, submit) in EXP_MEMBERS.items():
		register(f"{exp_prefix} {letter}", code, submit, source="experiment")


def _config_bindings(block):
	"""Bindings declared in config.keyboard_shortcuts -- inline `bindings:`
	and/or a separate `file:` (itself a top-level `bindings:` list) -- both
	optional, both usable together."""
	bindings = list(block.get("bindings") or [])
	file_path = block.get("file")
	if file_path:
		path = os.path.expanduser(file_path)
		if os.path.exists(path):
			with open(path) as f:
				file_data = yaml.safe_load(f) or {}
			bindings += file_data.get("bindings") or []
		else:
			print(f"[dim]keyboard_shortcuts: {path} declared but not found -- skipping.[/dim]")
	return bindings


def bind_config_shortcuts(config=None):
	"""Whatever's declared in config.keyboard_shortcuts -- inline and/or a
	separate file (see _config_bindings)."""
	if config is None:
		config = TrappyConfig().get()
	block = TrappyConfig.optional_block(config, "config", "keyboard_shortcuts")
	clear("config")
	if block is None:
		return
	for entry in _config_bindings(block):
		register(entry["keys"], entry["code"], entry.get("submit", True),
				  entry.get("description"), source="config")


def bind_all(scope=None, config=None):
	"""Bind everything config.keyboard_shortcuts allows: config-declared
	shortcuts (if the block is present/active), scope shortcuts if
	config.keyboard_shortcuts.scope_assembly (default True), experiment
	shortcuts if config.keyboard_shortcuts.experiment (default True).

	Call once the scope has been opened and its devices are mounted --
	safe to call again later (e.g. bind_scope_shortcuts(scope) alone) to
	refresh just the device list.
	"""
	if readline is None:
		print("[red]keyboard_shortcuts: readline is unavailable, skipping shortcut binding.[/red]")
		return

	if config is None:
		config = TrappyConfig().get()
	block = TrappyConfig.optional_block(config, "config", "keyboard_shortcuts")
	if block is None:
		return  # not declared, or active: false -- nothing to do

	## Scope/experiment bind FIRST, config LAST -- config-declared chords
	## are the ones you wrote down on purpose, so on any direct collision
	## (not just the "esc s <letter>" case _reserved_scope_letters already
	## prevents outright) they should be the one left standing, not
	## whichever channel happened to register last by accident of order.
	reserved = _reserved_scope_letters(_config_bindings(block))

	if block.get("scope_assembly", True):
		if scope is None:
			from hive.assembly import ScopeAssembly
			scope = ScopeAssembly.current
		if scope is not None:
			bind_scope_shortcuts(scope, reserved=reserved)

	if block.get("experiment", True):
		bind_experiment_shortcuts()

	bind_config_shortcuts(config)

	show_shortcuts()


def show_shortcuts():
	"""Print every currently bound shortcut, grouped by source, as a table."""
	table = Table(title="Keyboard shortcuts (Esc, ...)")
	table.add_column("Source", style="magenta")
	table.add_column("Chord", style="cyan", no_wrap=True)
	table.add_column("Runs", style="green")

	for source, bindings in _REGISTRY.items():
		for keys, (code, submit, description) in bindings.items():
			parts = keys.split()[1:]  # drop the leading "esc"
			label = "Esc, " + ", ".join("Space" if p.lower() in ("space", "spc") else p for p in parts)
			table.add_row(source, label, code)
	print(table)


if __name__ == "__main__":
	bind_all()
