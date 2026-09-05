"""
What each launcher menu item actually does.

Every action here wraps something that already exists elsewhere in the
codebase (expenv.build, Installer, intro(), findexp(), ScriptEngine) rather
than inventing new behaviour -- the menu is a selectable front end onto
functionality core/argparser.py otherwise only exposes as CLI flags you have
to remember (--install, --intro, ...).

Each function is responsible for its own exit/handoff: `boot` and
`open_experiment` end in an interactive console (mirroring `python -i
main.py`); the others print, run to completion, or open an editor, then
return so the process can exit normally.
"""

import os

import __main__


def _enter_console(namespace):
	vars(__main__).update(namespace)
	import code
	code.interact(local=vars(__main__), banner="", exitmsg="")


def boot():
	"""Build the experiment environment and drop into a console with it."""
	from expenv import build
	_enter_console(build())


def open_experiment():
	"""Boot, then immediately open an experiment instead of leaving exp=None."""
	from expenv import build
	namespace = build()
	if namespace.get("findexp"):
		namespace["exp"] = namespace["findexp"]()
	_enter_console(namespace)


def run_script():
	"""Prompt for a script path, queue it, then boot."""
	from prompt_toolkit import prompt
	path = prompt("Script to run on boot: ")
	if not path:
		return
	from expframework.scriptengine import ScriptEngine
	ScriptEngine.execlist.append(path)
	boot()


def install():
	from core.installer.installer import Installer
	Installer.do_all()


def intro():
	from utilities.fluff import intro as show_intro
	show_intro()


def edit_config():
	from core.permaconfig.config import TrappyConfig
	path = None
	for candidate in TrappyConfig.default_paths:
		if os.path.exists(candidate):
			path = candidate
			break
	if path is None:
		print("No trappyconfig.yaml found -- run with --new_config first.")
		return
	os.system(f'{os.environ.get("EDITOR", "vi")} "{path}"')
