"""
"Check virtual environment" menu item: does the environment declared in
config.venv (command + name) actually exist, and if not, offer to create
it. Nothing in this codebase checked this before -- core.installer.
environment's venv handling is a generic PEP 668 fallback, unrelated to
config.venv specifically.

Every config.venv example in this codebase (default_config.yaml's
template and the one real trappyconfig.yaml checked this session) uses
the same shape: `command: source .../bin/activate`, `name: <env>` --
classic conda activation, not a plain venv. Existence is checked against
conda/mamba accordingly; a declared venv that doesn't look conda-shaped
is reported, not guessed at further.
"""

import os
import re
import shutil
import subprocess

from rich.console import Console
from rich.prompt import Confirm

from core.permaconfig.config import TrappyConfig
from core.permaconfig.sharing import Share


def _min_python_version():
	"""Lower bound of requires-python from pyproject.toml (e.g. "3.12"
	from ">=3.12,<4.0") -- read with a plain regex, not a TOML parser:
	this can run from whatever interpreter happens to be on PATH before
	a proper environment necessarily exists, and tomllib itself needs
	Python 3.11+, not guaranteed here."""
	path = os.path.join(Share.scopecli_fullpath, "pyproject.toml")
	try:
		with open(path) as f:
			text = f.read()
		match = re.search(r'requires-python\s*=\s*"[>=~]*\s*(\d+\.\d+)', text)
		if match:
			return match.group(1)
	except OSError:
		pass
	return "3.12"


def check(console=None):
	console = console or Console()
	config = TrappyConfig().get()
	venv = TrappyConfig.optional_block(config, "config", "venv")
	if venv is None:
		console.print("[dim]config.venv is not declared or inactive -- nothing to check.[/dim]")
		return

	name = venv.get("name")
	command = venv.get("command", "")
	console.print(f"Declared venv: [bold]{name}[/bold]  (activated via: {command})")

	## "miniconda"/"anaconda" both already contain "conda" as a substring,
	## so checking for that alone covers all three.
	if not name or "conda" not in command.lower():
		console.print("[yellow]This doesn't look like a conda activation command -- "
					   "can't check existence automatically.[/yellow]")
		return

	exe = shutil.which("mamba") or shutil.which("conda")
	if not exe:
		console.print("[yellow]No conda/mamba on PATH -- can't check existence automatically.[/yellow]")
		return

	result = subprocess.run([exe, "env", "list"], capture_output=True, text=True)
	existing = {line.split()[0] for line in result.stdout.splitlines()
				if line and not line.startswith("#")}
	if name in existing:
		console.print(f"[green]{name} already exists.[/green]")
		return

	console.print(f"[yellow]{name} does not exist yet.[/yellow]")
	if not Confirm.ask(f"Create conda environment '{name}' now?", default=True):
		return

	version = _min_python_version()
	command_ = [exe, "create", "-n", name, "-y", f"python={version}"]
	console.print(f"$ {' '.join(command_)}")
	result = subprocess.run(command_)
	if result.returncode == 0:
		console.print(f"[green]Created {name}.[/green]")
	else:
		console.print(f"[red]Failed to create {name}.[/red]")


if __name__ == "__main__":
	check()
