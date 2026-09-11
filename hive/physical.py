import ast
import os
import shelve

from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app
from prompt_toolkit.cursor_shapes import CursorShape
from prompt_toolkit.key_binding.bindings.focus import focus_next, focus_previous
from prompt_toolkit.key_binding.defaults import load_key_bindings
from prompt_toolkit.key_binding.key_bindings import KeyBindings, merge_key_bindings
from prompt_toolkit.layout import Layout
from prompt_toolkit.layout.containers import HSplit, VSplit
from prompt_toolkit.widgets import Button, Dialog, Label, TextArea

from rich.console import Console
from rich.panel import Panel


class PhysicalObject(object):
	"""
	Metadata structure representing a physical object.
	"""

	def __init__(self, name, persistent=False, **kwargs):
		self.attribs = kwargs
		self.attribs["name"] = name
		self.persistent = persistent
		self.params = self.attribs  ## Aliased

		if persistent:
			## Lives under trappyverse/ (not directly in the home directory) so
			## that syncing the trappyverse folder to the config server (see
			## docs/notes/restructuring.md §7.2) actually backs this up. Moved
			## 2026-09-05 -- a shelve from before this change, sitting at
			## ~/<name>, is not picked up automatically; move it by hand under
			## trappyverse/state/ if it needs to survive.
			statedir = os.path.join(os.path.expanduser("~"), "trappyverse", "state")
			os.makedirs(statedir, exist_ok=True)
			state = shelve.open(os.path.join(statedir, name))

			## Current should override state
			for key, value in self.attribs.items():
				state[key] = value

			self.attribs = state
			self.params = self.attribs  ## Re-alias to the shelve-backed store

		if not "kind" in self.attribs:
			self.attribs["kind"] = "hive.PhysicalObject"

	def __getstate__(self):
		return {key: value for key, value in self.attribs.items()}

	def __close__(self):
		if self.persistent:
			self.attribs.sync()
			self.attribs.close()

	def __repr__(self):
		n = 3
		preview = list(self.attribs.items())[:n]
		preview_repr = ", ".join(f"{k!r}: {v!r}" for k, v in preview)
		suffix = "..." if len(self.attribs) > n else ""
		return f"< PhysicalObject{'-persistent' * self.persistent} :: {preview_repr}{suffix} >"

	def show(self):
		"""
		Pretty-print every field of this object as a rich.Panel.
		"""
		body = "\n".join(
			f"[bold cyan]{key}[/bold cyan] = [white]{value!r}[/white]"
			for key, value in self.attribs.items()
		)

		title = f"PhysicalObject{' · persistent' if self.persistent else ''}"
		panel = Panel(
			body,
			title=title,
			title_align="left",
			border_style="green" if self.persistent else "cyan",
			expand=False,
		)

		Console().print(panel)

	def __getitem__(self, key):
		return self.attribs[key]

	def __setitem__(self, key, value):
		self.attribs[key] = value

	@staticmethod
	def _parse_value(raw):
		"""
		Try to interpret user input as a Python literal (int, float, bool,
		list, dict, ...). Falls back to the raw string if that fails, so
		plain text like a motor's name still works.
		"""
		try:
			return ast.literal_eval(raw)
		except (ValueError, SyntaxError):
			return raw

	def update(self, new_field_slots=3):
		"""
		Edit this object's fields in a bordered dialog box — the same
		`Dialog` widget that backs prompt_toolkit's built-in
		input_dialog / message_dialog / etc. (see
		https://python-prompt-toolkit.readthedocs.io/en/stable/pages/dialogs.html),
		rather than a bare full-screen form.

		Every field shows up at once, pre-filled and directly editable.
		Tab / Shift+Tab (or click, thanks to mouse support) move between
		fields. Clear a value entirely and press Save to delete that
		field. A few blank rows at the bottom let you add new fields
		(fill in both the name and the value). 'kind' is shown for
		reference but is immutable — it has no input box here.

		Press Save to apply changes, or Cancel to discard them.

		If this object is persistent, changes are synced to disk
		automatically after a successful save.
		"""
		editable_keys = [key for key in self.attribs.keys() if key != "kind"]
		label_width = max([len(key) for key in self.attribs.keys()] + [8]) + 2

		field_areas = {}
		rows = []

		if "kind" in self.attribs:
			rows.append(VSplit([
				Label(text=f"{'kind':<{label_width}}", width=label_width),
				Label(text=f"{self.attribs['kind']!s}  (immutable)"),
			]))

		for key in editable_keys:
			area = TextArea(text=str(self.attribs[key]), multiline=False)
			field_areas[key] = area
			rows.append(VSplit([
				Label(text=f"{key:<{label_width}}", width=label_width),
				area,
			]))

		rows.append(Label(text=""))
		rows.append(Label(text="Add new fields:"))

		new_rows = []
		for _ in range(new_field_slots):
			key_area = TextArea(text="", multiline=False)
			val_area = TextArea(text="", multiline=False)
			new_rows.append((key_area, val_area))
			rows.append(VSplit([
				key_area,
				Label(text=" = ", width=3),
				val_area,
			]))

		result = {"saved": False}

		def save_handler():
			result["saved"] = True
			get_app().exit()

		def cancel_handler():
			result["saved"] = False
			get_app().exit()

		dialog = Dialog(
			title=f"Update {self.attribs.get('name', 'PhysicalObject')}",
			body=HSplit(rows, padding=0),
			buttons=[
				Button(text="Save", handler=save_handler),
				Button(text="Cancel", handler=cancel_handler),
			],
			with_background=True,
		)

		bindings = KeyBindings()
		bindings.add("tab")(focus_next)
		bindings.add("s-tab")(focus_previous)

		app = Application(
			layout=Layout(dialog),
			key_bindings=merge_key_bindings([load_key_bindings(), bindings]),
			mouse_support=True,
			full_screen=True,
			cursor=CursorShape.BLINKING_BLOCK,
		)
		app.run()

		if not result["saved"]:
			return

		for key, area in field_areas.items():
			raw = area.text
			if raw.strip() == "":
				del self.attribs[key]
			else:
				self.attribs[key] = self._parse_value(raw)

		for key_area, val_area in new_rows:
			new_key = key_area.text.strip()
			if new_key:
				self.attribs[new_key] = self._parse_value(val_area.text)

		if self.persistent:
			self.attribs.sync()