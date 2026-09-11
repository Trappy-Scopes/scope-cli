#from abcs.camera import AbstractCamera

import logging as log
import time

import sys
#from threading import sleep
from time import sleep
from yamlprotocol import YamlProtocol
from io import StringIO 
import gc
import subprocess
from subprocess import Popen, PIPE


from rich import print

class Camera:
	def __init__(self):
		self.process = None
		self.status  = "standby"
		self.modes = {"preview": self.__preview__, "vid": self.__video__, 
					  "img": self.__image__,
					  "vid_mjpeg_prev": self.__vid_mjpeg_prev__}

	def capture(self, action, filename, tsec=1,
				it=1, it_delay_s=0, init_delay_s=0, **kwargs):
		"""
		init_delay does not include camara mode changes applied at 
		the beginning which might be of the order of 100s of ms.
		"""	
		#TODO Add a better way to determine precision timing than ns_tick
		
		#print("For debug: cam properties:")
		#pprint(self.cam.video_configuration)

		action = action.lower().strip()
		
		sleep(init_delay_s)

		if it == 1:
			if action == "preview":
				self.status = "acq"
				self.modes[action](tsec=tsec, **kwargs)
			else:
				self.status = "acq"
				self.modes[action](filename, tsec=tsec, **kwargs)
		
		else:
			if action == "preview":
				self.status = "acq"
				self.modes[action](tsec=tsec, **kwargs)
			else:
				filename_stubs = filename.split(".")
				filenames_ = [f"{filename_stubs[0]}_{i}.{filename_stubs[1]}" \
				for i in range(it)]

				print(filenames_)
				sleep(init_delay_s)
				
				for i in range(it):
					filename_ = filenames_[i]
					print(f"{i}: {time.time_ns()}. Capturing file: {filename_} :")
					
					self.status = "acq"
					self.modes[action](filename_, tsec=tsec, **kwargs)
					self.status = "waiting"
					
					print(f"{i}:  {time.time_ns()}. Sleeping for {it_delay_s}s.")
					
					sleep(it_delay_s)
		self.status = "standby"
		gc.collect()

	def __process__(self, cmd):
		self.process = Popen(cmd, stdout=sys.stdout, stderr=sys.stderr, shell=True,\
					    universal_newlines=True)
		
		pid = self.process.pid
		stdout, stderr = self.process.communicate()
		return self.process.returncode, stdout, stderr, pid

	def preview(self, tsec=10):
		return self.__preview__(tsec=tsec)


	def __preview__(self, tsec=10):
		cmd_list = f"libcamera-vid -t {tsec*1000} -f"
		return self.__process__(cmd_list)

	def __image__(self, filename, *args, **kwargs):
		print("Capturing in 5 seconds!")
		cmd_list = f"libcamera-still -t {5*1000} -f -o {filename}"
		return self.__process__(cmd_list)

	def __video__(self, filename, *args, **kwargs):
		
		tsec = kwargs["tsec"]

		cmd_list = f"libcamera-vid -t {tsec*1000} -f -o {filename}"
		return self.__process__(cmd_list)

	def __vid_mjpeg_prev__(self, filename, *args, **kwargs):
		tsec = kwargs["tsec"]

		cmd_list = f"libcamera-vid -t {tsec*1000} -f -o {filename} --codec mjpeg --width 2028 --height 2028 --denoise off --awbgains 0,0 --analoggain 1 --framerate {kwargs['fps']} --shutter {kwargs['exposure_ms']*1000} -q {kwargs['quality']}"
		return self.__process__(cmd_list)

	def is_open(self):
		return True

	def open(self):
		pass
	def close(self):
		pass









		