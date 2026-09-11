class Lenses:
	"""
	Describes a data structure for Lenses.
	|- AchromaticDoublet
	|- 

	|-Asphere
		|- <Asphere-model n>
	|-Objective
		|- Zoom Lens
		|- <Objective-model n>
	|- Lens

	"""

	class TransferElement:
		def __init__(self):
			self.attribs = {}
		def light_gathering_factor(self):
			"""
			f/#
			"""
			return self.attribs["focal_length_mm"]/self.attribs["dia_mm"]

	class AchromaticDoublet:
		pass



	class Asphere:

		models = {"ACL2520U-DG6": {"name":"ACL2520U-DG6", "dia_mm":25, 
								   "focal_length_mm":20.1, "NA":0.60,
								   "grit": 600, "coating": "uncoated",
								    "vendor": "ThorLabs"},
				  "ACL2520U"     : {"name":"ACL2520U", "dia_mm":25, 
								   "focal_length_mm":20.1, "NA":0.60,
								   "grit": 0, "coating": "uncoated",
								    "vendor": "ThorLabs"},
				 }
		def __init__(self, name, attribs={}):
			self.name = name
			self.attribs = {"name": self.name, "type": "optics.lenses.asphere"}
			self.attribs.update(attribs)
			if self.name in Lenses.Asphere.models:
				self.attribs = Lenses.Asphere.models[self.name]
				self.attribs["type"] = "optics.lenses.asphere"
		def __getstate__(self):
			return self.attribs

		def __repr__(self):
			vendor = ""
			if "vendor" in self.attribs:
				vendor = self.attribs["vendor"]
			return f"< Optics.Lenses.Asphere :: {self.name} {'- '*bool(vendor)}{vendor} >"

	class Objective:
		"""
		|- Achromatic
		|- Fluorite
		|- Apochromatic
		
		"""
		models = {}

		def __init__(self, name, attribs={}):
			self.name = name
			self.attribs = {"name": self.name, "type": "optics.lenses.objective"}
			self.attribs.update(attribs)
			if self.name in Lenses.Objective.models:
				self.attribs = Lenses.Objective.models[self.name]
				self.attribs["type"] = "optics.lenses.objective"
		def __getstate__(self):
			return self.attribs

		def __repr__(self):
			vendor = ""
			if "vendor" in self.attribs:
				vendor = self.attribs["vendor"]
			return f"< Optics.Lenses.Objective :: {self.name} {'- '*bool(vendor)}{vendor} >"

		class ZoomLens:
			def __init__(self):
				pass
			def __getstate__(self):
				return {"name": "zoomlens", "type": "optics.lenses.zoomlens"}

			def __repr__(self):
				return f"< Optics.Lenses.Objective.Zoomlens >"

	class Lens:
		def __init__(self, name, attribs={}):
			self.name = name
			self.attribs = {"name": self.name, "type": "optics.lenses.objective", 
							"curvature":None, "f":None}
			self.attribs.update(attribs)
			if self.name in Lenses.Objective.models:
				self.attribs = Lenses.Objective.models[self.name]
				self.attribs["type"] = "optics.lenses.objective"


class Optics:

	lenses = []
	assembly = []



	def calc_metrics():
		"""
		res: read camera, calibrate usaf test target.
		mag: read Optics class, usaf target, or chamber.
		contrast: read camera, and take a few images.
		"""
		return {"res": None, "mag": None, "contrast": None}

	def populate(partialdevice):
		if "lenses" in partialdevice:
			for l in partialdevice["lenses"]:
				if "zoomlens" in l:
					Optics.lenses.append(Lenses.Objective.ZoomLens())
				else:
					Optics.lenses.append(Lenses.Asphere(l))