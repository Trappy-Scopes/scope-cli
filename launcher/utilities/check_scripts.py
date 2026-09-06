"""
"Check declared scripts' dependencies" menu item: for every .py file under
config.Experiment.scripts_dirs (same recursive walk
expframework/scriptengine.py's ScriptEngine.find() already uses), parse
its import statements (via ast, never executing the script) and check
whether each top-level module is importable in the current environment.

Static analysis only, deliberately: importing every declared script for
real to see what breaks would run arbitrary code as a side effect of
"checking" it, which isn't what a pre-install sanity check should do.
find_spec() answers "is this importable" without importing it.
"""

import ast
import importlib.util
import os

from rich.console import Console

from core.permaconfig.config import TrappyConfig


def _find_scripts(scripts_dirs):
	paths = []
	for root in scripts_dirs:
		root = os.path.expanduser(root)
		if not os.path.isdir(root):
			continue
		for dirpath, dirnames, filenames in os.walk(root):
			dirnames[:] = [d for d in dirnames if not d.startswith(".")]
			paths += [os.path.join(dirpath, f) for f in filenames if f.endswith(".py")]
	return paths


def _top_level_imports(path):
	"""Top-level module names a script imports. Relative imports
	(from . import x) are skipped -- project-internal by definition,
	not external dependencies to verify. Returns None on a parse error."""
	try:
		with open(path) as f:
			tree = ast.parse(f.read(), filename=path)
	except (SyntaxError, OSError):
		return None

	names = set()
	for node in ast.walk(tree):
		if isinstance(node, ast.Import):
			for alias in node.names:
				names.add(alias.name.split(".")[0])
		elif isinstance(node, ast.ImportFrom):
			if node.level == 0 and node.module:
				names.add(node.module.split(".")[0])
	return names


def _missing(names):
	missing = []
	for name in sorted(names):
		try:
			found = importlib.util.find_spec(name) is not None
		except (ImportError, ModuleNotFoundError, ValueError):
			found = False
		if not found:
			missing.append(name)
	return missing


def check(console=None):
	console = console or Console()
	config = TrappyConfig().get()
	scripts_dirs = (config.get("Experiment") or {}).get("scripts_dirs") or []
	if not scripts_dirs:
		console.print("[dim]Experiment.scripts_dirs is not declared -- nothing to check.[/dim]")
		return

	scripts = _find_scripts(scripts_dirs)
	if not scripts:
		console.print(f"[dim]No .py scripts found under {scripts_dirs}.[/dim]")
		return

	console.print(f"Checking {len(scripts)} script(s) under {scripts_dirs} ...")
	any_missing = False
	for path in scripts:
		names = _top_level_imports(path)
		if names is None:
			console.print(f"  [red]{path}: could not parse (syntax error)[/red]")
			any_missing = True
			continue
		missing = _missing(names)
		if missing:
			any_missing = True
			console.print(f"  [red]{path}: missing {', '.join(missing)}[/red]")

	if not any_missing:
		console.print("[green]All declared scripts' imports resolve in the current environment.[/green]")


if __name__ == "__main__":
	check()
