"""
"Wipe device" menu item. Thin -- the real logic lives in
core.installer.mpyfirmware, same pattern as environment.py wrapping
core.installer.environment. Deletes everything on a device's filesystem;
mpyfirmware.wipe() itself asks for confirmation before doing anything.
"""


def wipe(port=None):
	from core.installer import mpyfirmware
	mpyfirmware.wipe(port=port)


if __name__ == "__main__":
	wipe()
