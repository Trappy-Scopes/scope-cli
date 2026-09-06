"""
"Check scripts' dependencies" menu items: for .py files under
config.Experiment.scripts_dirs (same recursive walk
expframework/scriptengine.py's ScriptEngine.find() already uses), parse
import statements (via ast, never executing the script) and check whether
each top-level module is importable in the current environment.

Static analysis only, deliberately: importing every declared script for
real to see what breaks would run arbitrary code as a side effect of
"checking" it, which isn't what a pre-install sanity check should do.
find_spec() answers "is this importable" without importing it.

Two modes: check_all() walks every declared script and reports a table.
check_specific() picks exactly one script -- via the same prompt_toolkit
WordCompleter path-completion ScriptEngine.find() uses -- and, if it's
missing anything, offers to install the missing packages with uv.
"""

import ast
import importlib.util
import os
import shutil
import subprocess

from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from core.permaconfig.config import TrappyConfig


def _find_scripts(scripts_dirs):
	"""[(path, root), ...] -- `root` (whichever scripts_dir a script was
	found under) travels with each path so callers can show it relative
	to that root instead of the full absolute path."""
	found = []
	for root in scripts_dirs:
		root = os.path.expanduser(root)
		if not os.path.isdir(root):
			continue
		for dirpath, dirnames, filenames in os.walk(root):
			dirnames[:] = [d for d in dirnames if not d.startswith(".")]
			found += [(os.path.join(dirpath, f), root) for f in filenames if f.endswith(".py")]
	return found


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


def _scripts_dirs(console):
	config = TrappyConfig().get()
	scripts_dirs = (config.get("Experiment") or {}).get("scripts_dirs") or []
	if not scripts_dirs:
		console.print("[dim]Experiment.scripts_dirs is not declared -- nothing to check.[/dim]")
	return scripts_dirs


def check_all(console=None):
	console = console or Console()
	scripts_dirs = _scripts_dirs(console)
	if not scripts_dirs:
		return

	scripts = _find_scripts(scripts_dirs)
	if not scripts:
		console.print(f"[dim]No .py scripts found under {scripts_dirs}.[/dim]")
		return

	table = Table(title=f"Script dependency check ({len(scripts)} script(s) found)")
	table.add_column("Script")
	table.add_column("Issue", style="red")

	problems = 0
	for path, root in scripts:
		rel = os.path.relpath(path, root)
		names = _top_level_imports(path)
		if names is None:
			table.add_row(rel, "could not parse (syntax error)")
			problems += 1
			continue
		missing = _missing(names)
		if missing:
			table.add_row(rel, f"missing {', '.join(missing)}")
			problems += 1

	if problems:
		console.print(table)
	else:
		console.print(f"[green]All {len(scripts)} declared scripts' imports resolve "
					   f"in the current environment.[/green]")


def _install_with_uv(missing, console):
	exe = shutil.which("uv")
	if not exe:
		console.print("[yellow]uv is not on PATH -- can't install automatically.[/yellow]")
		return

	command = [exe, "pip", "install", *missing]
	console.print(f"$ {' '.join(command)}")
	result = subprocess.run(command)
	if result.returncode == 0:
		console.print(f"[green]Installed: {', '.join(missing)}[/green]")
	else:
		console.print(f"[red]uv pip install failed (exit {result.returncode}).[/red]")


def check_specific(console=None):
	"""Same interactive picker as ScriptEngine.find(): a prompt_toolkit
	WordCompleter over the recursively-discovered script paths, tab-
	completable. Checks just that one script, then -- if anything's
	missing -- offers to `uv pip install` it into the current environment."""
	from prompt_toolkit import prompt
	from prompt_toolkit.completion import WordCompleter

	console = console or Console()
	scripts_dirs = _scripts_dirs(console)
	if not scripts_dirs:
		return

	scripts = _find_scripts(scripts_dirs)
	if not scripts:
		console.print(f"[dim]No .py scripts found under {scripts_dirs}.[/dim]")
		return

	paths = [path for path, _root in scripts]
	completer = WordCompleter(paths, sentence=True)
	try:
		chosen = prompt("Script to check [ press tab to expand ] -> ", completer=completer)
	except (EOFError, KeyboardInterrupt):
		return

	if not chosen:
		console.print("[dim]No script selected.[/dim]")
		return
	if chosen not in paths:
		console.print(f"[yellow]{chosen} is not one of the declared scripts.[/yellow]")
		return

	names = _top_level_imports(chosen)
	if names is None:
		console.print(f"[red]{chosen}: could not parse (syntax error).[/red]")
		return

	missing = _missing(names)
	if not missing:
		console.print(f"[green]{chosen}: all imports resolve.[/green]")
		return

	console.print(f"[red]{chosen}: missing {', '.join(missing)}[/red]")
	if Confirm.ask(f"Install {', '.join(missing)} with uv?", default=True):
		_install_with_uv(missing, console)


if __name__ == "__main__":
	check_all()
