


def safepicam2_config(configuration):
	config = {}

	try:
		config["size"] = configuration.size
	except AttributeError:
		pass
	
	try:
		config["use_case"] = configuration.use_case
	except AttributeError:
		pass
	
	try:
		config["fps"] = configuration.controls.FrameRate
	except AttributeError:
		pass
	
	try:
		config["exposure_time"] = configuration.controls.ExposureTime
	except AttributeError:
		pass

	try:
		config["awb_enable"] = configuration.controls.AwbEnable
	except AttributeError:
		pass

	try:
		config["ae_enable"] = configuration.controls.AeEnable
	except AttributeError:
		pass

	try:
		config["analogue_gain"] = configuration.controls.AnalogueGain
	except AttributeError:
		pass

	try:
		config["brightness"] = configuration.controls.Brightness
	except AttributeError:
		pass

	try:
		config["contrast"] = configuration.controls.Contrast
	except AttributeError:
		pass

	try:
		config["colour_gains"] = configuration.controls.ColourGains
	except AttributeError:
		pass

	try:
		config["sharpness"] = configuration.controls.Sharpness
	except AttributeError:
		pass

	try:
		config["saturation"] = configuration.controls.Saturation
	except AttributeError:
		pass

	for stream in ["main", "raw", "lores"]:
		if configuration.__dict__[stream]:
			config[stream] = {}
			config[stream]["size"] = configuration.__dict__[stream].__dict__["size"]
			config[stream]["format"] = configuration.__dict__[stream].__dict__["format"]
			config[stream]["stride"] = configuration.__dict__[stream].__dict__["stride"]
			config[stream]["framesize"] = configuration.__dict__[stream].__dict__["framesize"]
		else:
			config[stream] = None

	return config
