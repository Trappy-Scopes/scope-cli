"""
Edit the configuration file.

Editor choice, in order: config.terminal_editor (if the user declared one),
else nano (if installed), else vi.
"""

import os
import shutil

from core.permaconfig.config import TrappyConfig


def _pick_editor(config=None):
	if config is None:
		config = TrappyConfig().get()
	preferred = (config.get("config") or {}).get("terminal_editor")
	if preferred:
		return preferred
	if shutil.which("nano"):
		return "nano"
	return "vi"


def edit():
	path = None
	for candidate in TrappyConfig.default_paths:
		if os.path.exists(candidate):
			path = candidate
			break
	if path is None:
		print("No trappyconfig.yaml found -- run with --new_config first.")
		return
	os.system(f'{_pick_editor()} "{path}"')


if __name__ == "__main__":
	edit()
