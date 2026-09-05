"""
Sync the whole trappyverse/ folder with the config server. Only job: rsync
(§7.2 of docs/notes/restructuring.md -- one folder, both directions,
"update" mode so the latest copy of each file wins either way).

One thing not explicit in the original spec, added deliberately: the remote
destination is namespaced by scopeid, not one shared folder for every scope.
trappyverse/ now holds per-scope local state (relocated shelves, see
hive/physical.py) alongside configs -- syncing every scope into the same
remote folder would let one scope's device state silently overwrite
another's. Configs meant to be shared across scopes still can be, by putting
them in config.config_files and syncing those paths explicitly; this
utility's job is just the folder transfer.
"""

import os

from rich.console import Console

from core.permaconfig.config import TrappyConfig
from core.permaconfig.sharing import Share
import core.sync as sync


def sync_trappyverse(config=None, console=None):
	"""
	Sync ~/trappyverse/ with the config server. Returns True if both
	directions completed without error (or there was nothing configured to
	sync, which isn't a failure), False otherwise.
	"""
	console = console or Console()
	if config is None:
		config = TrappyConfig().get()

	block = TrappyConfig.optional_block(config, "config", "config_server")
	if block is None:
		console.print("[yellow]config_server is not configured or is inactive -- nothing to sync.[/yellow]")
		return True

	mount_point = sync.mount(block["server"], block["share"],
							  block["username"], block["password"])
	scopeid = Share.scopeid or config.get("name", "unknown-scope")
	remote = os.path.join(mount_point, block["destination"], scopeid) + "/"
	local = os.path.join(os.path.expanduser("~"), "trappyverse") + "/"
	os.makedirs(local, exist_ok=True)

	console.print(f"Syncing {local} <-> {remote} (latest copy wins)...")
	pull = sync.sync(remote, local, mode="update")
	push = sync.sync(local, remote, mode="update")

	ok = pull.returncode == 0 and push.returncode == 0
	if ok:
		console.print("[green]trappyverse/ synced.[/green]")
	else:
		console.print("[red]Sync had errors.[/red]")
	return ok


if __name__ == "__main__":
	sync_trappyverse()
