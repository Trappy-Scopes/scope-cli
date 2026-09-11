import time
import logging as log

class Clock:
	"""
	Simple seconds-clock object that tracks time-elapsed and
	can be resumed by setting an offset.
	Note: Pickling the clock will automatically offset the clock.
	"""

	def __init__(self):
		self.init_time = time.perf_counter()
		self.offset = 0.0

	def offset_clock(self):
		newoffset = self.time_elapsed()
		self.offset = newoffset
		self.init_time = time.perf_counter()

	def time_elapsed(self):
		"""
		Time elapsed since the clock was created.
		"""
		return  self.offset + (time.perf_counter() - self.init_time)

	def read(self):
		"""AI Generated -- plain alias for time_elapsed(), added for
		MeasurementStream.subscribe_clock() (docs/notes/
		scripts_measurements_plotting.md §G.6) -- a Clock's own unit is
		always seconds, so callers just call .read()."""
		return self.time_elapsed()

	def resume_time(self):
		"""
		Time since the clock was last resumed.
		"""
		return (time.perf_counter() - self.init_time)

	def restart(self):
		self.init_time = time.perf_counter()
		self.offset = 0.0																


	def __repr__(self):
		return f"< Clock {self.time_elapsed()}s == {self.resume_time()}s+{self.offset}s >"
	
	def __getstate__(self):
		"""
		Pickling the clock will automatically offset the clock.
		"""
		self.offset_clock()
		return {"pause_time": time.perf_counter(), "offset": self.offset}

	def __setstate__(self, state):
		log.info(f"Resuming clock paused at: {state['pause_time']}s (epoch time)")
		self.init_time = time.perf_counter()
		self.offset = state["offset"]



