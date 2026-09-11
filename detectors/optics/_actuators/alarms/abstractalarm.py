from abc import abstractmethod


class Alarm:
	"""
	The same structure is followed by Beacons and Buzzers.
	"""

	@abstractmethod
	def __init__(self):
		pass

	@abstractmethod
	def on(self):
		"""
		Turn on the alarm indefinately.
		"""
		pass

	@abstractmethod
	def off(self):
		"""
		Turn off the alarm.
		"""
		pass

	@abstractmethod
	def blink(self):
		"""
		Blink/pulse the alarm indefinately.
		"""
		pass

	@abstractmethod
	def beep(self, n):
		"""
		Blink/pulse the alarm "n" times.
		"""
		pass

	def Selector(device, *args, **kwargs):
		device = device.lower() 
		if device == "onsystem":
			from .onsystem import Alarm
			return Alarm(*args, **kwargs)
		else:
			from .remote import Alarm
			return Alarm(*args, **kwargs)


