"""
AI Generated -- HistoryLoggingConsole, _enable_history(), and
_enable_tab_completion() added by Claude (Anthropic), 2026-09.

The one step that hands off out of the launcher and into the actual scope
CLI. The launcher is a layer above the scope CLI -- it never builds an
experiment environment or runs a script itself; this is where that
responsibility passes to expenv.build() (today's `python -i main.py`
equivalent).
"""

import atexit
import code
import io
import os
import readline
import sys

import __main__

from core.utilities import repl_history

DEFAULT_HISTORY_FILE = os.path.expanduser("~/.trappyscope_history")


class _Tee:
	"""A writable stream that forwards every write to `real` (so the user
	still sees output live on their actual terminal) while also collecting
	a copy in `buf` -- used to capture what a REPL statement printed
	without hiding it from the screen."""

	def __init__(self, real, buf):
		self.real = real
		self.buf = buf

	def write(self, data):
		self.real.write(data)
		self.buf.write(data)
		return len(data)

	def flush(self):
		self.real.flush()


class HistoryLoggingConsole(code.InteractiveConsole):
	"""code.InteractiveConsole that, once utilities.repl_history.enable()
	has been called, logs every completed statement's source and printed
	output (stdout and stderr both -- a raised exception's traceback is
	printed by the base class via stderr, so tee-ing both is what makes
	the "error" case show up in the captured text at all). A no-op check
	per statement when logging is off, so wrapping the console always
	costs nothing when the feature isn't in use.

	runsource() (not runcode()) is the override point: it's the one that
	receives the raw source text rather than a compiled code object, and
	it's called once per input line -- returning True means "incomplete,
	give me more lines" (a multi-line block still being typed), so a
	statement is only logged once it actually completes and runs.
	"""

	def runsource(self, source, filename="<input>", symbol="single"):
		if not repl_history.is_active():
			return super().runsource(source, filename, symbol)

		buf = io.StringIO()
		real_out, real_err = sys.stdout, sys.stderr
		sys.stdout, sys.stderr = _Tee(real_out, buf), _Tee(real_err, buf)
		try:
			more = super().runsource(source, filename, symbol)
		finally:
			sys.stdout, sys.stderr = real_out, real_err

		if not more:
			output = buf.getvalue()
			error = output if "Traceback (most recent call last)" in output else None
			repl_history.log_statement(source, output, error)
		return more


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

	`path` is a parameter, not hardcoded further down, so a caller could
	still point this at somewhere else. In practice the actual
	per-experiment need this was originally left open for -- a record of
	what ran, saved alongside the run it belongs to -- is now met by a
	richer, separate mechanism instead: utilities.repl_history (timestamped,
	structured, captures each statement's output/errors too, not just raw
	command text). This function's own remit stays just what it always
	was -- plain readline history for arrow-key recall across sessions.
	"""
	try:
		if os.path.exists(path):
			readline.read_history_file(path)
	except Exception:
		pass  # a corrupt or unreadable history file must never block boot
	readline.set_history_length(2000)
	atexit.register(readline.write_history_file, path)


def _enable_tab_completion():
	"""Wire up rlcompleter, which does NOT happen on its own here.

	Verified directly (readline.get_completer() is None before this
	runs): CPython's site.py only wires Tab-completion via a
	sys.__interactivehook__ that fires when the interpreter itself was
	started with -i (sys.flags.interactive) -- true for `python -i
	main.py`, never true for trappyscope's console-script entry point,
	regardless of code.interact() making the session look and feel
	interactive afterward. Without this, scope.<Tab> (or anything else)
	does nothing at all -- not a PhysicalObject-specific limitation, a
	missing completer for the whole session.

	Replicates site.py's own register_readline(): importing rlcompleter
	registers a completer bound to __main__'s namespace (looked up fresh
	on every completion, not frozen at import time -- vars(__main__).
	update(namespace) below still takes effect), and the actual key
	bind differs between GNU readline and macOS's libedit, exactly the
	same check site.py itself makes.
	"""
	try:
		import rlcompleter  # noqa: F401 -- importing this registers the completer
	except ImportError:
		return
	readline_doc = getattr(readline, "__doc__", "") or ""
	if "libedit" in readline_doc:
		readline.parse_and_bind("bind ^I rl_complete")
	else:
		readline.parse_and_bind("tab: complete")


def boot():
	"""Build the experiment environment and drop into a console with it."""
	from expenv import build
	namespace = build()

	vars(__main__).update(namespace)
	_enable_history()
	_enable_tab_completion()

	HistoryLoggingConsole(locals=vars(__main__)).interact(banner="", exitmsg="")
