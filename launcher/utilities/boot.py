"""
The one step that hands off out of the launcher and into the actual scope
CLI. The launcher is a layer above the scope CLI -- it never builds an
experiment environment or runs a script itself; this is where that
responsibility passes to expenv.build() (today's `python -i main.py`
equivalent).
"""

import atexit
import os
import readline

import __main__

DEFAULT_HISTORY_FILE = os.path.expanduser("~/.trappyscope_history")


def _enable_history(path=DEFAULT_HISTORY_FILE):
	"""
	Load persistent readline history from `path` (if it exists), and save
	back to it when the process exits.

	code.interact() does not do this on its own -- unlike `python -i`,
	where the interpreter's own top-level interactive loop gets automatic
	history-file load/save for free from a site.py startup hook,
	code.interact() runs its own independent prompt loop that was never
	wired to any file, in either the old (`python -i main.py`) code or
	this one. Within one session, up/down-arrow recall already worked
	(readline is imported, so the builtin input() picks it up regardless);
	what was actually missing is history surviving between runs.

	`path` is a parameter, not hardcoded further down, on purpose: the
	plan is for a per-experiment history file (one saved alongside the run
	it belongs to, inside that experiment's own directory) once an
	experiment is open, rather than only this one global fallback. This
	function is the point that future work should call again with that
	path once it exists -- readline.read_history_file/write_history_file
	both accept being pointed at a new file mid-session.
	"""
	try:
		if os.path.exists(path):
			readline.read_history_file(path)
	except Exception:
		pass  # a corrupt or unreadable history file must never block boot
	readline.set_history_length(2000)
	atexit.register(readline.write_history_file, path)


def boot():
	"""Build the experiment environment and drop into a console with it."""
	from expenv import build
	namespace = build()

	vars(__main__).update(namespace)
	_enable_history()

	import code
	code.interact(local=vars(__main__), banner="", exitmsg="")
