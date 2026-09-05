"""
The one step that hands off out of the launcher and into the actual scope
CLI. The launcher is a layer above the scope CLI -- it never builds an
experiment environment or runs a script itself; this is where that
responsibility passes to expenv.build() (today's `python -i main.py`
equivalent).
"""

import __main__


def boot():
	"""Build the experiment environment and drop into a console with it."""
	from expenv import build
	namespace = build()

	vars(__main__).update(namespace)

	import code
	code.interact(local=vars(__main__), banner="", exitmsg="")
