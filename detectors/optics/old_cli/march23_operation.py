import subprocess
import fluff
from pprint import pprint
from picamera import PiCamera
import pyboard
from time import sleep
import time
import sys
import os
from cam_config import cam_config

global pyb
pyb = None

def convert_to_mp4(filename, fps):
	foldername = filename.split(".")[0]
	mp4name = os.path.join(foldername, (filename.split(".")[0] + ".mp4"))

	command = f"MP4Box -add {filename}:fps={fps} {mp4name}"
	print(command)
	#process = subprocess.run(command, stdout=sys.stdout, stderr=sys.stderr, shell=True)
	os.system(command)
	return mp4name

def create_folder(filename):
	foldername = filename.split(".")[0]
	os.mkdir(foldername, mode = 0o777)
	return foldername

def postprocess(filename, fps=30):
	"""
	Postprocessing of recorded videos.
	"""

	# 1
	foldername = create_folder(filename)

	# 2
	mp4name = convert_to_mp4(filename, fps=fps)

	# 3 Move h264 to the same folder
	from shutil import move
	move(filename, os.path.join(foldername, filename))


def hey_pico(command):
	global pyb
	
	print(f"pico! do >> {command}")
	ret = pyb.exec(command)
	print(f"pico said >> {ret.decode()}")
	
	#pyb.exit_raw_repl()



def set_lightsV(pico_light_obj_name, rV, gV, bV):
	
	command = f"{pico_light_obj_name}.setVs({rV}, {gV}, {bV})"
	
	hey_pico(command)


def record_video(filename, res=[1920, 1088], fps=30, tsec=30):
	"""
	Call fucntion to record a video
	"""
	camera = PiCamera()
	camera.resolution = tuple(res)
	camera.framerate = fps
	print("Camera object acquired!\nCamera configuration:")
	

	# CONFIG -------------------------
	camera.framerate = 30
	camera.resolution(1920, 1080)
	
	camera.brightness(50)
	camera.color_effects(None)
	camera.contrast(0)

	camera.awb_mode("off")
	camera.awb_gains(1.9)

	camera.drc_strength("off")
	camera.flash_mode('off')


	camera.iso(200)
	camera.exposure_mode("off")
	# CONFIG -------------------------

	


	pprint(cam_config(camera))
	print()
	
	camera.start_recording(filename, format="h264")          # Start recording
	camera.start_preview()
	camera.wait_recording(tsec)                    				# Wait for while 
																# the camera records
	camera.stop_recording()                                     # Stop the camera
	print("Recording finished!")

	camera.close()

def preview(tsec=30):
	"""
	Simple function for previews.
	"""
	camera = PiCamera()
	camera.resolution = (1920, 1088)
	camera.framerate = 30

	camera.start_preview()
	time.sleep(tsec)
	camera.stop_preview()

	camera.close()
	
	
def init_seq(filename = None):
	
	# Configs
	pico_light_obj_name = "l2"
	fps=30

	# Step 1 - Turn on illumination
	hey_pico('exec(open("main.py").read())')
	hey_pico("handshake()")
	set_lightsV(pico_light_obj_name, 1,1,1)

	
	
	# Set filename
	if len(sys.argv) >= 2:
		filename = sys.argv[1]

	# Record Video
	if filename != None:
		record_video(filename, res=[1920, 1088], fps=fps, tsec=60)
	else: 
		print("No filename given! Exiting!")
		exit(1)

	# Step 3 - postprocess
	folder = postprocess(filename, fps=fps)
	print(folder)

	# Step 4 - Transfer
	#transfer_files(folder)
	
	#set_lightsV(pico_light_obj_name, 0,0,0)
	#print("Lights off!")

if __name__ == "__main__":
		
		print(fluff.header())
		print("All availbale ports:")
		import serial.tools.list_ports as list_ports
		all_ports = list(list_ports.comports())
		for port in all_ports:
			print(port)
		print("-"*10)
		
		
		pyb = pyboard.Pyboard('/dev/ttyACM0', 115200)
		print('/dev/ttyACM0 is acquired!')
		pyb.enter_raw_repl()

		if len(sys.argv) >= 2:
			init_seq()
		else:
			hey_pico('exec(open("main.py").read())')
			
		print("Setting interactive mode in python")
		import code
		code.interact(local=locals())
			
		


