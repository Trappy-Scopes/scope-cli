import sys
sys.path.append("./cameras/")

def CameraSelector(device, *args, **kwargs):
	device = device.strip().lower()

	if device == "rpi_hq_picam2":
		from  rpi_hq_picam2 import Camera
		return Camera(*args, **kwargs)
	
	if device == "rpi_hq_picam1":
		from rpi_hq_picam1 import Camera
		return Camera(*args, **kwargs)
	
	if device == "alliedvision":
		from alliedvision import Camera
		return Camera(*args, **kwargs)

	if "null" in device:
		from nullcamera import Camera
		return Camera(*args, **kwargs)

	if device == "libcamera":
		from libcameraint import Camera
		return Camera(*args, **kwargs)

	if device == "macos":
		from macos import Camera
		return Camera(*args, **kwargs)

	log.error(f"Invalid camera mode: {device}")
