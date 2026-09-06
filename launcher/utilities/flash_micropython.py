"""
"Flash MicroPython" menu item. Thin -- the real logic lives in
core.installer.mpyfirmware, same pattern as environment.py wrapping
core.installer.environment.
"""


def flash(port=None):
	from core.installer import mpyfirmware
	mpyfirmware.flash(port=port)


if __name__ == "__main__":
	flash()
