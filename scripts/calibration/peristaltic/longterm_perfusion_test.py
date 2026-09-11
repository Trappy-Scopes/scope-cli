description = \
"""
Experiment description

"""


import datetime
from time import sleep
import time
from experiment import Calibration
from rich import print
from rich.markdown import Markdown

from cleaners import safepicam2_config



print("Trap: ", trap)
print("Pump id: ", pump_id)


# Start experiment
unique_check = True
dt = str(datetime.date.today()).replace("-", "_")
t = time.localtime(time.time())


## Create experiment
exp = Experiment(f"{scopeid}_long_term_perfusion_{dt}_{t.tm_hour}_{t.tm_min}", append_eid=True)
exp.delay("Start delay", 3)





### Configure experiment
exp.attribs.update({"setup" : ["long_term_tests", "live_cells", "sampling"],
					"description" : description,
				    "res":[1920, 1080],
				    "fps": 20,
				    "magnification": 1.0,
				    "again":3,
				    "exposure_time_us":50000,
				    "voltage":2.0,
				    
				    "awb_enable" :  False,
				    "ae_enable" :  False,
				    "brightness" :  0.3,
				    "digital_gain":1,
				    "contrast" :  2.5,
				    "colour_gains" :  (0.,0.),
				    "sharpness" :  1.,
				    "saturation" :  .5,
				    "queue"      : False,

				    "quality" : 95,
				    "compress_level": 0,
				   })



def configure_camera():
	## Set Camera settings:
	cam.close()
	cam.open()

	# create video configuration
	res = exp.attribs["res"]
	cam.cam.create_video_configuration({"size":exp.attribs["res"]})
	cam.cam.video_configuration.controls.ExposureTime = exp.attribs["exposure_time_us"]
	cam.cam.video_configuration.controls.AwbEnable    = exp.attribs["awb_enable"]
	cam.cam.video_configuration.controls.AeEnable     = exp.attribs["ae_enable"]
	cam.cam.video_configuration.controls.AnalogueGain = exp.attribs["again"]
	#cam.cam.video_configuration.controls.DigitalGain = exp.attribs["digital_gain"]
	cam.cam.video_configuration.controls.Brightness   = exp.attribs["brightness"]
	cam.cam.video_configuration.controls.Contrast     = exp.attribs["contrast"]
	cam.cam.video_configuration.controls.ColourGains  = exp.attribs["colour_gains"]
	cam.cam.video_configuration.controls.Sharpness    = exp.attribs["sharpness"]
	cam.cam.video_configuration.controls.Saturation   = exp.attribs["saturation"]

	cam.cam.video_configuration.size  = (res[0], res[1])
	#cam.cam.video_configuration.queue  = exp.attribs["queue"]
	#cam.cam.video_configuration.buffer_count  = 4


	### Set compression and quality
	#cam.cam.options["quality"] = exp.attribs["quality"]
	#cam.cam.options["compress_level"] = exp.attribs["compress_level"]


	## Print -> set configuration
	read_config =  safepicam2_config(cam.cam.video_configuration)
	print(read_config)




global counter, mstream
counter = 0
mstream = exp.new_measurementstream("captures", measurements=["acq"],
								 	monitors=["tandh"])

def epoch_to_hours(epoch_time):
    hours_since_epoch = epoch_time / 3600
    return f"{hours_since_epoch:.2f}"

def acquire():
	now = time.time()
	capname = f"duration_{str(epoch_to_hours(now)).replace('.', '_')}h.h264"

	m = Experiment.current.streams["captures"]() ## Generate measurement

	## Capture
	cam.close()
	cam.open()
	cam.cam.create_video_configuration({"size":exp.attribs["res"]})
	#configure_camera()
	exp.delay("Camera sync wait", 10)
	cam.capture(vid_noprev, capname, tsec=30)
	cam.close()
	
	m["acq"] = capname
	m["fluidics"] = trap.name
	m["fluidics_type"] = trap.attribs["type"]
	m["pump_id"] = pump_id ## Need to be defined beforehand

	try:
		m["tandh"] = scope.picoprox.tandh.read()
	except:
		pass
	m.panel()
	#counter += counter





## Schedule acquisitions
exp.schedule.every().hour.do(acquire)  # registration now logs itself -- post_register() retired


## Configure
scope.picoprox.lit.setVs(exp.attribs["voltage"], 0, 0)
configure_camera()
exp.delay("Delay before first capture", 10)
acquire() ## Make the first acquisition

