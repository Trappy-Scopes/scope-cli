"""
Install/setup. Thin wrapper -- the actual logic lives in
core.installer.installer.Installer.do_all(), which now uses
`pip install -e .` (was the bug behind this menu item being removed
entirely for a while) and delegates hardware-profile sync to
core.installer.environment.
"""


def status():  # AI Generated
	"""(ready: bool, detail: str) -- whether trappyscopes is registered as
	an installed distribution, i.e. whether `pip install -e .` has been
	run at all. Doesn't re-verify every declared dependency resolves --
	that's what "Check all scripts' dependencies"/"Check new features are
	configured" are for -- just whether this step has been done once."""
	import importlib.metadata
	try:
		dist = importlib.metadata.distribution("trappyscopes")
		return True, f"installed (v{dist.version})"
	except importlib.metadata.PackageNotFoundError:
		return False, "not installed -- pip install -e . has not been run"


def install():
	from core.installer.installer import Installer
	Installer.do_all()


if __name__ == "__main__":
	install()
