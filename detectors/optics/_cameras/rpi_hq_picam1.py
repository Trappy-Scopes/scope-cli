from abcs.camera import AbstractCamera
from picamera import PiCamera
from pprint import pprint



class Camera(AbstractCamera):
	"""
	Camera object framework specialised for Raspberry Pi HQ Camera.
	Implementation used Picamera v1 python library. 
	"""
	def __init__(self):
		self.cam = None
		self.config = None

	def open(self):
		self.cam = picamera.PiCamera()
		print("Camera object acquired!")

	def close(self):
		self.cam.close()
		self.cam = None
		print("Camera object released!")

	def configure(self, cam_config_file):
		"""
		Need a better configuration method for all these options.
		"""

		if isinstance(self.cam, PiCamera):
			self.config = yaml.load(cam_config_file)

			self.cam.framerate = self.config["framerate"]
			self.cam.resolution = (*self.config["resolution"])
			
			self.cam.brightness = self.config["brightness"]
			self.cam.color_effects = self.config["color_effects"]
			self.cam.contrast = self.config["contrast"]

			#self.cam.awb_mode = self.config["awb_mode"]
			#self.cam.awb_gains = self.config["awb_gains"]

			self.cam.drc_strength = self.config["drc_strength"]
			self.cam.flash_mode = self.config["flash_mode"]


			self.cam.iso = self.config["iso"]
			self.cam.exposure_mode = self.config["exposure_mode"]

			print("Camera config set:")
			pprint(self.config)


		else:
			print("No camera to configure! init() first!")


	def capture(self, action, filepath, tsec=1,
				iterations=1, itr_delay_s=0, init_delay_s=2):

		if action not any(["image", "video", "timelapse"]):
			print(f"Invalid mode passed: {action}")
			return

		action_map = {"image": self.__image__,
					  "video": self.__video__,
					  "timelaspe": self.__timelapse
					  }
		
		# Execute action
		start_time = self.perf_counter()
		captured = action_map[action](filepaths, **kwargs)
		stop_time = self.perf_counter()
		duration_s = stop_time - start_time
		return captured

	
	def preview(self, tsec=30):
		"""
		Preview at set resolution.
		"""

		if "preview" in self.config:
			self.cam.resolution = (self.config["preview"]["resolution"])
			self.cam.framerate = self.config["preview"]["framerate"]

		self.cam.start_preview()
		time.sleep(tsec)
		self.cam.stop_preview()

	def __repr__(self):
		print(
	f"""
	   _______
	 _|__[*]__|_
	|   \\| |/   |
	|Rpi (O) Cam|     {self.cam}
	|   /| |\\   |
	-------------  
	""")

	# Functions not in ABC ---------------------------------

	
	# Capture Actions
	def __image__(self, filepath, **kwargs):
		if not filepath.endswith(".png"):
			filepath = filepath + ".png"
		self.cam.capture()


	def __video__(self, filepath, **kwargs):
		if not filepath.endswith(".h264")
			filepath = filepath + ".h264"

		self.cam.start_recording(filepath, format="h264")
		self.cam.wait_recording(kwargs["tsec"])
		self.cam.stop_recording()
		return filepath

	def __previewvideo__(self, filepath, **kwargs):
		if not filepath.endswith(".h264")
			filepath = filepath + ".h264"

		self.cam.start_recording(filepath, format="h264")
		self.cam.start_preview()
		self.cam.wait_recording(kwargs["tsec"])
		self.cam.stop_recording()
		self.cam.stop_preview()
		return filepath

	def __timelapse__(self, filepath, **kwargs):
		"""
		Previews by default
		"""

		camera.start_preview()
		sleep(kwargs["init_delay_s"])
		
		captured = []
		for filename, i in enumerate(self.cam.capture_continuous(
			f'{filepath}_{counter:03d}.png')):
		    
		    captured.append("%s")
		    print('Captured %s' % filename)
		    sleep(kwargs["itr_delay_s"]) # wait 5 minutes

		    if i == kwargs["iterations"]:
		    	break
		
		return captured


	def __ndarray__(self, filepath, **kwargs):
		
		no_frames = kwargs['frames']
		print(f"Capturning {no_frames} frames!")	
		output = np.empty((*self.cam.resolution, no_frames), 
						  dtype=np.uint16)

    	i = 0
    	start_time = time.perf_counter()
    	for _ in self.cam.capture_continuous():
    		camera.capture(output[i], 'rgb')
    		i = i + 1
    		if i >= no_frames:
    			break
    	end_time = time.perf_counter()
    	
    	print(f"Duration: {end_time - start_time} s" )
    	return output

	def __tiff__(self, filepath, **kwargs):
		pass


