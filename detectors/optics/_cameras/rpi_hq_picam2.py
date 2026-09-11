#from abcs.camera import AbstractCamera

from pprint import pprint, pformat
from copy import deepcopy
import logging as log
import numpy as np
import time
#from threading import sleep
from time import sleep
import yaml
from yaml.loader import SafeLoader
from io import StringIO 
import gc
import subprocess

from picamera2 import Picamera2, Preview
from picamera2.outputs import FfmpegOutput, FileOutput
from picamera2.encoders import H264Encoder, Quality

from core.utilities.mp4box import MP4Box



class Camera():
	"""
	Camera object framework specialised for Raspberry Pi HQ Camera.
	Implementation used Picamera v2 python library.

	config parameter can be used to pass a configuration dict.
	"""

	# 1
	def __init__(self):
		
		self.cam = Picamera2()
		log.info("PiCamera2 Camera was opened.") # Constructor opens the cam.

		self.cam_fsaddr = None   ## TODO
		self.opentime_ns = time.perf_counter()
		

		# Preview Window Settings
		self.preview_type = 1#Preview.QT # Other options: Preview.DRM or Preview.QT
		self.win_title_fields = ["ExposureTime", "FrameDuration"]  ##
		#self.cam.title_fields = ["ExposureTime", "FrameDuration"]  ##
		
		# Capture Modes for this implementation
		self.modes = {
					  "preview"      : self.preview,
					  "img"          : self.__image__,
					  "img_trig"     : self.__image_trig__,
					  "timelapse"	 : self.__timelapse__,
					  "vid"	         : self.__video__,
					  "vidmp4"       : self.__videomp4__,
					  "vid_noprev"   : self.__video_noprev__,
					  "vid_raw"      : self.__video_raw__,
					  "ndarray"		 : self.__ndarray__,
					  "stream"		 : self.__stream__
					 }

		## Capture the 4 different fundamental camera senor modes
		## TODO This dumps a whole list on the screen
		#self.sensor_modes = self.cam.sensor_modes


		# Video Encoders and image quality parameters
		self.encoderh264 = H264Encoder()
		self.cam.options["quality"] = 95
		self.cam.options["compress_level"] = 0
		self.output = None  ## Add a stream address


		# Monolithic Configurations
		with open("config/camconfig_picamera2.yaml") as file:
			self.config = yaml.load(file, Loader=SafeLoader)
		

		self.debug_mode = False
		if self.debug_mode:
			print("Camera configuration loaded: ")
			pprint(self.config)
		self.def_config = self.config
		

		### Set configuration using the configure function.
		self.configure(config=self.config)
		
		# Set camera status flags
		self.config_mode = "video" # Current Mode - ["preview", "still", "video"]
		self.status = "standby"
		self.all_statuses = ["standby", "acq", "waiting"]
		self.run_mode = "fixed" ## ["free", "fixed"]

		### Pre and Post Callbacks - timetagging and lux measurements
		self.en_pre_callback = False
		self.en_pre_lux_callback = False
		self.pre_buffer = StringIO()
		self.pre_callbackfile = None

		self.en_post_lux_callback = False
		self.en_post_callback = False
		self.post_buffer = StringIO()
		self.post_callbackfile = None


		# Configuration Setting Functions
		self.config_default =  lambda : self.configure(res=(1980, 1080), fps=30)
		self.config_default2 = lambda : self.configure(res=(2028, 1080), fps=30)
		self.config_largeres = lambda : self.configure(res=(4056, 3040), fps=10)
		self.config_largefps = lambda : self.configure(res=(1332, 990), fps=120)

		self.config_cammode1 = lambda : self.configure(res=(2028, 1080), fps=50)
		self.config_cammode2 = lambda : self.configure(res=(2028, 1520), fps=40)
		self.config_cammode3 = lambda : self.configure(res=(1332, 990), fps=120)
		self.config_cammode4 = lambda : self.configure(res=(4056, 3040), fps=10)
		

	# 2
	def open(self):
		##self.close()
		self.cam = Picamera2()
		self.opentime_ns = time.perf_counter()
		log.info(f"PiCamera2 Camera was opened: {self.opentime_ns}")

	# 3
	def is_open(self):
		return self.cam.is_open

	# 3
	def close(self):
		if self.cam.is_open:
			self.cam.close()
			now = time.perf_counter()
			log.info(f"PiCamera2 Camera was closed: {now} : duration {now-self.opentime_ns:.2f} s.")


	def new_config(self):
		### Configuration are usually missing
		pass



	# 4
	### NOk
	def configure(self, config=None, fps=None, res=None):
		"""
		Configure the base settings of the camera. 
		Both the [stream] configurations and controls.
		
		TODO: change buffer_count
		      maybe disable queue option
			  display="lores" for enabling preview
		"""


		## Custom configuration
		self.cam.stop()
		if config:
			if isinstance(config, str): ## Assume its a valid path
				with open(config) as file:
					self.config = yaml.load(file, Loader=SafeLoader)
			else:  ## Assume a dictionary of incomplete configuration options
				self.config = config

			## Interleave config with self.def_config to 
			## get a complete configuration set
			complete_set = self.def_config
			for key in complete_set:
				if key in config:
					complete_set[key] = config[key]
			for key in complete_set["controls"]:
				if key in config["controls"]:
					complete_set["controls"][key] = config["controls"][key]
			self.config = complete_set
			##########
			
			## Print updated configuration
			if self.debug_mode:
				print("Camera configuration loaded: ")
				pprint(self.config)
		
		# Only change fps and resolution
		if res != None:
			self.config["size"] = tuple(res)
			self.cam.video_configuration.main.size = tuple(res)
			self.config["size"] = tuple(res)
			print(f"rpi_hq_picam2: Set resolution to: {self.cam.video_configuration.main.size}.")
		if fps != None:
			frameduration = int((1/fps)*(1**6))
			framedurationlim = (frameduration, frameduration)
			self.cam.video_configuration.controls.FrameRate = fps
			self.config["controls"]["FrameDurationLimits"] = (framedurationlim, frameduration)
			self.config["controls"]["FrameRate"] = fps
			print(f"rpi_hq_picam2: Set fps to: : {self.cam.video_configuration.controls.FrameRate}.")		



		## Set all configuration options
		self.cam.video_configuration.controls.ExposureTime = self.config["controls"]["ExposureTime"]
		self.cam.video_configuration.controls.AwbEnable = self.config["controls"]["AwbEnable"]
		self.cam.video_configuration.controls.AeEnable = self.config["controls"]["AeEnable"]
		self.cam.video_configuration.controls.AnalogueGain = self.config["controls"]["AnalogueGain"]
		self.cam.video_configuration.controls.Brightness = self.config["controls"]["Brightness"]
		self.cam.video_configuration.controls.Contrast = self.config["controls"]["Contrast"]
		self.cam.video_configuration.controls.ColourGains = self.config["controls"]["ColourGains"]
		self.cam.video_configuration.controls.Sharpness = self.config["controls"]["Sharpness"]
		self.cam.video_configuration.controls.Saturation = self.config["controls"]["Saturation"]
		#self.cam.video_configuration.controls.ExposureValue = self.config["controls"]["ExposureValue"]
		
		## TODO - Duplicate config setting
		#self.cam.video_configuration.controls.FrameRate = self.config["controls"]["FrameRate"]
		#self.cam.video_configuration.size = tuple(res)
		self.cam.configure("video")
		self.cam.start()
		#sleep(2) # Sync Delay
		
		#Random fact: pH of blood of 7.4.

	# 5
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
		self.run_mode = "fixed"
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

				pre_ts_filenames  = [f"{filename_stubs[0]}_{i}_prets.txt" \
				for i in range(it)]

				post_ts_filenames = [f"{filename_stubs[0]}_{i}_postts.txt" \
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
		self.__do_callback_file_dumps__()
		gc.collect()


	# 6 ## OK
	def preview(self, tsec=10):
		"""
		Start a preview. Defaults for 30seconds. 
		Infinite preview or pre-emptive termination is not supported. 
		"""
		print(f"Preview: tsec: {tsec}")
		self.cam.title_fields = self.win_title_fields
		self.cam.start(show_preview=True)
		#self.cam.start_preview(preview=self.preview_type)
		sleep(tsec)
		self.cam.stop()
		self.cam.stop_preview()

	def new_h264encoder(self):
		if self.encoderh264.running:
			self.encoderh264.stop()
		return H264Encoder()


	## NOK
	def start_capture(mode, filename):
		"""
		Procedure
		---------
		> filename --> create-output --> create-encoder --> record
		"""
		if mode not in ["vid", "vidmp4"]:
			print("Unknown mode: switching to H264 captures.")
			mode = "vid"
		#---- cleanup-------------
		
		self.status = "acq"
		self.run_mode = "free"
		
		if mode == "vid":
			self.output = filename  ## No additional output object required
		elif mode == "vidmp4":
			self.output = FfmpegOutput(filename)
		
		## Start recording
		self.encoderh264 = self.new_h264encoder()
		if not "noprev" in mode:
			self.cam.start_preview()
		self.cam.start_recording(self.encoderh264, self.output, quality=Quality.HIGH)
	
	## NOK
	def stop_capture():
		"""
		Stop free capture
		"""
		self.cam.stop_preview()
		if self.run_mode == "free":
			self.cam.stop_recording()
		self.status = "waiting"


	
	# 7 TODo Rethink
	def state(self):
		"""
		Returns a dictionary of the parameter settings of the camera.
		"""
		state_ = {}
		state_["config"] = self.config
		state_.update(self.cam.camera_properties)
		return state_

	# 8
	def help(self):
		"""
		Prints docstrings for all capture modes.
		"""
		helpdict = {}
		for mode in self.modes:
			print(self.modes[mode])
			helpdict[mode] = self.modes[mode].__doc__.strip("\n").strip("\t")
		print("PiCamera2 Capture Modes:")
		for z in zip(self.modes.keys(), helpdict):
			pprint(z)


	# 9
	def __repr__(self):
		time_now = time.perf_counter()
		return f"<PiCamera2 - op for {(time_now - self.opentime_ns):.2f}s>"




	## Callback functions
	
	# 10 
	def en_pre_timestamps(self, filename):
		"""
		Need to be enabled before every acqusition.
		"""
		self.en_pre_callback = True

		## Clear buffer for use
		self.pre_buffer.truncate(0)
		self.pre_buffer.seek(0)

		## Open file in appendmode
		self.pre_callbackfile = open(filename, "a")

	# 11
	def en_post_timestamps(self, filename):
		"""
		Need to be enabled before every acqusition.
		"""
		self.en_post_callback = True

		## Clear buffer for use
		self.post_buffer.truncate(0)
		self.post_buffer.seek(0)

		## Open file in appendmode
		self.post_callbackfile = open(filename, "a")

	# 11
	def __do_callback_file_dumps__(self):
		"""
		Dumps the buffers to file.
		"""
		if self.en_pre_callback:
			print(f"Writing pre callbacks: {self.pre_callbackfile}")
			#print(self.pre_buffer.getvalue())
			self.pre_callbackfile.write(self.pre_buffer.getvalue())
			self.en_pre_callback = False
			self.pre_callbackfile.flush()
			self.pre_callbackfile.close()

			## disable callbacks
			self.cam.pre_callback = None

		if self.en_post_callback:
			print(f"Writing post callbacks: {self.post_callbackfile}")
			self.post_callbackfile.write(self.post_buffer.getvalue())
			print(self.post_buffer.getvalue())
			self.en_post_callback = False
			self.post_callbackfile.flush()
			self.post_callbackfile.close()

			## disable callbacks
			self.cam.post_callback = None


	### Callback functions
	def __pre_timestamp__(self, request):
		self.pre_buffer.write("{}{}".format(time.perf_counter(), "\n"))
	def __post_timestamp__(self, request):
		print("!",end="")
		self.post_buffer.write("{}{}".format(time.perf_counter(), "\n"))
	def __pre_lux_timestamp__(self, request):
		md = self.cam.capture_metadata()
		self.pre_buffer.write("{}{}{}".format(md, time.perf_counter(), "\n"))
	


	#### TODO Not evaluated at this point
	# --- Implementation Specific functions ---


	def optimize(self):
		# TODO Redo for all three configurations
		self.config = self.cam.align_configuration(self.config)
		log.info(f"Camera config optimized to: {self.config}")
		self.cam.configure(self.config)
		sleep(3)


	def timestamp(self, mode, *args, **kwargs):
		tsec = kwargs["tsec"]
		for i in range(tsec*self.get_fps()):
			f_md = self.frame_metadata()
			print(f"{i}. {self.time.time_ns()}")

	def frame_metadata(self):
		"""
		Returns the Metadata from the last frame.
		"""
		md = self.cam.capture_metadata()
		return md

	def lux_state(self):
		"""
		Returns the Lux state ("Avg Lux and ColorTemp of the last frame.")
		"""
		md = self.frame_metadata()
		return {"lux": md["Lux"], "color_temp": md["ColorGains"]}

	def lux(self):
		md = self.frame_metadata()
		return md["Lux"]


	def autoadjust(self, wb=True, exposure=True):
		"""
		Autoadjust "ExposureTime", "AnalogueGain", and "ColourGains".
		wb [optonal] : Adjusts the white balance (Red - Blue Ratio).
		exposure [optional] : Adjusts the exposure time of the camera.
		"""
		control_struct = {}
		if wb:
			control_struct.update({"AwbEnable": 1})
		if exposure:
			control_struct.update({"AeEnable": 1})

		self.cam.start_preview(self.preview_type)

		self.cam.stop()
		self.cam.configure(self.cam.create_video_configuration()) #Instead of this only upodate specific fields
		self.cam.start()

		sleep(1) # Wait for autoadjustments

		self.cam.set_controls({"AwbEnable": 0, "AeEnable": 0})
		sleep(5) # For checking the results.
		
		
		self.cam.stop_preview()
		self.cam.title_fields = self.win_title_fields

		# Push the updates to the controls structure and update the camera.
		ExposureTime = self.cam.video_configuration.ExposureTime
		ColorGains =  self.cam.video_configuration.ColorGains
		
		print(f"Autoadjusted -> ExposureTime: {ExposureTime} and ColorGains: {ColorGains}")
		print("Pushing the values to Camera Controls.")
		
		self.controls["ExposureTime"] = ExposureTime
		self.controls["ColorGains"] = ColorGains
		#for mode in self.config_map:
		#	self.config_map[mode]["controls"] = self.controls
		self.configure()
		
		#self.set_mode_config(self.mode_)

	def get_fps(self):
		"""
		Uses the Video Configuration as the default configuraation.
		"""
		return self.cam.video_configuration.controls.FrameRate

	def get_res(self):
		"""
		Uses the Video Configuration as the default configuraation.
		"""
		return self.cam.video_configuration.main.size

	
	### Capture mode implementations

	# OK
	def __image__(self, filename, *args, **kwargs):
		"""
		Capture a png image.
		tsec is ignored.
		"""
		#self.set_mode_config("still")
		self.cam.start_and_capture_file(filename)
		self.cam.stop_preview()

	# NOK
	def __image_trig__(self, filename, *args, **kwargs):
		"""
		Capture PNG image when the `Enter` key is pressed.
		"""
		#self.set_mode_config("still")
		
		self.cam.start_preview(self.preview_type)
		start = time.perf_counter()
		_ = input("Waiting for image trigger: Enter key...")
		
		self.cam.capture_file(filename, format='png')
		print("Capture completed.")

		self.cam.stop_preview()

	# NOk
	def __timelapse__(self, filename, *args, **kwargs):
		"""
		Captures a timelapse sequence in jpeg format.
		filenames: is preceeded by the capture sequence number.
		frames: number of frames that must be captured.
		delay_s (optional) : Delay between images in seconds.
		"""
		if not all(["frames", "delay_s"]) in kwargs:
			raise KeyError("Either arguments missing: frames and/or delay_s")

		#self.set_mode_config("still")

		self.cam.start_preview(self.preview_type)
		filenames_ = "{:03d}" + filename
		self.cam.start_and_capture_files( \
			name=filenames_, init_delay=0, \
			num_files = kwargs["frames"], delay = kwargs["delay_s"], \
			show_preview = True)
		self.cam.stop_preview()

	
	# OK
	def __video__(self, filename, *args, **kwargs):
		"""
		Record an h264 video.
		RPi Hardware supports processing upto 1080p30.
		timestamping is allowed for this mode.
		"""

		#self.cam.configure(self.cam.create_video_configuration())
		#self.set_mode_config("video")

		if self.en_pre_callback:
			self.cam.pre_callback = self.__pre_timestamp__
		if self.en_post_callback:
			self.cam.post_callback == self.__post_timestamp__

		tsec = kwargs["tsec"]
		output = FileOutput(filename)
		self.encoderh264 = self.new_h264encoder()
		self.cam.start_and_record_video(output, encoder=self.encoderh264, \
								 show_preview=True, \
								 duration=tsec)
		self.cam.stop_preview()
		# quality=Quality.HIGH

		### Dump callbacks to file
		self.__do_callback_file_dumps__()

	# OK
	def __video_noprev__(self, filename, *args, **kwargs):
		"""
		Record a video without preview in h264 format.
		Recommended for high fps recordings.
		"""
		#self.set_mode_config("video")

		if self.en_pre_callback:
			self.cam.pre_callback = self.__pre_timestamp__
		if self.en_post_callback:
			self.cam.post_callback == self.__post_timestamp__

		tsec = kwargs["tsec"]
		output = FileOutput(filename)
		self.cam.start_and_record_video(output, #encoder=self.encoderh264, \
								 show_preview=False, \
								 duration=tsec)

		## Asyncronously autoconvert to MP4
		if "mp4" in kwargs:
			if kwargs["mp4"]:
				mp4filename = filenamMe.rsplit(".", 1)

				mp4filename = filename[0] + ".mp4"
				MP4Box.convert(filename, mp4filename, \
							   30)
							   #self.cam.video_configuration.main.FrameRate)

	# Ok
	def __videomp4__(self, filename, *args, **kwargs):
		"""
		Record an MP4 file using Ffmpeg.
		Timestamps are not passed to Ffmpeg. Hence they are estimated.
		timestamping is enabled.
		"""
		#self.set_mode_config("video")

		if self.en_pre_callback:
			self.cam.pre_callback = self.__pre_timestamp__
		if self.en_post_callback:
			self.cam.post_callback == self.__post_timestamp__

		tsec = kwargs["tsec"]
		self.encoderh264 = self.new_h264encoder()
		self.output = FfmpegOutput(filename) # Opens a new encoder file object
		
		self.cam.start_and_record_video(self.output, encoder=self.encoderh264, \
								 show_preview=True, \
								 duration=tsec)
		self.cam.stop_preview()

		### Dump callbacks to file
		#self.__do_callback_file_dumps__()

	# 
	def __video_raw__(self, filename, *args, **kwargs):
		"""
		Captures in raw binary unncoded format. NOT IMPLEMENTED.
		"""
		self.set_mode_config("video") #Probably not necessary
		tsec = kwargs["tsec"]

	# 
	def __ndarray__(self, filename, *args, **kwargs):
		"""
		Capture to ndarray object. NOT IMPLEMENTED
		If filename is passed. The ndarray is packed to a .npy binary file.
		tsec: Capture time in seconds. Number of frames captured is tsec*framerrate.
		Shape of the captured array: frame X Width(px) X Height(px).
		"""

		# Need to set RGB888 format first
		
		# Check validity of the resolution
		tsec = kwargs["tsec"]
		fps = 30
		valid_res = [mode["size"] for mode in self.cam.sensor_modes]
		print(valid_res)
		res = [2028, 1080]
		#if self.config["size"] not in any(valid_res):
		#
		#	log.error("Invalid resolution for raw capture. Capture cancelled.")
		#	log.debug(f"Use the following resolutions instead: {valid_res}")
		#	return

		# Pre-allocate array
		array_shape = [int(tsec*fps), int(res[0]), int(res[1]), 4]
		self.array = np.ndarray(*array_shape)
		print(self.array.shape)

		self.cam.capture_arrays("main")

	# 
	def __stream__(self, stream):
		"""
		Capture to a stream like object. NOT IMPLEMENTED.
		"""
		pass

		
