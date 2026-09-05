"""
Install/setup. Thin wrapper -- the actual logic lives in
core.installer.installer.Installer.do_all(), which now uses
`pip install -e .` (was the bug behind this menu item being removed
entirely for a while) and delegates hardware-profile sync to
core.installer.environment.
"""


def install():
	from core.installer.installer import Installer
	Installer.do_all()


if __name__ == "__main__":
	install()
