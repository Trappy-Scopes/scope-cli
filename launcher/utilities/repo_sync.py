"""
"Repository utility >" submenu: status for every repository declared in
config.git_dependencies (split-out dependents like pico_firmware or a
protocols directory) plus trappyscopes' own codebase -- previously the
one repo this tool had no update option for at all -- then an animated
menu (same _show_menu() mechanism as MicroPython/Configuration) to pick
ONE to pull. Pulling re-shows an updated table before the menu appears
again, rather than syncing everything behind at once with no way to see
what changed afterward.

Uses GitPython rather than shelling out to `git` and parsing text --
already a project dependency, and already the established pattern here
(core/bookkeeping/session.py uses it to record the commit id per session).
"""

import os

import git
from rich.console import Console
from rich.prompt import Confirm
from rich.table import Table

from core.permaconfig.config import TrappyConfig
from core.permaconfig.sharing import Share

_SELF_LABEL = "trappyscopes (this codebase)"


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


def all_repos(config=None):
	"""{label: path} -- config.git_dependencies plus trappyscopes' own
	repo (Share.scopecli_fullpath, the same path _version_line() in
	tui.py already reads its commit from)."""
	if config is None:
		config = TrappyConfig().get()
	repos = {path: path for path in ((config.get("config") or {}).get("git_dependencies") or {}).values()}
	repos[_SELF_LABEL] = Share.scopecli_fullpath
	return repos


def status_table(repos):
	"""(Table, {label: (dirty, ahead, behind, error)}) for `repos` (as
	returned by all_repos()) -- built together so the menu that follows
	doesn't have to re-fetch what the table just showed."""
	table = Table(title="Repository status")
	table.add_column("Repository")
	table.add_column("Dirty")
	table.add_column("Ahead")
	table.add_column("Behind")
	table.add_column("Note", style="red")

	statuses = {}
	for label, path in repos.items():
		path = os.path.expanduser(path)
		dirty, ahead, behind, error = _status(path)
		statuses[label] = (dirty, ahead, behind, error)
		table.add_row(
			label,
			"-" if dirty is None else ("yes" if dirty else "no"),
			"-" if ahead is None else str(ahead),
			"-" if behind is None else str(behind),
			error or "",
		)
	return table, statuses


def pull(label, path, console):
	"""Pull one repo by label/path (as returned by all_repos()). Used by
	the launcher's animated picker (tui.py's _show_repo_menu()); public
	so it isn't a same-module-only private helper."""
	try:
		git.Repo(os.path.expanduser(path)).remotes.origin.pull()
		console.print(f"[green]pulled[/green] {label}")
		if label == _SELF_LABEL:
			console.print("[yellow]trappyscopes itself was updated -- restart the "
						   "launcher (exit and run `trappyscope` again) to actually "
						   "run the new code. This running session is still "
						   "executing what was already loaded in memory; only the "
						   "version line will reflect the pull immediately.[/yellow]")
	except Exception as e:
		console.print(f"[red]Pull failed: {e}[/red]")


if __name__ == "__main__":
	_console = Console()
	_table, _ = status_table(all_repos())
	_console.print(_table)
