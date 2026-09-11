"""
The trappyscope launcher: two entry points into the same pre-flight
sequence.

	trappyscope             fast track -- runs "launch normally" directly,
	                        no menu, no animation (see fast_track()).
	trappyscope --launcher  the animated menu (see launcher.tui.run_launcher).

The launcher sits above the scope CLI, not inside it: it checks and syncs
configuration and repository status, then hands off control. It never opens
an experiment or runs a script itself -- see launcher/utilities/boot.py,
the one place that responsibility passes to expenv.build() (what
`python -i main.py` already does today).
"""


def fast_track():
	"""
	The bare `trappyscope` path -- exactly the menu's "Launch normally" item,
	reached without the menu.
	"""
	from .utilities import launch_normally
	launch_normally.run()


def run_launcher():
	from .tui import run_launcher as _run_launcher
	_run_launcher()


def main():
	"""
	The `trappyscope` installed console script (see pyproject.toml
	[project.scripts]). Lives here, not in core/ -- this function imports
	expenv/expframework/hive by way of fast_track()/run_launcher(), and core
	must not import upward into them (docs/notes/restructuring.md §2.3).

	core.argparser is imported first because it's the module that actually
	parses sys.argv (a side-effecting import, by existing convention -- see
	core/argparser.py) and some of its flags (--install, --intro, ...) exit()
	before this function would ever branch.
	"""
	import core.argparser  # noqa: F401
	from core.permaconfig.sharing import Share

	if Share.argparse.get("launcher"):
		run_launcher()
	else:
		fast_track()
