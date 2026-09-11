from rich import print
from rich.rule import Rule
from rich.panel import Panel
from rich.table import Table
import os
from importlib import import_module
from collections.abc import Iterable



from .experiment import Experiment


class ScriptEngine:
	"""
	Scripts execution framework.

	TODO: Importing module fails when an experiment is already loaded. Use `raise_exceptions=False` in that case.

	Payload copying - scipts are copied to the experiemnt/scripts folder.
	Copying is performed:
	1. When experiments are created - all the scripts in the past
	2. With an open experiment: when the script passes the commitment phase, i.e.
	   after its successfully imported and is about to be executed.

	AI Generated -- `symbols`/`loaded` and the tracking in run() below,
	added by Claude (Anthropic), 2026-09. The double import_module()+exec()
	load itself is untouched (that's a separate, bigger, not-yet-approved
	rewrite -- see docs/notes/scripts_measurements_plotting.md §A.1/§A.2);
	these are additive: every script's top-level names still land in the
	same shared `globals_`, deliberately (a later create_exp() replacing
	an earlier one is a feature, not a bug -- see §A.2/§G) -- what's new
	is *visibility* into when that happens, and a live record of what's
	actually loaded right now.
	"""
	execlist = []
	payload = []   ## Of what is copied to the Experiment payload
	modules = []
	symbols = {}   ## AI Generated -- {name: source script path} -- who last defined each top-level name
	loaded = []    ## AI Generated -- [{"path", "description", "roles": {"setup"/"start"/"cleanup": [names]}}]

	def run(globals_, scripts=None, raise_exceptions=False):
		"""Run a list of scripts."""

		if isinstance(scripts, str): ## If a single path is given
			scripts = [scripts]

		if scripts == None:
			scripts = ScriptEngine.execlist

		for script in scripts:
			if not os.path.exists(script):
				print(Panel(f"Script not found: {script}", style="red"))
				if raise_exceptions:
					raise FileNotFoundError
			elif script != None:

				## Import script as a module
				try:
					import_path = script.lstrip(os.sep).replace(".py", "").replace(os.sep, ".")
					script_mod = import_module(import_path)
					ScriptEngine.modules.append(script_mod)
				except Exception as e:
					print(f"Script could not be imported as a module: {script}")
					if raise_exceptions:
						raise e
					else:
						ScriptEngine.modules.append(None)

				## Now execute the script
				if True:
					print('\n', Rule(title=f"Running script: {script}", align="center", style="yellow"))
					description = "No script description."
					if ScriptEngine.modules[-1] is not None:
						if "__description__" in dir(ScriptEngine.modules[-1]):
							description = ScriptEngine.modules[-1].__description__
						print(Panel(description, title="description"))

					## Commitment to execution is performed
					ScriptEngine.payload.append(os.path.abspath(script))
					if Experiment.current:
						Experiment.current.copy_payload([ScriptEngine.payload[-1]])

					## Run the script
					with open(script) as f:
						if Experiment.current:
							Experiment.current.log_event("script_run",
								attribs={"path": script, "description":description})
						## AI Generated -- snapshot before exec, so anything
						## new or reassigned by this script's top-level code
						## can be told apart from what was already there.
						before_ids = {k: id(v) for k, v in globals_.items()}
						try:
							## AI Generated -- compile with the real path
							## instead of bare exec()'s synthetic "<string>"
							## filename: inspect.getsource() (needed by
							## compose_effective_script() above) reads via
							## linecache, which only finds real source for
							## a real, existing file path -- and tracebacks
							## from inside the script now show its actual
							## path/line instead of "<string>" too.
							exec(compile(f.read(), script, "exec"), globals_)
						except KeyboardInterrupt:
							print('\n', Rule(title="Script interrupted!", align="center", style="red"))
							if Experiment.current:
								Experiment.current.log_event("script_interrupted",
									attribs={"path": script})
						ScriptEngine._track_symbols(script, globals_, before_ids)
						ScriptEngine._register_loaded(script, globals_, description)

	def _track_symbols(script, globals_, before_ids):
		"""AI Generated -- for every callable (function/class) this
		script's exec newly introduced or reassigned in globals_, log a
		symbol_redefined event if a *different* prior script had already
		claimed that name -- keeping the override itself (deliberate,
		see the class docstring) but making it visible instead of silent."""
		for name, value in list(globals_.items()):
			if name.startswith("_") or not callable(value):
				continue
			if before_ids.get(name) == id(value):
				continue  # untouched by this script
			prior = ScriptEngine.symbols.get(name)
			if prior is not None and prior != script and Experiment.current is not None:
				Experiment.current.log("symbol_redefined", attribs={
					"name": name, "by": script, "was": prior,
				})
			ScriptEngine.symbols[name] = script

	def _register_loaded(script, globals_, description):
		"""AI Generated -- the live script registry: what's actually
		loaded right now, and which @Script-tagged roles it declared
		(see expframework/script.py). Session-lifetime, not tied to any
		one open Experiment -- a script can be (and often is) loaded
		before an experiment exists at all."""
		roles = {"setup": [], "start": [], "cleanup": []}
		for name, value in globals_.items():
			role = getattr(value, "_script_role", None)
			if role in roles:
				roles[role].append(name)
		ScriptEngine.loaded.append({
			"path": script,
			"description": globals_.get("__description__", description),
			"roles": roles,
		})

	def show_loaded():
		"""AI Generated -- what's actually loaded in this session right
		now, same "print a table" convention as
		utilities.keyboard_shortcuts.show_shortcuts()."""
		table = Table(title="Scripts loaded this session")
		table.add_column("Path", style="cyan")
		table.add_column("Description")
		table.add_column("setup", style="green")
		table.add_column("start", style="green")
		table.add_column("cleanup", style="green")
		for entry in ScriptEngine.loaded:
			table.add_row(
				entry["path"], entry.get("description") or "",
				", ".join(entry["roles"]["setup"]),
				", ".join(entry["roles"]["start"]),
				", ".join(entry["roles"]["cleanup"]),
			)
		print(table)

	def compose_effective_script(globals_, out_path=None):
		"""AI Generated -- the "effective script" compose tool
		(docs/notes/scripts_measurements_plotting.md §A.3b): for every
		name in ScriptEngine.symbols, pulls its real, current source via
		inspect.getsource() -- looked up in `globals_` (the same
		namespace run() executed scripts into, e.g. vars(__main__)) --
		from whichever script last defined it, and concatenates them into
		one literal, standalone file: what was actually callable by the
		end of the session, attributed back to its real origin script,
		rather than requiring someone to read through every loaded script
		by hand to work that out. A read-only report over what already
		happened, not a live feature of running a script -- deliberately
		not wired into run() itself. Writes to `out_path` if given (in
		addition to returning the text), otherwise just returns it."""
		import inspect
		import datetime

		lines = [
			f"# Effective script -- composed {datetime.datetime.now().isoformat(timespec='seconds')}",
			f"# {len(ScriptEngine.symbols)} name(s), from "
			f"{len(set(ScriptEngine.symbols.values()))} loaded script(s).",
			"",
		]
		for name, source_script in ScriptEngine.symbols.items():
			obj = globals_.get(name)
			if obj is None:
				continue
			lines.append(f"# --- {name}  (from {source_script}) ---")
			try:
				lines.append(inspect.getsource(obj))
			except (OSError, TypeError) as e:
				lines.append(f"# <source unavailable: {e}>")
			lines.append("")

		text = "\n".join(lines)
		if out_path:
			with open(out_path, "w") as f:
				f.write(text)
		return text

	def find(globals_):
		""" Find and run scripts."""
		print("\n\n")
		print("[bold blue]Find scripts >>> [default]")
		print("Press Ctrl+Z to exit or enter to ignore.")
		from prompt_toolkit import prompt
		from prompt_toolkit.completion import WordCompleter
		from core.permaconfig.config import TrappyConfig


		## AI Generated -- Load scriptpaths -- Experiment.scripts_dirs is an "expand" field
		## (see README's "Expanded config fields" table): a lab-wide
		## manifest appended via config.config_files should be able to add
		## shared script directories without disturbing this device's own,
		## so this unions across every layered source (TrappyConfig.
		## expanded()) rather than letting the highest-priority source
		## replace the others wholesale.
		all_script_paths = TrappyConfig.current.expanded("Experiment", "scripts_dirs")
		all_script_paths = [os.path.expanduser(path) for path in all_script_paths]
		print("Looking into:", all_script_paths)
		#scriptcompleter = PathCompleter(only_directories=False, 
		#							    get_paths=lambda: all_script_paths, 
		#							    file_filter=lambda file: file.endswith(".py") or os.path.isdir(file), 
		#							    expanduser=True)

		paths = []
		paths = []
		for root in all_script_paths:
			for dirpath, dirnames, filenames in os.walk(root):
			    dirnames[:] = [d for d in dirnames if not d.startswith(".")]
			    paths.append(dirpath)
			    paths += [os.path.join(dirpath, f) for f in filenames]
		paths = [path for path in paths if path.endswith(".py")]



		scriptcompleter = WordCompleter(paths, sentence=True)
		script_name = prompt('Enter script path [ press tab to expand ] -> ', completer=scriptcompleter)
		ScriptEngine.run(globals_, scripts=script_name)
