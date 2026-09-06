"""
"Flash firmware" menu item. Thin -- the real logic lives in
core.installer.mpyfirmware, same pattern as environment.py wrapping
core.installer.environment. Also works as an update: sync_files() is
incremental (skip_unchanged), so this is safe to run again on a device
that's already configured.
"""


def flash():
	from core.installer import mpyfirmware
	mpyfirmware.sync()


if __name__ == "__main__":
	flash()
