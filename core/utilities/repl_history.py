"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

REPL command-history logging: records what was typed at the interactive
prompt and what happened when it ran (its printed output, or the
traceback if it raised), one timestamped YAML document per statement.

Reuses core.permaconfig.yaml_logger's create_yaml_logger()/
close_yaml_logger() -- the same "timestamped YAML stream via a rotating
file handler" this codebase already uses for Experiment's own logs.yaml
-- rather than inventing a second logging mechanism. Routed through a
dedicated "repl_history" logger (not root), so these records never mix
into error_collector or anything else already attached to the root
logger.

Off by default. enable() is an explicit call the user makes any time
during a session -- launcher/utilities/boot.py's HistoryLoggingConsole
always wraps the REPL, but only actually captures anything once enable()
has been called. Requires an open Experiment: the whole point is a
per-run audit trail (what was executed, alongside the run it belongs to),
which isn't meaningful with nowhere to anchor it -- enable() refuses (with
a clear message) rather than falling back to some generic, unscoped
location when nothing is open.
"""

import logging
import os

from core.permaconfig.yaml_logger import create_yaml_logger, close_yaml_logger

_logger = logging.getLogger("repl_history")
_logger.propagate = False  # never bubble into the root logger / error_collector
_logger.setLevel(logging.INFO)
_active_path = None


def enable(path=None):
	"""Start logging every REPL statement from now on. `path` defaults to
	the open experiment's own directory -- refuses if no experiment is
	open and no explicit `path` was given, since there's nothing for the
	log to be "the history of" otherwise. Safe to call again with a new
	path mid-session (e.g. a new experiment opens while logging was
	already on) -- the previous file's handler is cleanly closed first."""
	global _active_path

	if path is None:
		from expframework.experiment import Experiment
		if Experiment.current is None:
			print("REPL history logging needs an open experiment -- "
				  "start one first (e.g. exp = Experiment('name')), or "
				  "pass enable(path=...) explicitly.")
			return
		path = os.path.join(Experiment.current.exp_dir, "repl_history.yaml")
	else:
		path = os.path.expanduser(path)

	if _active_path and _active_path != path:
		disable()

	create_yaml_logger(path, logger=_logger)
	_active_path = path
	print(f"REPL history logging enabled -> {path}")


def disable():
	"""Stop logging. Safe to call even if not currently enabled."""
	global _active_path
	if _active_path:
		close_yaml_logger(_active_path, _logger)
		print(f"REPL history logging disabled ({_active_path})")
	_active_path = None


def is_active():
	return _active_path is not None


## Cap on how much of a statement's captured output actually gets written.
## A command that prints something huge (a big DataFrame, a long-running
## loop's output) would otherwise write a correspondingly huge YAML blob
## per statement -- this keeps each entry bounded to "enough to see what
## happened", not a full transcript, while still recording exactly what
## was actually shown on screen (not some separate, deeper representation
## of the value).
MAX_OUTPUT_CHARS = 4000


def _truncate(text):
	if len(text) <= MAX_OUTPUT_CHARS:
		return text
	omitted = len(text) - MAX_OUTPUT_CHARS
	return text[:MAX_OUTPUT_CHARS] + f"\n...[truncated, {omitted} more characters]"


def log_statement(source, output, error=None):
	"""Record one completed REPL statement. No-op if logging isn't
	enabled -- callers don't need to check is_active() themselves first."""
	if not is_active():
		return
	extra = {"input": source, "output": _truncate(output)}
	if error:
		extra["error"] = _truncate(error)
	_logger.info("repl_statement", extra=extra)


if __name__ == "__main__":
	enable()
	log_statement("1 + 1", "2\n")
	disable()
