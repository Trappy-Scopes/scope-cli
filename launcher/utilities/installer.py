"""
Install/setup. Deferred: wraps the existing Installer as-is for now; a
fuller installer utility is future work, not this round.
"""


def install():
	from core.installer.installer import Installer
	Installer.do_all()


if __name__ == "__main__":
	install()
