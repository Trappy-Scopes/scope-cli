
"""
An implementation of the FIM image browser for the terminal
"""

import subprocess
from collections.abc import Iterable

def fim(filenames):
	if not isinstance(filenames, Iterable):
		filenames = list(filenames)
	subprocess.run(["fim", "-a", *filenames])