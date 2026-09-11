"""
AI Generated.

Drift-free waiting -- replaces core/precision/timing.py (removed
entirely): that module's precise_sleep() was a bare time.sleep() despite
its name (real callers: detectors/cameras/rpi_hq_picam2.py, 5 call
sites), and its DriftCorrected.monitored_sleep() was dead, non-functional
code (never imported anywhere; would have raised NameError/AttributeError
if it ever ran) sitting under a `# TODO: Correct processor drift.`
comment that was never acted on.

The pattern here is PsychoPy's, not invented here -- credited explicitly:
psychopy.core.wait(secs, hogCPUperiod=0.2) and PsychToolbox's
WaitSecs('UntilTime', target) both split a wait into a coarse sleep
phase (cheap, but subject to OS scheduling jitter -- typically 1-15ms)
and a final short busy-poll phase (expensive -- pins one CPU core, but
resolves to roughly microsecond/low-millisecond precision because it
never yields to the OS scheduler at all). See
docs/notes/experiment_architecture_and_actions.md §F for the full
writeup, including why subdividing a sleep into equal steps (the old
Experiment.delay()/DriftCorrected pattern) is an anti-pattern, not a
precision mechanism: it accumulates assumed elapsed time from nominal
sleep durations instead of measuring real elapsed/remaining time from a
clock, so OS jitter compounds across every step instead of staying
bounded.
"""

import time


def precise_sleep(seconds, hog_period=0.2, on_tick=None):
	"""Wait `seconds`, accurate to roughly the busy-poll phase's
	resolution (sub-millisecond on most systems), not time.sleep()'s
	looser OS-scheduling jitter.

	Never accumulates assumed progress from nominal sleep durations --
	every loop iteration re-measures `remaining` fresh from
	time.perf_counter() against one absolute deadline computed up front,
	so any single sleep call's overshoot is absorbed on the next
	iteration instead of compounding.

	on_tick(elapsed), if given, fires roughly every 250ms during the
	coarse phase -- e.g. to drive a progress bar -- from *measured*
	elapsed time (seconds - remaining), never from counting iterations.
	Safe to omit for a plain blocking wait.
	"""
	deadline = time.perf_counter() + seconds

	# Coarse phase: sleep against the real deadline, not a fixed step count.
	while True:
		remaining = deadline - time.perf_counter()
		if remaining <= hog_period:
			break
		time.sleep(min(remaining - hog_period, 0.25))
		if on_tick:
			on_tick(seconds - remaining)

	# Precise phase: busy-poll the last hog_period for real precision.
	while time.perf_counter() < deadline:
		pass

	if on_tick:
		on_tick(seconds)
