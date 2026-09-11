"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

The `@Script` decorator scheme -- see docs/notes/scripts_measurements_plotting.md
§A.5 for the full design record (and §I for why both forms below are
equally first-class, not one a fallback for the other). Two shapes:

    from expframework.script import Script

    Script.describe("What this script does.")   # function-based (the common case)

    @Script.setup
    def create_exp():
        ...

    @Script.start / @Script.cleanup              # tag other lifecycle roles, same way
    ...

    @Script(description="...")                   # class-based (multiple instances)
    class Foo:
        @Script.setup
        def create_exp(self): ...

`__description__` (the old dunder-string convention -- misspelling-prone;
two of this session's own scripts had it as `__decription__` and
ScriptEngine never caught it) is dropped in favor of `Script.describe()` --
a real call, so a typo is an immediate NameError/AttributeError instead of
a silently-ignored wrong variable. `describe()` sets `__description__` in
the *caller's* module namespace under the hood, so today's unmodified
`ScriptEngine.run()` (which already looks for `"__description__" in
dir(module)`) picks it up with no changes needed there -- this file adds
the declarative decorator surface without rewiring ScriptEngine as a side
effect, since that redesign (the auto-run driver, redefinition logging,
the "effective script" manifest) is still a separate, not-yet-built piece
(same doc, §A and §G).

`@Script.setup`/`@Script.start`/`@Script.cleanup`/`@Script.unstructured`
are tagging decorators only, for now -- they mark a function's role
(readable via the `_script_role`/`_script_unstructured` attributes below)
for whenever ScriptEngine's own consumption of these tags is built;
today they are identity decorators with no other runtime effect, so
applying them can't change a script's behavior.
"""

import inspect

_ROLE_ATTR = "_script_role"
_UNSTRUCTURED_ATTR = "_script_unstructured"
_DESCRIPTION_ATTR = "_script_description"


def _tag_role(func, role):
	setattr(func, _ROLE_ATTR, role)
	return func


class Script:
	"""Class decorator -- `@Script(description="...")`. Stores the
	description on the class itself, alongside whatever `@Script.setup`/
	`start`/`cleanup`-tagged methods it defines."""

	def __init__(self, description=None):
		self.description = description

	def __call__(self, cls):
		setattr(cls, _DESCRIPTION_ATTR, self.description)
		return cls

	@staticmethod
	def describe(text):
		"""Function-based scripts: call once at module level in place of
		a `__description__` string. Sets `__description__` in the
		*calling module's* own namespace, so it's found by exactly the
		same lookup ScriptEngine.run() already does -- a real call
		instead of a bare string that can be silently misspelled."""
		caller_globals = inspect.stack()[1].frame.f_globals
		caller_globals["__description__"] = text
		return text

	@staticmethod
	def setup(func):
		"""Tags a function/method as this script's setup step (build the
		experiment, mount devices, ...)."""
		return _tag_role(func, "setup")

	@staticmethod
	def start(func):
		"""Tags a function/method as this script's start step (begin the
		actual run -- scheduling, acquisition, ...)."""
		return _tag_role(func, "start")

	@staticmethod
	def cleanup(func):
		"""Tags a function/method as this script's cleanup step (stop
		jobs, safe-state hardware, save/sync/close)."""
		return _tag_role(func, "cleanup")

	@staticmethod
	def unstructured(obj):
		"""Explicit opt-out: marks a file/class as deliberately not
		following the setup/start/cleanup contract (a plain function
		library, e.g. livetrack.py), rather than just not having gotten
		to it yet."""
		setattr(obj, _UNSTRUCTURED_ATTR, True)
		return obj
