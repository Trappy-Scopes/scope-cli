"""
General machine introspection. Scope is `os`/`board`/`cpu`/`memory`/
`storage`, kept extensible by registering more facts rather than growing
one function. CPU/RAM/storage were originally considered and dropped as
not needed for hardware-profile selection (still their only consumer
inside core.installer.environment) -- added back once the device tree
(launcher/utilities/device_tree.py) needed somewhere to source them for
its system-state line.

Not a duplicate of core/bookkeeping/systeminfo.py: that module records
narrow *identity* facts (MAC address, hostname) for experiment provenance.
This one answers "what kind of machine is this," for anything that needs
to branch on it or display it.

`board` recognises only the two natively-known cases (Raspberry Pi,
Jetson) plus a generic fallback. It is deliberately *not* the full
hardware-profile scanner -- that walks native/external/machine-local
profile directories with precedence and reads each one's own `profile.yaml`
`detect:` command, and lives in core/installer/environment.py, which calls
`collect("board")` as one input among others (including profiles this
module has no knowledge of).

cpu/memory/storage use psutil rather than hand-rolled per-OS parsing (the
`/sys`, `/proc`, `system_profiler` style used in devicetree.py) -- psutil
already is the one library that reports this uniformly across Windows/
Mac/Linux, so there's no OS-branching reason to write it by hand here.
"""

import os
import platform as _platform

import psutil

_FACTS = {}


def fact(name):
	"""Decorator: register a function as a system fact under `name`."""
	def decorator(fn):
		_FACTS[name] = fn
		return fn
	return decorator


@fact("os")
def _os():
	return {
		"system": _platform.system(),
		"release": _platform.release(),
		"machine": _platform.machine(),
	}


@fact("board")
def _board():
	"""raspberrypi / jetson / generic."""
	if _platform.system() != "Linux":
		return "generic"

	try:
		with open("/proc/device-tree/model") as f:
			if "Raspberry Pi" in f.read():
				return "raspberrypi"
	except (FileNotFoundError, PermissionError):
		pass

	if os.path.exists("/etc/nv_tegra_release"):
		return "jetson"

	return "generic"


@fact("cpu")
def _cpu():
	return {
		"physical": psutil.cpu_count(logical=False),
		"logical": psutil.cpu_count(logical=True),
	}


@fact("memory")
def _memory():
	vm = psutil.virtual_memory()
	return {"total": vm.total, "available": vm.available, "used": vm.used}


@fact("storage")
def _storage():
	"""
	Usage of the filesystem the home directory lives on -- the disk this
	machine actually stores things on (its "ROM", for an embedded-systems
	reading of the word), not necessarily "/" (a separate /home or /data
	mount would make "/" the wrong answer).
	"""
	du = psutil.disk_usage(os.path.expanduser("~"))
	return {"total": du.total, "used": du.used, "free": du.free}


def collect(*names):
	"""
	Collect a subset of facts (or all, if none named). One fact failing
	doesn't take down the rest -- a bad fact is recorded as
	{"error": "..."} in its own slot, not raised.
	"""
	names = names or list(_FACTS)
	result = {}
	for name in names:
		try:
			result[name] = _FACTS[name]()
		except Exception as e:
			result[name] = {"error": str(e)}
	return result
