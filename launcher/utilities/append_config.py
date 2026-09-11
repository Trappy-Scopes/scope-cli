"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

"Create additional configuration file" -- appends a NEW yaml file into
config.config_files, the layering mechanism TrappyConfig already reads
(core/permaconfig/config.py's __init__: every path in config.config_files
is loaded via confuse.YamlSource and layered ON TOP of the device's own
primary trappyconfig.yaml). Intended use: a shared lab manifest -- common
protocols, repositories, experiment payload structure -- declared once and
appended onto every device's own config, rather than copy-pasted into each
device's file by hand.

Merge behavior -- verified directly against confuse (not assumed): confuse
CAN deep-merge a dict across sources, but only when the reading code
bracket-chains all the way down to a scalar leaf (e.g.
`TrappyConfig.current.leaf("Experiment", "exp_dir")` -- formalized this
session as `TrappyConfig.leaf()`, since expframework/experiment.py and
scriptengine.py were the only two places already using this pattern by
hand). Every other reader -- most of this codebase that reads config,
including repo_sync.py, wallpaper.py, migrate_legacy.py,
check_new_features.py, mpyfirmware.py -- calls `TrappyConfig().get()` once
and treats the result as an ordinary plain dict. Proven with a direct
confuse test: for THAT access pattern, confuse does NOT merge dicts across
sources -- whichever source has the highest priority at a given key
provides that key's entire value, wholesale, and every sibling key the
*other* source declared at that same path is simply gone.

Concretely: an appended file that declares `config: {log_level: 5}` does
not add log_level alongside the primary file's other config.* keys as
seen by almost all of this codebase's own code -- it makes `config:`
appear to be *just* `{log_level: 5}`, silently dropping the primary
file's venv/git_dependencies/micropython/etc. entirely.

The only genuinely safe way to use config_files given this, until/unless
the wide-spread `TrappyConfig().get()` access pattern is changed: put
lab-wide settings under a top-level key the primary file never touches at
all (this tool's template uses `lab:`), not inside config:/Experiment:/
devices: alongside the primary file's own entries for those same blocks.
"""

import os

from rich.console import Console
from rich.prompt import Confirm, Prompt

from core.permaconfig.config import TrappyConfig

from .edit_config import pick_editor

TEMPLATE = """## Additional Trappy-Scopes configuration file, layered on top of the
## primary trappyconfig.yaml (see config.config_files in that file).
##
## IMPORTANT -- verified against confuse directly, not assumed: almost
## every reader in this codebase (repo_sync.py, wallpaper.py, mpyfirmware.
## py, and 11 others) loads the whole config in one shot and treats it as
## a plain dict. For that access pattern, confuse does NOT merge dicts
## across files -- declaring ANY key under config:/Experiment:/devices:
## here REPLACES that entire top-level block as those readers see it,
## silently dropping every other key the primary file set there.
##
## The safe way to use this file: put shared settings under a top-level
## key the primary file does not otherwise touch -- `lab:` below -- not
## inside config:/Experiment:/devices: alongside the primary file's own
## entries for those blocks.
##
## Example:
# lab:
#   name: "Living Physics Group"
#   shared_repos:
#     https://github.com/<org>/<repo>: "~/code/<repo>"
#   protocols_dirs: ["~/lab_protocols"]
"""


def _primary_config_path():
	loaded_from = getattr(TrappyConfig.current, "loaded_from", None)
	if loaded_from:
		return loaded_from
	for candidate in TrappyConfig.default_paths:
		if os.path.exists(candidate):
			return candidate
	return None


def _append_to_config_files(primary_path, new_path):
	"""Register `new_path` in the primary file's config.config_files list.
	Handles the three shapes that list can actually be in: entirely absent
	(most real files today, since it's only ever supplied by
	default_config.yaml's fallback `[]`), an empty inline list
	(`config_files: []`), or an existing block list. Returns True if it
	patched the file, False if the shape wasn't one of these three (left
	untouched rather than risking a bad edit)."""
	with open(primary_path) as f:
		lines = f.readlines()

	## Find the config_files: line, if any, first -- so "found but a shape
	## we won't touch" (a non-empty inline list) can bail out immediately,
	## rather than falling through to case 3 and inserting a duplicate key.
	key_line = None
	for i, line in enumerate(lines):
		stripped = line.strip()
		if stripped == "config_files:" or stripped.startswith("config_files:"):
			key_line = i
			break

	if key_line is not None:
		line = lines[key_line]
		stripped = line.strip()
		rest = stripped[len("config_files:"):].strip()
		indent = line[:len(line) - len(line.lstrip())]

		if rest in ("[]", "[ ]"):
			## Case 1: explicit empty inline list.
			lines[key_line] = f'{indent}config_files:\n{indent}  - "{new_path}"\n'
		elif rest == "":
			## Case 2: bare key, with or without existing block-list
			## children -- append AFTER whatever's already there (list
			## order is priority order: later entries outrank earlier
			## ones, per confuse's .set() semantics -- see the module
			## docstring), never before.
			j = key_line + 1
			while j < len(lines) and lines[j].startswith(indent + "  - "):
				j += 1
			lines.insert(j, f'{indent}  - "{new_path}"\n')
		else:
			return False  # an inline non-empty list -- don't risk a fragile edit

		with open(primary_path, "w") as f:
			f.writelines(lines)
		return True

	## Case 3: no config_files: key anywhere -- add one under the
	## top-level config: block.
	for i, line in enumerate(lines):
		if line.rstrip("\n") == "config:":
			lines.insert(i + 1, f'  config_files:\n    - "{new_path}"\n')
			with open(primary_path, "w") as f:
				f.writelines(lines)
			return True

	return False


def create(console=None):
	console = console or Console()
	primary_path = _primary_config_path()
	if primary_path is None:
		console.print('[yellow]No primary trappyconfig.yaml found -- create one first '
					   '("Create configuration file").[/yellow]')
		return

	name = Prompt.ask("Name for the new configuration file (no path, no extension)",
					   default="lab_manifest")
	target = os.path.join(os.path.dirname(primary_path), f"{name}.yaml")
	if os.path.exists(target):
		console.print(f"[red]{target} already exists.[/red]")
		return

	with open(target, "w") as f:
		f.write(TEMPLATE)
	console.print(f"[green]Created {target}.[/green]")

	if not Confirm.ask(f"Add it to config.config_files in {primary_path}?", default=True):
		console.print("[dim]Not registered -- it won't be loaded until you add it to "
					   "config.config_files yourself.[/dim]")
		return

	if _append_to_config_files(primary_path, target):
		console.print(f"[green]Registered in {primary_path}.[/green]")
	else:
		console.print(f"[red]config.config_files in {primary_path} isn't in a shape this tool "
					   f'handles automatically -- add `- "{target}"` to it by hand.[/red]')
		return

	if Confirm.ask(f"Open {target} in {pick_editor()} now?", default=True):
		os.system(f'{pick_editor()} "{target}"')


if __name__ == "__main__":
	create()
