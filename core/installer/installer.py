import subprocess
import sys

from core.installer import environment


class Installer:
	"""
	The one real entry point is do_all(). No dependency is declared here --
	binary or Python -- by design (see docs/notes/restructuring.md): this
	module only orchestrates, everything it installs comes from
	pyproject.toml, bootstrap-requirements.txt, or hardware-profiles/*/.

	Previously declared its own pylibs/binlibs lists (a second, drifting
	copy of what pyproject.toml already declared) and ran `pip install .`
	(non-editable) here -- the exact bug that silently replaced a working
	editable dev install and broke `trappyscope` itself. Both removed.
	"""

	def do_all():
		"""
		Reinstall trappyscopes as an editable package, then hand off to
		core.installer.environment for everything else (uv, PEP 668/venv,
		hardware-profile discovery and sync).
		"""
		print("Installing trappyscopes (editable)...")
		result = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."],
								 check=False)
		if result.returncode != 0:
			print("pip install -e . failed -- stopping before touching hardware profiles.")
			return

		environment.ensure()
