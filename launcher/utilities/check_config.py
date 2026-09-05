"""
YAML syntax checker for the scope configuration file.

Deliberately syntax-only, per spec: pass -> "YAML syntax correct"; fail ->
a small rich-formatted traceback pointing at the exact line, not a full
schema validator. yaml.YAMLError already carries a `problem_mark` with
line/column, so no schema-validation library is needed for this.
"""

import os

import yaml
from rich.console import Console
from rich.panel import Panel

from core.permaconfig.config import TrappyConfig


def _config_path():
	for candidate in TrappyConfig.default_paths:
		if os.path.exists(candidate):
			return candidate
	return None


def check(path=None, console=None):
	"""
	Check the configuration file's YAML syntax. Returns True if valid,
	False otherwise (including "file not found").
	"""
	console = console or Console()
	path = path or _config_path()
	if path is None:
		console.print("[red]No trappyconfig.yaml found.[/red]")
		return False

	with open(path) as f:
		text = f.read()

	try:
		yaml.safe_load(text)
	except yaml.YAMLError as e:
		detail = str(e)
		mark = getattr(e, "problem_mark", None)
		if mark is not None:
			lines = text.splitlines()
			start = max(0, mark.line - 1)
			end = min(len(lines), mark.line + 2)
			snippet = "\n".join(
				f"{'>> ' if i == mark.line else '   '}{i + 1:>4} | {lines[i]}"
				for i in range(start, end)
			)
			detail = f"Line {mark.line + 1}, column {mark.column + 1}:\n\n{snippet}"
		console.print(Panel(detail, title="[red]YAML syntax error[/red]",
							 border_style="red", title_align="left"))
		return False

	console.print(f"[green]YAML syntax correct[/green] ({path})")
	return True


if __name__ == "__main__":
	check()
