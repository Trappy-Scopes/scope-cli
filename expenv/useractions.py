"""
User tools exposed into the experiment environment.

These were `exec()`-ed into the session's globals, which is why several of them
used to reference names (ScopeAssembly, Experiment) they never imported. This
module is now imported normally by the recipe, so it imports what it uses.
"""

import os
from rich import print
from rich.rule import Rule
from time import sleep
from core.permaconfig.sharing import Share
from hive.assembly import ScopeAssembly
import logging as log




### Variables -> mostly constants
vid = "vid"
img = "img"
vidmp4 = "vidmp4"
prev = "preview"
vid_noprev = "vid_noprev"
################


# OK
def clear():
	"""
	Clear screen function.
	"""
	os.system('clear')
	print("You can also use Ctrl+L to clear the screen.", Rule())
	sleep(1)
	os.system('clear')


def capture(action, name, *args, **kwargs):
	"""
	Default capture  -> Should be moved to experiment class. It not wise to 
	acquire without starting an experiment. TODO
	"""
	if not cam.is_open():
		cam.open()
		sleep(1)
	print(f"acq: {name}")
	
	if not action:
		action = "video"
	
	# File  uniqueness check
	if unique_check:
		if exp.active:
			if not exp.unique(name):
				print(f"{Fore.RED}File already exists - ignoring the call.{Fore.RESET}")
				return
	
	# Capture call -------------------------------
	cam.capture(action, name,  *args, **kwargs) #|
	#### -----------------------------------------

	#cam.close()
	
	if exp or exp.active():
		exp.log_event(name)

# Ok
def preview(tsec=30):
	"""
	Start camera preview.
	"""
	cam = ScopeAssembly.current.cam
	
	if cam:
		if not cam.is_open():
			cam.open()
		log.info("Starting camera preview.")
		cam.preview(tsec=tsec)
		log.info("Ending camera preview.")
	else:
		log.error("No camera found.")
			


# Ok
def findexp():
	"""
	Find and load an experiment from the microscope. Only confirms once.
	"""

	print("\n\n")
	print("[bold blue]Find experiment >>> [default]")
	print("Press Ctrl+Z to exit or enter to ignore.")
	from prompt_toolkit import prompt
	from prompt_toolkit.completion import WordCompleter
	from expframework.experiment import Experiment

	expcompleter = WordCompleter(sorted([os.path.basename(exp_) for exp_ in Experiment.list_all()], reverse=True))
	exp_name = prompt('Input the session/experiment name -> ', completer=expcompleter)
	#autocompleter.directory("/Users/byatharth/experiments")
	#exp_name = input("Input the session/experiment name -> ")
	exp_name.strip()


	ScopeAssembly.current.exp = None
	if exp_name:
		ScopeAssembly.current.exp = Experiment(exp_name)
	return Experiment.current


def delexp():
	"""
	Delete an experiment from the microscope. Only confirms once.
	"""
	global exp
	print("\n\n")
	print("[bold red]Delete experiment >>> [default]")
	print("Press Ctrl+Z to exit or enter to ignore.")
	from prompt_toolkit import prompt
	from prompt_toolkit.completion import WordCompleter
	from expframework.experiment import Experiment

	expcompleter = WordCompleter([os.path.basename(exp_) for exp_ in Experiment.list_all()])
	exp_name = prompt('Input the session/experiment name -> ', completer=expcompleter)
	#autocompleter.directory("/Users/byatharth/experiments")
	#exp_name = input("Input the session/experiment name -> ")
	exp_name.strip()


	path = None
	if exp_name:
		if exp_name in Experiment.list_all_pathmap().keys():
			path = Experiment.list_all_pathmap()[exp_name]
		from rich.prompt import Confirm
		confirmdelete = Confirm.ask(f"Delete for sure? : {exp_name}")
		if confirmdelete:
			import shutil
			shutil.rmtree(path)


# Ok
def explorefn(fn):
	"""
	Inspect and print a function/callable.
	"""
	from rich import inspect
	inspect(fn, methods=True, all=True)


