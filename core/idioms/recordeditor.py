"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

General-purpose editor for any list of dict-like records that mix
system-computed fields with user-editable ones. Experiment's own event
log and measurement stream are the first two users, but nothing here is
Experiment-specific -- see docs/notes/protocols.md §9 for the survey of
other record collections (measurements, notebook entries, session
history, a PhysicalObject's own fields) this is meant to eventually cover
the same way.

A RecordSet wraps a list *in place* -- no copies -- so editing through it
mutates the same list/dicts the caller already holds. Whatever mechanism
that caller uses to persist that list (Experiment's own @autosave-driven
__save__(), a shelve's .sync(), ...) keeps working unchanged; RecordSet
only needs an optional `on_change` callback to trigger it.

What's editable is declared once, at construction, rather than inferred
from a record's shape -- different record types genuinely mean different
things by "editable":
  - `container_path`: where field writes land inside each record. ()
    (default) edits the record's own top-level keys directly (e.g.
    Measurement's "success" lives at the top level); ("attribs",) edits
    the nested `record["attribs"]` dict instead (e.g. TSEvent-shaped
    events, whose system-computed fields live at the top level and all
    user data lives in "attribs" -- see docs/notes/protocols.md §2.3).
  - `allowed_fields` / `denied_fields`: an allow-list or deny-list of
    field names within that container. Neither given means "anything in
    the container is fair game" -- correct for a container that's
    already entirely user-owned (an event's attribs).
"""

from rich import print
from rich.table import Table


class RecordEditError(Exception):
	pass


class RecordSet:
	def __init__(self, records, container_path=(), allowed_fields=None,
				 denied_fields=None, on_change=None, on_edit=None):
		self._records = records
		self.container_path = tuple(container_path)
		self.allowed_fields = set(allowed_fields) if allowed_fields is not None else None
		self.denied_fields = set(denied_fields) if denied_fields is not None else set()
		self.on_change = on_change  # e.g. Experiment.__save__ -- persist after an edit
		self.on_edit = on_edit      # e.g. Experiment._log_edit -- optional edit-trail hook

	def __len__(self):
		return len(self._records)

	def __iter__(self):
		return iter(self._records)

	def __getitem__(self, index):
		if isinstance(index, slice):
			return RecordSet(self._records[index], self.container_path, self.allowed_fields,
							  self.denied_fields, self.on_change, self.on_edit)
		return self._records[index]

	def _container(self, record):
		node = record
		for key in self.container_path:
			node = node[key]
		return node

	def _check(self, fields):
		if self.allowed_fields is not None:
			illegal = set(fields) - self.allowed_fields
		else:
			illegal = set(fields) & self.denied_fields
		if illegal:
			raise RecordEditError(f"Not editable here: {sorted(illegal)}")

	def edit(self, index, track_history=True, **fields):
		"""Edit one record's fields (validated against allowed_fields/
		denied_fields), optionally recording the change via `on_edit`
		before applying it, then persisting via `on_change`."""
		self._check(fields)
		record = self._records[index]
		container = self._container(record)

		if track_history and self.on_edit:
			changed = {k: {"from": container.get(k), "to": v} for k, v in fields.items()}
			self.on_edit(record, changed)

		container.update(fields)
		if self.on_change:
			self.on_change()
		return record

	def edit_all(self, track_history=True, **fields):
		"""Apply the same field mapping to every record currently in this
		set -- filter() first to scope which records that means."""
		for index in range(len(self._records)):
			self.edit(index, track_history=track_history, **fields)

	def filter(self, **kwargs):
		"""Keep records whose top-level fields match every kwarg exactly.
		A callable value is used as a predicate instead of an equality
		check, for open-ended cases (e.g. `since=lambda dt: dt > cutoff`)."""
		def keep(record):
			for key, want in kwargs.items():
				have = record.get(key)
				matched = want(have) if callable(want) else have == want
				if not matched:
					return False
			return True

		return RecordSet([r for r in self._records if keep(r)], self.container_path,
						  self.allowed_fields, self.denied_fields, self.on_change, self.on_edit)

	def table(self, *fields, page=50, offset=0):
		"""Print a paginated rich.Table over `fields` (top-level record
		keys) -- thousands of records must never mean printing thousands
		of rows at once. Returns how many more records remain past this
		page, so a caller can decide whether to show more."""
		window = self._records[offset:offset + page]
		table = Table(title=f"Records {offset}-{offset + len(window)} of {len(self._records)}")
		for field in fields:
			table.add_column(field)
		for record in window:
			table.add_row(*[str(record.get(field, "")) for field in fields])
		print(table)
		return max(0, len(self._records) - (offset + page))
