## Move to another place


from numpy import arange
from picamera import PiCamera

def read_cam_config(camera):
	config_dict = {
			'resolution'     : camera.resolution,
			'framerate'      : camera.framerate,
			'ISO'            : camera.iso,
			'ana_gain'       : camera.analog_gain,
			'dig_gain'       : camera.digital_gain,
			'exposure_speed' : str(camera.exposure_speed/1000) + ' ms',
			'exposure_mode'  : camera.exposure_mode,
			'max_resolution' : camera.MAX_RESOLUTION,
			'max.framerate' : str(camera.MAX_FRAMERATE),
			'drc_strengths'  : camera.DRC_STRENGTHS
				  }
	return config_dict


def scan_iso(camera):
	iso_range =[100, 200, 320, 400, 500, 640, 800]
		i = 0
		while True:
			camera.iso(iso_range%len(iso_range))
			i = i + 1
			yield camera

def scan_awb(camera, adjust="uniform", increments=1.0, setval=4):
	"""
	Single value adjustments fix both red and blue gains uniformly.
	Tuple values adjust both seperately.
	adjust: "uniform", "red", "blue" : tuple is ("red", "blue")
	range of gain values is between 0 and 8.
	"""
	i = 0
	gain_range = list(arange(0, 8, increments))
	mode_map = {"uniform": lambda x: (x,x),
				"red"    : lambda x: (x, setval),
				"blue"   : lambda x: (setval, x)
				}
		i = 0
		while True:
			if adjust == "uniform"
			camera.awb(mode_map[adjust](gain_range%len(iso_range)))
			i = i + 1
			yield camera


def scan_contrast(camera):
	contrast_list = [i*10 for i in range(10)]

	i = 0
	while True:
		camera.contrast(contrast_list[i%10])
