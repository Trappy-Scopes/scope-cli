"""
AI Generated -- rewritten by Claude (Anthropic), 2026-09, from a
CSV-read-modify-rewrite-every-call design to a YAML append-log, reusing
core.permaconfig.yaml_logger's create_yaml_logger() (the same mechanism
already backing logs.yaml/repl_history.yaml/event_edits.yaml) instead of
inventing a fourth. O(1) per registration now, not O(N) (the old version
read and rewrote the entire CSV on every single call). See
docs/notes/scripts_measurements_plotting.md §E.3.

Moved off ~/.trappyscope_registry to trappyverse/state/registry.yaml,
matching core/idioms/deviceregistry.py's sibling device_registry.yaml --
same family, same reasoning (human-inspectable, not a private cache).

migrate_old_csv() is a one-time, explicit migration off the old CSV --
call it by hand once; it is never run automatically.
"""

import csv
import datetime
import logging
import os
import shutil

import yaml
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.pretty import Pretty
from rich.rule import Rule
from rich.table import Table

from core.permaconfig.yaml_logger import create_yaml_logger
from core.idioms.recordeditor import RecordSet

import pandas as pd

_REGISTRY_PATH = os.path.join(os.path.expanduser("~"), "trappyverse", "state", "registry.yaml")
_OLD_CSV_PATH = os.path.join(os.path.expanduser("~"), ".trappyscope_registry")

_logger = logging.getLogger("trappyscope_registry")
_logger.setLevel(logging.INFO)  # else inherits root's WARNING and .info() is dropped
_logger.propagate = False       # never bubble into root / error_collector
_logger_ready = False


def _ensure_logger():
	global _logger_ready
	if not _logger_ready:
		os.makedirs(os.path.dirname(_REGISTRY_PATH), exist_ok=True)
		create_yaml_logger(_REGISTRY_PATH, logger=_logger)
		_logger_ready = True


def _load_all():
	"""Every registered entry, oldest first, as plain dicts. `name` is
	kept out of the raw LogRecord `extra=` (it collides with LogRecord's
	own reserved `name` attribute -- confirmed directly, `extra={"name":...}`
	raises `KeyError: Attempt to overwrite 'name' in LogRecord`), so each
	YAML document nests the real record under one `record:` key instead."""
	if not os.path.exists(_REGISTRY_PATH):
		return []
	entries = []
	with open(_REGISTRY_PATH) as f:
		for doc in yaml.safe_load_all(f):
			if doc and "record" in doc:
				entries.append(doc["record"])
	return entries


def Registry(name, kind, tag=None, dt=None, verbose=True, **extra):
	"""Append one registration. Any extra keyword becomes an additional
	field on the record -- the same "arbitrary extras" flexibility the
	old free function offered via a plain dict literal. `dt`/`verbose`
	are internal knobs for migrate_old_csv() (preserve the real historical
	timestamp; skip printing a panel per migrated row) -- a normal call
	never needs either."""
	_ensure_logger()
	row = {"name": name, "kind": kind,
		   "dt": (dt or datetime.datetime.now()).isoformat(timespec="seconds"), "tag": tag, **extra}
	_logger.info("registered", extra={"record": row})
	if verbose:
		print(Panel(Pretty(row), title="TrappyScope Registry"))
	return row


def find(**kwargs):
	"""Search registered entries by field -- exact match per kwarg, or
	pass a callable for substring/fuzzy matching (e.g.
	find(name=lambda v: "pump" in v.lower())). Built on
	core.idioms.recordeditor.RecordSet, the same tool the event editor
	uses -- no bespoke search logic needed at registry scale (hundreds to
	low-thousands of entries over a scope's lifetime, not millions)."""
	return RecordSet(_load_all()).filter(**kwargs)


def ShowRegistry():
	console = Console()
	entries = _load_all()
	if not entries:
		console.print("[dim]Registry is empty.[/dim]")
		return
	table = Table(title="TrappyScope Registry")
	## Union of every field seen across all entries, not just the first
	## row's keys -- registrations can carry arbitrary extra fields now.
	headers = sorted({key for entry in entries for key in entry.keys()})
	for header in headers:
		table.add_column(header)
	for entry in entries:
		table.add_row(*[str(entry.get(h, "")) for h in headers])
	console.print(table)


def migrate_old_csv():
	"""One-time migration off ~/.trappyscope_registry (the old CSV) --
	call by hand, never automatic. Replays every row through the exact
	same Registry() append path a fresh registration uses (so migrated
	entries have the same shape as if they'd always been written this
	way), preserving each row's real historical timestamp -- verified
	directly against real data that `datetime.fromisoformat()` round-trips
	the old CSV's `str(datetime.now())`-formatted `dt` column cleanly.
	Moves (never deletes) the old file aside once done."""
	if not os.path.exists(_OLD_CSV_PATH):
		return "nothing to migrate -- no old CSV found"
	if os.path.exists(_REGISTRY_PATH):
		return (f"{_REGISTRY_PATH} already exists -- not overwriting; "
				f"move or delete it first if you really want to re-migrate")

	with open(_OLD_CSV_PATH) as f:
		rows = list(csv.DictReader(f))

	for row in rows:
		dt = None
		if row.get("dt"):
			try:
				dt = datetime.datetime.fromisoformat(row["dt"])
			except ValueError:
				dt = None  # keep None (falls back to "now") rather than guess at an unknown format
		Registry(row.get("name"), row.get("kind"), tag=(row.get("tag") or None), dt=dt, verbose=False)

	shutil.move(_OLD_CSV_PATH, _OLD_CSV_PATH + ".migrated")
	return f"migrated {len(rows)} entr{'y' if len(rows) == 1 else 'ies'} -> {_REGISTRY_PATH}; old file moved to {_OLD_CSV_PATH}.migrated"


class Reg:
	"""The older, interactive-picker half of this module -- kept
	alongside find()/Registry()/ShowRegistry() above rather than merged
	into them, since Reg.search()'s prompt_toolkit fuzzy picker is a
	genuinely different use case (an interactive pick-one UI) from a
	programmatic find(). Reg.registry stays a pandas DataFrame, same as
	before, just built from the new YAML source instead of pd.read_csv --
	Reg.search() below is unchanged."""
	registry = None

	def load():
		Reg.registry = pd.DataFrame(_load_all())
		if Reg.registry.empty:
			Reg.registry = pd.DataFrame(columns=["name", "kind", "dt", "tag"])

	def search():
		from prompt_toolkit import prompt
		from prompt_toolkit.completion import WordCompleter
		from prompt_toolkit.shortcuts import CompleteStyle
		from prompt_toolkit.validation import Validator
		from colorama import Fore
		escape_validation = False
		def is_valid_uid(text):
			if text == "":
				## return true
				escape_validation = True
				return True
			return text in Reg.registry.name.to_numpy()

		validator = Validator.from_callable(
			is_valid_uid,
			error_message='Object id is not present in the registry!',
			move_cursor_to_end=False)

		all_objects = WordCompleter(Reg.registry.name)
		print("[red](press enter to abort search)[default]")
		obj_name = prompt('Enter registry id -> ', completer=all_objects, \
						  complete_style=CompleteStyle.MULTI_COLUMN, validator=validator)
		if obj_name != None and obj_name != "":
			print(Rule("Search successfull!", style="green"))
			partial_df = Reg.registry[Reg.registry['name'] == obj_name]
			result = partial_df.iloc[0]
			print(Panel(Pretty(result.to_dict()), title=obj_name))
			return str(obj_name)
		else:
			print(Rule("Search un-successfull!", style="red"))
			return None
