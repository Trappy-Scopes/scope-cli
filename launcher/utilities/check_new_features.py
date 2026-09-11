"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

"Check new features are configured" -- unlike migrate_legacy.py (which fixes
stale/wrong-shape config left over from before this branch's changes), this
checks whether the newer capability blocks this branch's own features
depend on (config.micropython.*, config.git_dependencies) actually have
real, usable values on THIS device -- not just "present and non-crashing",
which core/installer/mpyfirmware.py and repo_sync.py already guard against
on their own, but "filled in with something that will actually work here."

Nothing here can be auto-fixed: every value needed (a firmware version, a
firmware image path/URL, a local repo checkout path) is something only
this device's owner knows -- there is no sensible default to invent, unlike
Experiment.exp_dir (default_config.yaml declares a real fallback for it).
Report only, tabulated the same way.
"""

import os

from rich.console import Console
from rich.table import Table

from core.permaconfig.config import TrappyConfig


def _check_micropython(config):
	rows = []
	mp = (config.get("config") or {}).get("micropython") or {}

	version = mp.get("version")
	rows.append(("micropython.version", str(version) if version else "not set",
				  "ok" if version else "flashing can't skip boards already at this version"))

	image = mp.get("firmware_image")
	rows.append(("micropython.firmware_image", str(image) if image else "not set",
				  "ok" if image else "\"Flash MicroPython\" has nothing to flash"))

	firmware_dir = mp.get("firmware_dir")
	if not firmware_dir:
		rows.append(("micropython.firmware_dir", "not set",
					  "\"Flash firmware\"/sync has nothing to sync"))
	else:
		expanded = os.path.expanduser(firmware_dir)
		exists = os.path.isdir(expanded)
		rows.append(("micropython.firmware_dir", firmware_dir,
					  "ok" if exists else f"path does not exist on this device: {expanded}"))
	return rows


def _check_git_dependencies(config):
	deps = (config.get("config") or {}).get("git_dependencies") or {}
	if not deps:
		return [("git_dependencies", "not declared",
				 "Repository utility will show no extra repos for this device")]

	rows = []
	for url, path in deps.items():
		expanded = os.path.expanduser(path)
		exists = os.path.isdir(expanded)
		rows.append((f"git_dependencies[{url}]", path,
					 "ok" if exists else f"path does not exist on this device: {expanded}"))
	return rows


def check(console=None):
	console = console or Console()
	config = TrappyConfig().get()

	rows = _check_micropython(config) + _check_git_dependencies(config)

	table = Table(title="New-feature configuration readiness")
	table.add_column("Field")
	table.add_column("Value")
	table.add_column("Status")
	for field, value, status in rows:
		table.add_row(field, value, status, style=None if status == "ok" else "yellow")
	console.print(table)


if __name__ == "__main__":
	check()
