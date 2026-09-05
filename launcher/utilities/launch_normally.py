"""
"Launch normally": what happens when you run `trappyscope` without
--launcher, and also the first, default menu item when you do. Runs the
whole pre-flight sequence, then hands off to the real scope CLI.

Sequence: environment (uv/conda/PEP668/hardware-profile sync) -> check
config -> sync config (if configured) -> re-check (a file rewritten by the
sync has not itself been validated) -> repo status/sync -> boot. Whatever
flags the original `trappyscope` invocation carried are already sitting in
Share.argparse by the time boot() runs -- core.argparser parses the whole
of sys.argv in one pass before the launcher/fast-track branch is even
chosen, so there's nothing extra to forward here.

Environment activation was the one open piece of this sequence (§7.3 step
0, since the very first session on this codebase) -- now implemented, via
core.installer.environment.
"""

from rich.console import Console

from . import check_config, sync_config, repo_sync, environment, boot as boot_


def run(console=None):
	console = console or Console()

	environment.ensure()

	if not check_config.check(console=console):
		return

	if sync_config.sync_trappyverse(console=console):
		if not check_config.check(console=console):
			return

	repo_sync.check_and_sync(console=console)

	boot_.boot()


if __name__ == "__main__":
	run()
