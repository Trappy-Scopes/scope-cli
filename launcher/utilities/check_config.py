"""
YAML syntax checker for the scope configuration file.

Deliberately syntax-only, per spec: pass -> "YAML syntax correct"; fail ->
a small rich-formatted traceback pointing at the exact line, not a full
schema validator. yaml.YAMLError already carries a `problem_mark` with
line/column, so no schema-validation library is needed for this.

Offers to create one (TrappyConfig.new_config()) when none exists --
that method already existed but had no caller anywhere in the codebase
before this; the README's `--new_config` flag it was clearly meant for
was never actually wired to any argparser flag either.
"""

import os

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm

from core.permaconfig.config import TrappyConfig


def _config_path():
	for candidate in TrappyConfig.default_paths:
		if os.path.exists(candidate):
			return candidate
	return None


def status():  # AI Generated
	"""(ready: bool, detail: str) -- read-only, no prompts, safe to call on
	every "Install / setup" menu redraw. Shared by check() (which adds the
	interactive create/error-reporting flow on top) and the status panel."""
	path = _config_path()
	if path is None:
		return False, "no trappyconfig.yaml found"
	try:
		with open(path) as f:
			yaml.safe_load(f.read())
	except yaml.YAMLError:
		return False, f"{path} exists but has a YAML syntax error"
	return True, path


def check(path=None, console=None):
	"""
	Check the configuration file's YAML syntax. Returns True if valid,
	False otherwise (including "file not found", after offering to
	create a new one from the default template).
	"""
	console = console or Console()
	path = path or _config_path()
	if path is None:
		console.print("[yellow]No trappyconfig.yaml found.[/yellow]")
		if Confirm.ask("Create a new one from the default template?", default=True):
			target = TrappyConfig.default_paths[0]
			TrappyConfig.new_config(None, target)
			path = target
		else:
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


def check_templates(path=None, console=None):
	"""AI Generated -- companion to check() above, kept separate rather
	than folded into it: check() is deliberately syntax-only per its own
	docstring, this is a different, softer kind of problem (a value that
	parses fine as YAML but wouldn't evaluate the way its author expects).
	Scans every string value in the config for "{...}"-looking template
	syntax and flags any that references a name outside
	TrappyConfig.TEMPLATE_VARS -- a typo, or a field that doesn't actually
	support templating at all (see launcher/utilities/sync_config.py's
	config_server.destination warning). Report-only, never blocks."""
	import re
	console = console or Console()
	path = path or _config_path()
	if path is None:
		return True
	with open(path) as f:
		data = yaml.safe_load(f.read()) or {}

	problems = []

	def walk(node, breadcrumb):
		if isinstance(node, dict):
			for k, v in node.items():
				walk(v, breadcrumb + [str(k)])
		elif isinstance(node, list):
			for i, v in enumerate(node):
				walk(v, breadcrumb + [str(i)])
		elif isinstance(node, str) and "{" in node:
			names = re.findall(r"\{(\w+)", node)
			unknown = [n for n in names if n not in TrappyConfig.TEMPLATE_VARS]
			if unknown:
				problems.append((".".join(breadcrumb), node, unknown))

	walk(data, [])
	for field_path, value, unknown in problems:
		console.print(
			f"[yellow]{field_path}: '{value}' references unknown template "
			f"var(s) {unknown} -- only {TrappyConfig.TEMPLATE_VARS} are supported.[/yellow]"
		)
	return not problems


if __name__ == "__main__":
	check()
