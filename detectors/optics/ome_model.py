from ome_types.model import Instrument, Objective, InstrumentRef
from ome_types.model import Microscope as OMEMicroscope
from hive.physical import PhysicalObject


class MicroscopeDataModel(PhysicalObject):
	"""
	OME complient data-model for describing a microscope.
	Reference: https://www.openmicroscopy.org/Schemas/OME/2016-06/

	It subclasses the trappy-scopes `hive`module model `PhysicalObject`.
	"""
	def __init__(self, name, microscope_spec=None, objectives_spec=[]):
		"""
		name: Required for the trappy-scopes hive framework.
		microscope_spec : OEM specification for the microscope data model.
		objectives_spec: List of OEM specifications for objectives.
		
		#todo
		More options to specify :
		'generic_excitation_sources': [],
			'light_emitting_diodes': [],
			'filaments': [],
			'arcs': [],
			'lasers': [],
			'detectors': [],
			'filter_sets': [],
			'filters': [],
			'dichroics': [],
			'annotation_refs': [],
		"""

		self.instrument_ref = None ## todo Can this be changed?
		
		self.microscope = OMEMicroscope(**microscope_spec)
		self.objectives = []
		for objective in objectives_spec:
			self.objectives.append(Objective(**objective))
		
		self.instrument = Instrument(microscope=self.microscope, 
									  objectives=self.objectives)
		self.instrument_ref = InstrumentRef(id=self.instrument.id)
		super().__init__(name, persistent=False, **self.instrument.dict())


	def get_ref(self):
		self.instrument_ref = InstrumentRef(id=self.instrument.id)
		return self.instrument_ref