import os
import confuse
import logging
from copy import deepcopy
from rich import print
from rich.console import Console
from rich.panel import Panel
from rich.live import Live
from rich.text import Text
import logging as log
import shutil
import time

from core.utilities import fluff
from ..exceptions import TS_ConfigNotFound


class TrappyConfig(confuse.Configuration):
	"""
	Trappy-Scopes configuration system.



	"""


	## current instance
	current = None

	## Config must be present at these two paths in the order of preference
	default_paths = [os.path.join(os.path.expanduser("~"), "trappyverse", "trappyconfig.yaml"),
					 os.path.join(os.path.expanduser("~"), "trappyconfig.yaml"),]


	def __init__(self, file=None):
		"""
		Initalize the configuration and configure the terminal environment for use.
		"""
		super().__init__('trappyscopes', __name__)

		## Read configuration file
		found = False
		if file is  None:
			for file_ in TrappyConfig.default_paths:
				if os.path.exists(file_):
					found = True
					file = file_
					print(f"[green][OK] [bold cyan]Trappy-Scopes[default] config set: {file}")
					break
			if not found:
				raise TS_ConfigNotFound("Config file not found.")
		
		source = confuse.YamlSource(os.path.join(os.path.dirname(__file__), "default_config.yaml"))
		self.add(source)
		self.set_file(file)
		self.loaded_from = file  # AI Generated

		## Load all other configuration files
		all_config_files = self["config"]["config_files"].get()
		for file in all_config_files:
			source = confuse.YamlSource(file)
			self.set(source)


		## Configure logger
		try:
			from ..permaconfig import loggersettings
			logger = logging.getLogger()
			logger.setLevel(self["config"]["log_level"].get())  # or any level you need
			logger.addHandler(loggersettings.error_collector)
		except Exception as e:
			print(e)
			print(f"[red][NOK] [bold cyan]Trappy-Scopes[default] config: Logger configuration failed. Try importing core.permaconfig.loggersettings as it is.")
		

		## Configure rich
		try:
			from ..permaconfig import richsettings
		except Exception as e:
			print(e)
			print(f"[red][NOK] [bold cyan]Trappy-Scopes[default] config: rich configuration failed. Try importing core.permaconfig.richsettings as it is.")

		## Singelton template
		TrappyConfig.current = self


	def new_config(self, filename=None):
		"""Write a new configuration file with the given name.
		   TODO: default scopename should be the hostname of the device."""
		
		if filename is None:
			filename = os.path.join(os.path.expanduser("~"), "trappyverse", "trappyconfig.yaml")
		if os.path.exists(filename):
			raise IOError("File already exists. This operation is not allowed.")
		os.makedirs(os.path.dirname(filename), exist_ok=True)
		shutil.copy(os.path.join(os.path.dirname(__file__), "default_config.yaml"), filename)

		def render(i):
			colors = ["red", "green", "blue", "white"]
			return Text(fluff.pageheader_plain(), style=colors[i], justify="center")
		
		with Live(render(0), screen=True) as live:
			for i in range(1, 4):
				time.sleep(1)
				live.update(render(i))
		time.sleep(0.5)
		print(Panel(f"{render(3)}\n[bold]Config path: {filename}", title="New configuration"))
	

	## AI Generated -- leaf()/expanded() below, added by Claude (Anthropic)
	## to fix a real confuse merge-semantics bug (an eager .get() above a
	## leaf silently collapses every layered config_files source down to
	## one). See README's "Layering additional configuration files"
	## section.
	def leaf(self, *path):
		"""
		Resolve `path` to a single scalar/dict/list value the correct way:
		bracket-chained all the way down before calling .get(), so confuse
		does its real per-key fallback across every layered source
		(self.sources -- the primary file plus each config.config_files
		entry, highest-priority last-added) at that exact path, rather
		than one source wholesale-replacing the others.

		This is NOT the same as calling .get() partway down and indexing
		into a plain dict afterward (config.get()["config"]["expdir"], or
		worse config.get()) -- verified directly against confuse: calling
		.get() on anything above the actual leaf collapses every source
		down to whichever one has highest priority AT THAT PATH, silently
		dropping every sibling key the other sources declared alongside
		it. leaf() exists so call sites can't make that mistake by hand.

		Only correct for fields meant to behave as "the most specific
		declaration wins" (almost everything). A field meant to combine
		declarations from multiple sources instead (git_dependencies,
		Experiment.scripts_dirs -- see README's "Expanded config fields"
		table) must use expanded(), not this.
		"""
		node = self
		for key in path:
			node = node[key]
		return node.get()

	def expanded(self, *path):
		"""
		Union `path`'s value across every layered source instead of
		letting the highest-priority one replace the rest -- confuse has
		no such mechanism itself, even via correct leaf-chained access
		(verified directly: bracket-chaining all the way to a dict- or
		list-valued key still only returns one source's value, wholesale).
		This walks self.sources by hand -- each one is directly
		dict-subscriptable -- and combines what it finds:
		  - dict-valued: merged key by key, lower-priority sources first,
		    so a key declared in only one source survives, and a key
		    declared in several resolves to the highest-priority source's
		    value (same rule as leaf(), just applied per-key instead of
		    to the whole dict).
		  - list-valued: concatenated in low-to-high priority order,
		    de-duplicated by first occurrence.
		Returns {} if no source declares `path` at all.

		Only call this for a field explicitly documented as "expand"
		semantics in the README's "Expanded config fields" table -- every
		other field should use leaf(). Whether a field expands or
		overrides is a decision about what that field *means*, which
		confuse (and this method) has no way to infer from its shape
		alone -- a list can just as easily mean "this device's own value,
		full stop" (e.g. Experiment.exp_dir_structure) as "combine across
		every layered source" (Experiment.scripts_dirs).
		"""
		combined = None
		for source in reversed(self.sources):
			node = source
			try:
				for key in path:
					node = node[key]
			except (KeyError, TypeError):
				continue

			if isinstance(node, dict):
				combined = dict(combined or {})
				combined.update(node)
			elif isinstance(node, list):
				combined = list(combined or [])
				for item in node:
					if item not in combined:
						combined.append(item)
			else:
				combined = node  # not a composite value -- highest priority just wins
		return combined if combined is not None else {}

	## AI Generated -- template()/leaf_templated()/TEMPLATE_VARS below,
	## added by Claude (Anthropic), centralizing what used to be
	## expframework.expsync.ExpSync's own private, inline effify() (used
	## only for file_server.destination). See
	## docs/notes/scripts_measurements_plotting.md §G.10.
	TEMPLATE_VARS = ("scopeid", "date", "time", "user")

	def template(self, raw):
		"""Evaluate `raw` as an f-string template against exactly the
		four known context vars in TEMPLATE_VARS -- for a caller that
		already has the raw template string (e.g. ExpSync, which cached
		it at configure() time) and just needs it evaluated, without a
		fresh config lookup. leaf_templated() below is the "look it up
		and evaluate it" convenience on top of this.

		Sanitized deliberately: evaluated against a namespace containing
		ONLY those four names -- never the caller's own locals()/
		globals() -- plus an empty __builtins__, so a rogue template
		can't reach a builtin function (e.g. {__import__('os')...}) even
		inside that otherwise-restricted namespace. Any other name
		referenced in the template is a clean NameError, not a silent
		security hole.
		"""
		if not isinstance(raw, str):
			return raw

		from core.permaconfig.sharing import Share
		from core.bookkeeping.user import User

		context = {
			"scopeid": Share.scopeid,
			"date": Share.get_date_str(),
			"time": Share.get_time_str(),
			"user": User.name(),
			"__builtins__": {},
		}
		return eval(f'f"""{raw}"""', context)

	def leaf_templated(self, *path):
		"""template(leaf(*path)) -- opt-in per call site (not automatic
		on every leaf() call), since plenty of config strings legitimately
		contain "{"/"}" without meaning to be templates."""
		return self.template(self.leaf(*path))

	@staticmethod
	def optional_block(config_dict, *path):
		"""
		Walk `path` through an already-materialised config dict (e.g. from
		`TrappyConfig().get()`) and return whatever is found there, or None if
		any step is missing, or if what's found is a block that declares
		`active: false`. Absence and explicit deactivation are the same
		signal to a consumer: don't run this feature.

		Only meaningful for the `active:`-flagged block shape (venv,
		file_server, config_server, ...). A bare boolean gate like the
		current `git_sync` is a different shape and isn't affected by this --
		a non-dict value found at `path` is returned as-is.
		"""
		node = config_dict
		for key in path:
			if not isinstance(node, dict) or key not in node:
				return None
			node = node[key]
		if isinstance(node, dict) and node.get("active") is False:
			return None
		return node

	def panel(self):
		"""
		Draw a panel with all the nested configuration.
		"""
		from rich.pretty import Pretty
		from rich.panel import Panel
		from rich.tree import Tree
		from collections import OrderedDict

		def dict_to_tree(d, tree=None):
			if tree is None:
				tree = Tree("root")
			for key, value in d.items():
				if isinstance(value, dict) or isinstance(value, OrderedDict):
					branch = tree.add(f"[bold]{key}[/bold]")
					dict_to_tree(value, branch)
				else:
					tree.add(f"[bold]{key}[/bold]: {value}")
			return tree

		devicepanel = Panel(dict_to_tree(self.get()), title="Device")
		print(devicepanel)

