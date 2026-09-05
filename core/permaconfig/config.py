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

from utilities import fluff
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

