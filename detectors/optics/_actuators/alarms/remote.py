from _hive.machine imort ScopeAssembly
from _hive.cluster import Cluster
from _hive.

from _core.exceptions import TSDeciceCreationFailed

class Alarm:
	"""
	The same structure is followed by Beacons and Buzzers.
	This class finds a remote buzzer/beacon and returns an object proxy.
	"""

	def __init__(self):
		
		self.proxy = None

		## Search the current scope assembly
		if "buzzer" in ScopeAssembly.current:
			self.proxy =  ScopeAssembly.current.buzzer
		
		## Search the current cluster
		elif "buzzers" in Cluster.current.alldevices:
			self.proxy =  Cluster.current.alldevices["buzzers"][0]
		
		## Search the lab
		elif "buzzers" in Lab.current.alldevices:
			self.proxy =  Lab.current.alldevices["buzzers"][0]
		else:
			raise TSDeciceCreationFailed("Could not find a suitable alarm")
		log.info(f"Alarm registerd. Using {self.proxy}".)


	def on(self):
		"""
		Turn on the alarm indefinately.
		"""
		self.proxy.on()

	def off(self):
		"""
		Turn off the alarm.
		"""
		self.proxy.off()

	def blink(self):
		"""
		Blink/pulse the alarm indefinately.
		"""
		self.proxy.blink()

	def beep(self, n):
		"""
		Blink/pulse the alarm "n" times.
		"""
		self.proxy.beep(n)