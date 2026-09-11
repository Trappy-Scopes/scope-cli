"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

One-time migration for a device still running an older config/state layout
onto the current one. Fixes what's safe to automate (config file location,
PhysicalObject shelve state location, a stale `abstraction`/`abstractions`
key), and reports -- without guessing a fix -- the one shape mismatch that
can't be auto-converted without losing information (git_sync). Every check
is collected as a row and reported in one table at the end, not scattered
prose -- same convention as check_scripts.py's check_all().

Note (2026-09-09): the config.expdir/Experiment.exp_dir key-mismatch check
that used to live here was removed -- expframework/experiment.py now reads
Experiment.exp_dir via TrappyConfig.leaf() (which correctly falls back to
default_config.yaml's own Experiment.exp_dir default), not the old
undocumented config.expdir key with no fallback at all. A device whose
config still declares the old `config.expdir` isn't broken by this (the
key is just unread now, not an error) but can drop it -- it's dead.

Meant to be run once per physical device, on that device itself: it
operates on the ambient home directory (os.path.expanduser("~")), the
same way every other launcher utility reads whatever TrappyConfig resolves
locally, not a path supplied for some other machine.

Every finding here is backed by an actual `grep` of what reads what --
not a guess from comparing template files, which this session already
found to be stale/aspirational in more than one place (see
docs/notes/restructuring.md's "schema drift" table). Concretely:
  - hive/assembly.py reads scopeconfig["abstractions"] (plural); every
    real config this session has seen (and core/permaconfig/exempler.py,
    the one other example config in this repo) declares `abstraction:`
    (singular). Currently harmless -- the branch that reads it doesn't
    run in the current startup path -- but a free, safe rename.
  - repo_sync.py and hive/assembly.py both read config.git_sync as a
    bare bool plus a separate config.git_dependencies map; the other
    documented shape (git_sync as a block with active/command/repos)
    can't be auto-converted since its repos are local paths with no
    remote URL.
"""

import glob
import os
import re
import shutil

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from core.permaconfig.config import TrappyConfig

HOME = os.path.expanduser("~")
OLD_CONFIG_PATH = os.path.join(HOME, "trappyconfig.yaml")
NEW_CONFIG_PATH = os.path.join(HOME, "trappyverse", "trappyconfig.yaml")
STATE_DIR = os.path.join(HOME, "trappyverse", "state")


def _config_path():
	loaded_from = getattr(TrappyConfig.current, "loaded_from", None)
	if loaded_from:
		return loaded_from
	for candidate in TrappyConfig.default_paths:
		if os.path.exists(candidate):
			return candidate
	return None


def _migrate_config_location():
	if os.path.exists(NEW_CONFIG_PATH):
		return ("Config location", f"already at {NEW_CONFIG_PATH}", "no action needed")
	if not os.path.exists(OLD_CONFIG_PATH):
		return ("Config location", "not found at either location", "no action needed")

	if not Confirm.ask(f"Found config at the old location ({OLD_CONFIG_PATH}). "
						f"Move it to {NEW_CONFIG_PATH}?", default=True):
		return ("Config location", f"found at old location ({OLD_CONFIG_PATH})", "skipped")
	os.makedirs(os.path.dirname(NEW_CONFIG_PATH), exist_ok=True)
	shutil.move(OLD_CONFIG_PATH, NEW_CONFIG_PATH)
	return ("Config location", f"found at old location ({OLD_CONFIG_PATH})", f"moved to {NEW_CONFIG_PATH}")


def _declared_persistent_devices(config):
	"""Device names declared in config["devices"] whose kwargs ask for
	persistent=True -- these are the only ones hive/physical.py's
	PhysicalObject backs with a shelve, and the only ones that could have
	pre-migration state sitting at the old location."""
	names = []
	for name, spec in (config.get("devices") or {}).items():
		kwargs = (spec or {}).get("kwargs") or {}
		if kwargs.get("persistent"):
			names.append(name)
	return names


def _migrate_shelve_state(config):
	rows = []
	names = _declared_persistent_devices(config)
	if not names:
		return [("Shelve state", "no devices declared persistent=True", "no action needed")]

	os.makedirs(STATE_DIR, exist_ok=True)
	for name in names:
		check = f"Shelve state ({name})"
		## dbm's on-disk shape varies by backend (a single "<name>.db", or
		## a "<name>.dir"/"<name>.dat"/"<name>.bak" trio) -- glob rather
		## than assume one extension.
		old_matches = sorted(p for p in glob.glob(os.path.join(HOME, f"{name}.*")) + [os.path.join(HOME, name)]
							  if os.path.isfile(p))
		if not old_matches:
			rows.append((check, "no legacy state found", "no action needed"))
			continue

		new_matches_exist = bool(glob.glob(os.path.join(STATE_DIR, f"{name}.*")) +
								  glob.glob(os.path.join(STATE_DIR, name)))
		if new_matches_exist:
			rows.append((check, f"legacy file(s) at {', '.join(old_matches)}",
						 "left alone -- new-location state already exists"))
			continue

		if not Confirm.ask(f"{name}: found legacy shelve state at "
						   f"{', '.join(old_matches)}. Move into {STATE_DIR}?", default=True):
			rows.append((check, f"legacy file(s) at {', '.join(old_matches)}", "skipped"))
			continue
		for path in old_matches:
			shutil.move(path, os.path.join(STATE_DIR, os.path.basename(path)))
		rows.append((check, f"legacy file(s) at {', '.join(old_matches)}", f"moved into {STATE_DIR}"))
	return rows


def _check_abstraction_key(config, config_path):
	"""hive/assembly.py reads scopeconfig["abstractions"] (plural); every
	config seen this session (and exempler.py) declares `abstraction:`
	(singular). Currently harmless -- freestyle's ScopeAssembly(scopeid)
	call doesn't pass config, so the branch never runs -- but a safe,
	deterministic rename, not a guess."""
	check = "abstraction(s) key"
	if "abstractions" in config:
		return (check, "already `abstractions:` (plural)", "no action needed")
	if "abstraction" not in config:
		return (check, "not declared", "no action needed")
	if config_path is None:
		return (check, "found `abstraction:` (singular)", "could not locate a config file to patch -- rename by hand")

	if not Confirm.ask(
		"Found `abstraction:` (singular) -- hive/assembly.py reads "
		'`scopeconfig["abstractions"]` (plural). Currently harmless. Rename to '
		f"`abstractions:` in {config_path}?",
		default=True,
	):
		return (check, "found `abstraction:` (singular)", "skipped")

	with open(config_path) as f:
		text = f.read()
	new_text, count = re.subn(r"(?m)^abstraction:", "abstractions:", text, count=1)
	if not count:
		return (check, "found `abstraction:` (singular)", "could not find the line to rename -- do it by hand")
	with open(config_path, "w") as f:
		f.write(new_text)
	return (check, "found `abstraction:` (singular)", "renamed to `abstractions:`")


def _check_git_sync_shape(config):
	"""git_sync (nested under config:) should be a bare bool, with a
	separate config.git_dependencies: {repo-url: local-path} map -- the
	shape hive/assembly.py and repo_sync.py both actually read. The other
	documented shape -- git_sync as a block ({active, command, repos:
	[...]}), with no git_dependencies at all -- can't be auto-converted:
	its `repos` are local paths with no remote URL, which git_dependencies
	needs to do anything. Reported, not fixed."""
	check = "config.git_sync shape"
	git_sync = (config.get("config") or {}).get("git_sync")
	if isinstance(git_sync, dict):
		return (check, f"old structured shape ({git_sync!r})",
				"manual fix needed -- rewrite as a bool + separate git_dependencies map")
	return (check, "already a plain bool", "no action needed")


def migrate(console=None):
	console = console or Console()

	rows = [_migrate_config_location()]

	## Re-load after a possible move -- TrappyConfig.default_paths already
	## checks the new location first, so this picks up whichever now exists.
	config = TrappyConfig().get()
	config_path = _config_path()

	rows += _migrate_shelve_state(config)
	rows.append(_check_abstraction_key(config, config_path))
	rows.append(_check_git_sync_shape(config))

	table = Table(title="Legacy config/state migration")
	table.add_column("Check")
	table.add_column("Finding")
	table.add_column("Action", style="green")
	for check, finding, action in rows:
		style = "yellow" if action.startswith(("skipped", "manual fix", "could not")) else None
		table.add_row(check, finding, action, style=style)
	console.print(table)


if __name__ == "__main__":
	migrate()
