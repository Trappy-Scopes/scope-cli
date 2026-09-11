import sounddevice as sd

import numpy as np
from time import sleep
from threading import Thread
import atexit
from functools import partial
import logging as log

from .abstractalarm import Alarm as AbstractAlarm

class Alarm(AbstractAlarm):
	freq = 600
	def __init__(self):
		self.thread = None
		self.state = 0 #0 is off and 1 is on

	def on(self):
		"""
		Turn on the alarm indefinately.
		Produces 5secs ON and 0.1sec OFF. Can't be fixed (I think).
		Maximum limit of 100 seconds.
		"""
		self.state = 1
		def alarm_on_100sec():
			i = 0
			while self.state and i < (99/3):
				self.__sine__(Alarm.freq, 3)
				i=i+1
			self.state = 0
			log.debug("Alarm switched off.")

		self.thread = Thread(name="alarm_on", target=alarm_on_100sec)
		self.thread.start()
		atexit.register(self.off)

	def off(self):
		"""
		Turn off the alarm.
		"""
		atexit.unregister(self.off)
		self.state = 0
		if isinstance(self.thread, Thread):
			if self.thread.is_alive():
				self.thread.join()

	def blink(self):
		"""
		Blink/pulse the alarm indefinately.
		Maximum limit of 100 seconds: 1Hz.
		"""
		self.state = 1
		def alarm_on_100sec_beep():
			i = 0
			while self.state and i < 99:
				self.__sine__(Alarm.freq, 1, low_time_s=1)
				i=i+1
			self.state = 0
			log.debug("Alarm switched off.")

		self.thread = Thread(name="alarm_blinking", target=alarm_on_100sec_beep)
		self.thread.start()
		atexit.register(self.off)

	def beep(self, n):
		"""
		Blink/pulse the alarm "n" times.
		Blocking process.
		"""
		for i in range(n):
			self.__sine__(Alarm.freq, 1, low_time_s=1)


	def __sine__(self, freq, duration, low_time_s=0, sample_rate=22050):
		t = np.linspace(0, duration, int(sample_rate * duration), endpoint=False)
		x = 0.5 * np.sin(2 * np.pi * freq * t)
		sd.play(x, sample_rate)
		sd.wait()
		if low_time_s:
			sleep(low_time_s)