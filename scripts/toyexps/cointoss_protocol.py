"""
AI Generated -- new file, Claude (Anthropic), 2026-09.

Coin-toss experiment driven by an electronic protocol instead of a fixed
scheduled sequence -- the counterpart to cointoss.py (which just runs 5
scheduled tosses), used to test expframework.protocol.Protocol itself:
inline python execution, per-step keyboard shortcuts, and
enable_shortcuts() checkpoint mode (see docs/notes/protocols.md).

author: Claude (Anthropic), for Yatharth Bhasin
date: 2026-09-08
"""

import random
import time

from rich import print

from expframework.experiment import Experiment
from expframework.protocol import Protocol


__description__ = """
Coin-toss test fixture for the electronic-protocol engine. Loads
test_protocols/cointoss.md (from Experiment.protocols_dirs) and drives it
via keyboard shortcuts instead of a scheduled loop -- Esc,b starts a
session, Esc,t records one toss, Esc,n ends it and reports how long the
recorded tosses took.
"""

print("Use create_exp() to create an experiment.")
print("Use load_protocol() to load test_protocols/cointoss.md, then p.enable_shortcuts().")
print("Esc,b starts a session; Esc,t records a toss; Esc,n ends the session.")


def create_exp():
	"""Construct the test experiment and its `tosses` measurement stream."""
	global exp, tosses
	exp = Experiment.Construct(["test", "protocol_engine", "coin_toss"],
								user=True, eid=True, date=True, time=True, scopeid=True)
	tosses = exp.new_measurementstream("tosses", measurements=["result"])


def load_protocol():
	"""Load the coin-toss test protocol -- call p.enable_shortcuts() next."""
	global p
	p = Protocol("test_protocols/cointoss.md")
	p.show()
	return p


def toss_session_start():
	"""Bound to Esc,b by the protocol's own `run:` declaration -- marks
	the start of a toss session so toss_session_end() can report elapsed
	time for exactly this session, not the whole experiment."""
	global _session_start
	_session_start = time.time()
	print("[green]Toss session started.[/green]")


def record_toss():
	"""Bound to Esc,t -- one coin toss, logged to the `tosses` stream."""
	result = random.choice(["heads", "tails"])
	tosses(result=result)
	print(f"Toss #{len(tosses.readings)}: [bold]{result}[/bold]")
	return result


def toss_session_end():
	"""Bound to Esc,n -- reports how many tosses were recorded and how
	long the session actually took."""
	elapsed = time.time() - _session_start
	n = len(tosses.readings)
	print(f"[yellow]Session ended -- {n} toss(es) in {elapsed:.2f}s.[/yellow]")
	exp.log("toss_session_ended", attribs={"n_tosses": n, "elapsed_s": elapsed})


if __name__ == "__main__":
	create_exp()
	load_protocol()
	p.enable_shortcuts()
