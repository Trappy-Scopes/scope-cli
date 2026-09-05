"""
The trappyscope launcher: two entry points into the same experiment
environment.

	trappyscope             fast track -- no menu, no animation, straight
	                        through to a booted console (see fast_track()).
	trappyscope --launcher  the animated menu (see launcher.tui.run_launcher).

Neither path yet performs the full boot sequence from
docs/notes/restructuring.md §7.3 (environment activation, config validation,
config-server sync, git-sync) -- those steps aren't built yet. Both currently
do exactly what `python -i main.py` does today: build the experiment
environment and hand it to an interactive console. `run_launcher` additionally
offers a few actions (open a specific experiment, queue a script, install,
show the intro, edit the config) that already existed as core/argparser.py
flags, as selectable menu items instead.
"""

def fast_track():
	"""
	The bare `trappyscope` path: build the experiment environment and drop
	into an interactive console with it. No menu, no animation. Identical to
	the menu's "Boot normally" action -- this *is* that action, just reached
	without the menu.
	"""
	from . import actions
	actions.boot()


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
