"""
The interactive launcher: `trappyscope --launcher`.

A prompt_toolkit full-screen app. The chlamy_dance animation loops
continuously in the top pane while a selectable menu sits below it, and
neither is written from scratch: chlamy_dance.render() already emits raw
24-bit ANSI escapes, and prompt_toolkit's `ANSI()` helper parses that
directly, so embedding the animation needed no changes to it at all.

The menu is a small hand-rolled control rather than prompt_toolkit's
RadioList widget, on purpose: RadioList binds Enter/Space internally to mean
"select this item", and composing that cleanly with an app-level "confirm
and exit" binding on the same key is exactly the kind of thing that's easy
to get subtly wrong. A menu this size (six items, up/down/enter/quit) is
less code to hand-roll than to verify against a widget's internal bindings.
"""

import time

from prompt_toolkit.application import Application
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.layout import HSplit, Layout, Window
from prompt_toolkit.layout.controls import FormattedTextControl
from prompt_toolkit.widgets import Frame

from . import chlamy_dance as dance

FPS = 20

MENU_ITEMS = [
	("boot", "Boot normally"),
	("open_experiment", "Open an existing experiment"),
	("run_script", "Run a script"),
	("install", "Install / setup"),
	("intro", "Show the introduction"),
	("edit_config", "Edit the configuration file"),
]

ACTIONS = {
	"boot": "boot",
	"open_experiment": "open_experiment",
	"run_script": "run_script",
	"install": "install",
	"intro": "intro",
	"edit_config": "edit_config",
}


class Menu:
	"""Selection state for a simple up/down/enter menu. No widget, no magic."""

	def __init__(self, items):
		self.items = items
		self.index = 0

	@property
	def selected_key(self):
		return self.items[self.index][0]

	def up(self):
		self.index = (self.index - 1) % len(self.items)

	def down(self):
		self.index = (self.index + 1) % len(self.items)

	def text(self):
		fragments = []
		for i, (_, label) in enumerate(self.items):
			style = "reverse" if i == self.index else ""
			prefix = "> " if i == self.index else "  "
			fragments.append((style, f"{prefix}{label}\n"))
		return fragments


def _build_app(menu, animation_text, input=None, output=None):
	kb = KeyBindings()

	@kb.add("up")
	def _(event):
		menu.up()

	@kb.add("down")
	def _(event):
		menu.down()

	@kb.add("enter")
	def _(event):
		event.app.exit(result=menu.selected_key)

	@kb.add("c-c")
	@kb.add("q")
	def _(event):
		event.app.exit(result=None)

	animation = Window(content=FormattedTextControl(animation_text), height=dance.H)
	menu_window = Window(content=FormattedTextControl(menu.text))
	root = HSplit([Frame(animation, title="Trappy-Scopes"), Frame(menu_window)])

	return Application(
		layout=Layout(root),
		key_bindings=kb,
		full_screen=True,
		refresh_interval=1 / FPS,
		input=input,
		output=output,
	)


def run_launcher():
	"""
	Show the animated menu and run whichever action was chosen (or nothing,
	if cancelled). Each action is responsible for its own exit/handoff.
	"""
	start = time.monotonic()

	def animation_text():
		t = (time.monotonic() - start) % dance.DURATION
		return ANSI(dance.render(dance.frame(t)))

	menu = Menu(MENU_ITEMS)
	app = _build_app(menu, animation_text)
	choice = app.run()

	if choice is None:
		return
	from . import actions
	getattr(actions, ACTIONS[choice])()
