"""
Check status of every repository declared in config.git_dependencies
(the project itself, plus split-out dependents like pico_firmware or a
protocols directory), show it, then ask before pulling any of them.

Uses GitPython rather than shelling out to `git` and parsing text --
already a project dependency, and already the established pattern here
(core/bookkeeping/session.py uses it to record the commit id per session).
A real object model (repo.is_dirty(), iter_commits() for ahead/behind) is
worth it for more than this one menu item: it's the same foundation for
recording git state on Experiment more thoroughly later.
"""

import os

import git
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from core.permaconfig.config import TrappyConfig


def _status(path):
	"""Returns (dirty, ahead, behind, error) for the repo at `path`."""
	try:
		repo = git.Repo(path)
	except git.InvalidGitRepositoryError:
		return None, None, None, "not a git repository"
	except git.NoSuchPathError:
		return None, None, None, "path does not exist"

	dirty = repo.is_dirty()
	try:
		branch = repo.active_branch.name
		repo.remotes.origin.fetch()
		ahead = sum(1 for _ in repo.iter_commits(f"origin/{branch}..HEAD"))
		behind = sum(1 for _ in repo.iter_commits(f"HEAD..origin/{branch}"))
	except Exception as e:
		return dirty, None, None, f"fetch failed: {e}"

	return dirty, ahead, behind, None


def check_and_sync(config=None, console=None, confirm=True):
	"""
	Show status for every repo in config.git_dependencies, then -- if the
	caller confirms -- pull whichever are behind their remote.
	"""
	console = console or Console()
	if config is None:
		config = TrappyConfig().get()

	repos = (config.get("config") or {}).get("git_dependencies") or {}
	if not repos:
		console.print("[yellow]No repositories declared in config.git_dependencies.[/yellow]")
		return

	table = Table(title="Repository status")
	table.add_column("Path")
	table.add_column("Dirty")
	table.add_column("Ahead")
	table.add_column("Behind")
	table.add_column("Note", style="red")

	pullable = []
	for url, path in repos.items():
		path = os.path.expanduser(path)
		dirty, ahead, behind, error = _status(path)
		table.add_row(
			path,
			"-" if dirty is None else ("yes" if dirty else "no"),
			"-" if ahead is None else str(ahead),
			"-" if behind is None else str(behind),
			error or "",
		)
		if error is None and behind:
			pullable.append(path)

	console.print(table)

	if not pullable:
		return
	if confirm and not Confirm.ask(f"Pull {len(pullable)} repo(s) that are behind?"):
		return

	for path in pullable:
		git.Repo(path).remotes.origin.pull()
		console.print(f"[green]pulled[/green] {path}")


if __name__ == "__main__":
	check_and_sync()
