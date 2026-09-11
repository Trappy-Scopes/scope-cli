import os

from rich import print
from rich.panel import Panel

from rayoptics.environment import OpticalModel, open_model, PupilSpec, InteractiveLayout, WvlSpec
import matplotlib.pyplot as plt

from rayoptics.elem.surface import *
from rayoptics.seq.gap import Gap
from rayoptics.seq.interface import Interface

class OpticalAssembly(OpticalModel):
	"""
	LED -> Thin Lens -> Diffuser --> Condensor --> ObjPlane(Dummy) --> TubeLens --> 
	"""



	def __init__(self, scopeid):

		super().__init__()
		self.sm = self['seq_model']
		self.osp = self['optical_spec']
		self.pm = self['parax_model']
		self.em = self['ele_model']
		self.pt = self['part_tree']

		self.system_spec.title = scopeid
		self.system_spec.dimensions = 'mm'


		self.osp['pupil'] = PupilSpec(self.osp, key=['object', 'epd'], value=5)
		self.sm.do_apertures = False
		self.sm.gaps[0].thi=5

	def add_zeemax(self, name, flip=False, t=10, **kwargs):
		if not name.lower().endswith(".zmx"):
			name = name + ".zmx"
		#opm, info = open_model(os.path.join("optics/zeemax_models", name), info=True)
		idx = self.sm.get_num_surfaces()
		self.add_from_file(os.path.join("optics/zeemax_models", name), t=t, label=name, **kwargs)
		
		#print(Panel(info, title=name))
		self.update_model()
		if flip:
			self.flip(idx, self.sm.get_num_surfaces())
			self.update_model()
		#return opm

	def specify_spectrum(self, *wvls_nm):
		spectrum = [(wvl, 1.0) for wvl in wvls_nm]
		self.osp['wvls'] = WvlSpec(spectrum, ref_wl=1)

	def create_zoom_lens(spacing=20):
	    opm = OpticalModel()
	    
	    # Add an aperture stop
	    opm.seq_model.gaps[0].thi = 0.0  # Set first gap thickness (aperture stop)
	    
	    # Add first lens (biconvex lens)
	    opm.seq_model.add_surface([0.0, 5.0, 1.516, 64.1])
	    opm.seq_model.add_surface([-0.02, spacing, 1.000, 64.1])  # Adjustable spacing

	    # Add second lens (biconvex lens)
	    opm.seq_model.add_surface([0.02, 5.0, 1.516, 64.1])
	    opm.seq_model.add_surface([-0.02, 100.0, 1.00, 64.1])  # Distance to image plane

	def add_component(self, component, pre_gap=None, post_gap=None, gap_medium=None):
		
		self.opm.add_lens()

	def add_detector(self, dims):
		#ifc = Interface(interact_mode='dummy', max_ap=min(dims))
		rect = Rectangular(dims[0]/2, dims[1]/2)
		#self.add_part(Rectangular(dims[0]/2, dims[1]/2), gap=Gap(t=0))
		self.em.add_element(rect)
		self.update_model()

	def add_sample(self, trap):
		
		if trap.material == "pdms":
			## PDMS
			optics.sm.add_surface([0.0, 7, trap.material_ri, 35])
			optics.sm.add_surface([0.0, trap.thi, 1.3325, 35]) ## Water
			optics.sm.add_surface([0.0, 0])

		
		## Glass -> soda lime 1mm thickness
		optics.sm.add_surface([0., 1, 1.5234, 75])
		

		## Sample stage aparture
		optics.sm.add_surface([0.0, 10.0, 'air', 75], max_aperture=50.0, label="Sample stage")
		optics.update_model()


optics = OpticalAssembly("scopeid")



## 1. LED - Probably a ray bundle
optics.specify_spectrum(627.5, 525.0, 467.5)
#RayBundle(opt_model, fld, fld_label, wvl, start_offset

## 2. Plastic asphere - add later
optics.add_zeemax("LA1024", flip=True, t=4)
	

## 3. Thorlabs asphere
optics.add_zeemax("ACL2520U", flip=True, t=20.1)
optics.sm.list_model()

## 4. Add sample stage -> Later add PDMS and glass

## PDMS
optics.sm.add_surface([0., 7, 1.43, 35])
optics.sm.add_surface([0., 0])

## Glass
optics.sm.add_surface([0., 1, 1.516, 75])
#optics.add_dummy_plane(t=10)

## Sample stage aparture
optics.sm.add_surface([0.0, 10.0, 'air', 75], max_aperture=50.0, label="Sample stage")
optics.update_model()


## 5. Add tube lens
optics.add_zeemax("LA1024", flip=False, t=10)
optics.add_zeemax("LA1024", flip=False, t=4)
optics.add_zeemax("LA1024", flip=False, t=10)
optics.add_zeemax("LA1024", flip=False, t=4)
optics.update_model()


## Camera
#optics.add_detector([6.287, 4.712])

optics.sm.list_model()
## Plot
layout_plt1 = plt.figure(FigureClass=InteractiveLayout, opt_model=optics,
                        do_draw_rays=True, do_paraxial_layout=False,
                        is_dark=True).plot()
plt.show()

