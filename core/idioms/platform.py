"""
General machine introspection. Not package-management-specific -- CPU/RAM
facts were considered and deliberately dropped (not needed); scope is
`os`/`board` only, kept extensible by registering more facts rather than
growing one function.

Not a duplicate of core/bookkeeping/systeminfo.py: that module records
narrow *identity* facts (MAC address, hostname) for experiment provenance.
This one answers "what kind of machine is this," for anything that needs
to branch on it -- currently just hardware-profile selection.

`board` recognises only the two natively-known cases (Raspberry Pi,
Jetson) plus a generic fallback. It is deliberately *not* the full
hardware-profile scanner -- that walks native/external/machine-local
profile directories with precedence and reads each one's own `profile.yaml`
`detect:` command, and lives in core/installer/environment.py, which calls
`collect("board")` as one input among others (including profiles this
module has no knowledge of).
"""

import os
import platform as _platform

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
