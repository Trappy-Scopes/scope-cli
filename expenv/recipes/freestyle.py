"""
The `freestyle` experiment environment.

The full setup, and the default: parse arguments, condition the machine, build
the ScopeAssembly, expose the standard object names (`scope`, `exp`, `lab`,
...) and the user tools, then run any startup scripts. This is the environment
for freestyling experiments at the prompt.

	|- 1. Parse arguments that enable special features (installer, uid generation, etc).
	|- 2. Condition machine - set up console and logging operations.
	|- 3. Set-up a ScopeAssembly object on the machine - the virtual microscope object.
	|- 4. Expose standard object names for user convenience (exp, cam, lit, pico, etc).
	|- 5. Run the user-defined experimental script in the Experiment-Orchestration-Engine.
	|- 6. Expose higher order functions for user convenience (capture(), delexp(), findexp(), etc).
	*

This was `core/startup/__init__.py`, which was `exec()`-ed into main.py's
globals. It is now a function returning a namespace; see expenv/__init__.py
for why.
"""

import os
import logging
import readline

import yaml
from yaml.loader import SafeLoader

from rich import print
from rich.align import Align
from rich.markdown import Markdown
from rich.panel import Panel
from rich.pretty import Pretty
from rich.rule import Rule
from rich.table import Table
import rich.box as box

## Importing the argparser parses sys.argv and handles the early-exit flags
## (--intro, --install, --uid, ...). It is imported for those side effects; the
## values it parsed are read off Share.argparse below.
import core.argparser  # noqa: F401
from core.permaconfig.sharing import Share

from core.bookkeeping.user import User
from core.bookkeeping.session import Session
from core.bookkeeping.yamlprotocol import YamlProtocol
from core.bookkeeping.registry import Reg
from core.permaconfig import loggersettings
from core.installer.installer import Installer

from expframework.experiment import Experiment
from expframework.protocol import Protocol
from expframework.expsync import ExpSync
from expframework.scriptengine import ScriptEngine
from expframework.plotter import Plotter as plt

from hive.assembly import ScopeAssembly
from hive.rpycserver import RpycServer
from hive.laboratory import Lab
from hive.processorgroups.micropython import SerialMPDevice

from core.utilities.fluff import pageheader, intro
from core.utilities.codeviewer import codeviewer
from core.utilities.keyboard_shortcuts import bind_all
from core.utilities.repl_history import enable as enable_history_logging, disable as disable_history_logging

from .. import useractions


def build(config):
	"""
	Build the freestyle environment and return its namespace.
	"""
	device_metadata = config

	## Define exp - for crash safety. Scripts and tools rebind it.
	exp = None

	## Login and session ------------------------------------------------
	User.login(Share.argparse["user"])
	session = Session()
	User.exp_hook = exp

	og_directory = os.getcwd()

	## Device ID and metadata --------------------------------------------
	## Wallpaper generation now happens at the launcher level (see
	## launcher/utilities/launch_normally.py) -- it reads config the same
	## way the launcher's other pre-flight steps do, before this recipe
	## (or any other startup_recipie) ever runs.
	scopeid = device_metadata["name"]
	Share.scopeid = scopeid

	SerialMPDevice.print_all_ports()

	## Draw page header ---------------------------------------------------
	for i in range(1, 5):
		print(Rule(characters='═', style=f"rgb(0,{51*i},{51*i})"),  end='')
	print("\n")
	print(Align.center(pageheader()))
	for i in range(1, 6):
		print(Rule(characters='═', style=f"rgb(0,{int(255/i)},{int(255/i)})"),  end='')

	## Draw ScopeAssembly --------------------------------------------------
	scope = ScopeAssembly(scopeid)
	server = RpycServer()
	RpycServer.roll["scope"] = scope
	scope.open(device_metadata, abstraction="microscope")
	for i in range(1, 5):
		print(Rule(characters='═', style=f"rgb({51*i},{51*i},0)"),  end='')
	scope.draw_tree()
	for i in range(1, 5):
		print(Rule(characters='═', style=f"rgb({int(255/i)},{int(255/i)},0)"),  end='')

	## Bind keyboard shortcuts -- config.keyboard_shortcuts (inline/file),
	## scope devices (e.g. Esc, s, n -> scope.node), and the Experiment
	## member table, per config.keyboard_shortcuts.{scope_assembly,experiment}.
	bind_all(scope, config)

	## List experiments ----------------------------------------------------
	exppanel = Table("#.", "EID", "Experiment", box=False, show_lines=True, title_style="blink2")
	expmap = Experiment.list_all_eids()
	for i, key in enumerate(expmap):
		exppanel.add_row(str(i), key, expmap[key])
	for i in range(1, 5):
		print(Rule(characters='═', style=f"rgb({51*i},{51*i},{51*i})"),  end='')
	print(Panel(exppanel, title="All current experiments on the Microscope", style="white"))
	for i in range(1, 6):
		print(Rule(characters='═', style=f"rgb({int(255/i)},{int(255/i)},{int(255/i)})"),  end='')

	## Summary of errors ---------------------------------------------------
	for i in range(1, 4):
		print(Rule(characters='═', style=f"rgb({int(51*i)},0,0)"),  end='')
	print(Rule(title="Summary of errors", characters='═', style=f"rgb({int(51*5)},0,0)"),  end='')
	print(loggersettings.error_collector.summarize_errors())
	print(Rule(characters='═', style=f"rgb({int(51*5)},0,0)"),  end='')
	for i in range(1, 5):
		print(Rule(characters='═', style=f"rgb({int(255/i)},0,0)"),  end='')
	print("\n")

	print("\nCall intro() to get an introduction.")

	ExpSync.configure(device_metadata)

	if scopeid == "MDev":
		Reg.load()

	lab = Lab()

	print("Use `exp = findexp()` to search for an old experiment.")
	print("Use `exp = Experiment('new_name')` to create a new experiment.")

	## Collect the namespace ------------------------------------------------
	## Everything bound above becomes a top-level name in the session, plus the
	## user tools (findexp, delexp, clear, preview, ...) from expenv.useractions.
	namespace = {k: v for k, v in locals().items() if not k.startswith("_")}
	namespace.update({
		k: v for k, v in vars(useractions).items() if not k.startswith("_")
	})
	## AI Generated -- enable_history_logging/disable_history_logging are module-level
	## imports here (not locals of build()), so the locals() sweep above
	## doesn't pick them up on its own -- added explicitly so a user can
	## call enable_history_logging() directly at the REPL (see
	## utilities.repl_history and Esc,e,l in keyboard_shortcuts.py).
	namespace["enable_history_logging"] = enable_history_logging
	namespace["disable_history_logging"] = disable_history_logging

	## Scripts must run as if they were the main program, so their
	## `if __name__ == "__main__":` blocks fire. When startup was exec()-ed,
	## ScriptEngine received main.py's globals, which carried these dunders;
	## a freshly built dict does not. The failure is silent rather than loud:
	## with `__name__` absent from globals the lookup falls through to
	## builtins, where `__name__` is "builtins", so the guard is just quietly
	## False. `__file__` is main.py's path, not the script's -- scripts like
	## scripts/alignmenttools/framealignment.py build paths assuming that.
	import __main__
	namespace["__name__"] = "__main__"
	namespace["__file__"] = getattr(__main__, "__file__", "main.py")

	## Run startup scripts ---------------------------------------------------
	## CLI scripts first (recorded by core.argparser), then the ones named in
	## the configuration. Scripts run against the namespace we just built, so
	## they see `scope`, `exp` and the tools without importing anything.
	ScriptEngine.execlist = list(Share.argparse.get("scriptlist", []))
	if device_metadata["config"].get("startup_scripts"):
		ScriptEngine.execlist += device_metadata["config"]["startup_scripts"]
	if ScriptEngine.execlist:
		ScriptEngine.run(namespace)

	Share.updateps1()
	return namespace
