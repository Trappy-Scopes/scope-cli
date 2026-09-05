"""Edit the configuration file. Deferred: opens $EDITOR on it, as-is."""

import os

from core.permaconfig.config import TrappyConfig


def edit():
	path = None
	for candidate in TrappyConfig.default_paths:
		if os.path.exists(candidate):
			path = candidate
			break
	if path is None:
		print("No trappyconfig.yaml found -- run with --new_config first.")
		return
	os.system(f'{os.environ.get("EDITOR", "vi")} "{path}"')


if __name__ == "__main__":
	edit()
