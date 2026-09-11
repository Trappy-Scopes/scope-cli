# +----------------------------------------------------------------------------+
# |                                                                            |
# |       .-"""""""-.             ___                                          |
# |     .'           '.       _,~"                                             |
# |    /          .##.  \   ,~"                                                |
# |   |           '##'  |~"                                                    |
# |    \                /~,                                                    |
# |     '.            .'   "~,_                                                |
# |       '-........-'        "~,__                                            |
# |                                                                            |
# | Author    : Yatharth Bhasin (yatharth1997+ts@gmail.com)                    |
# | Date      : June 2026                                                      |
# | Copyright (c) 2026 Yatharth Bhasin                                         |
# | License-Identifier: MIT                                                    |
# +----------------------------------------------------------------------------+

__description__ = \
"""Script to track and segment moving cells on the fly.
Functions Added
---------------
`add_cell_object()`
`record_short_video(filename, time_s=10)`
`track_sample(filename="sample_video.mjpeg", fps=25, 
			 time_s=3, no_processes=4, minmass=0.2,
			  pix_size_um=3.1, stub_size_s=2)`
`view_cells()` : Use fim to open saved tracks.
Complete workflow
-----------------

Use `see_cells(filename="sample_video.mjpeg", fps=25, time_s=3, 
			   no_processes=4, minmass=0.2, pix_size_um=3.1, 
			   stub_size_s=2)`

+ Add cell object --> Record Video --> Track and Segment --> Open Plots"""



def __installer__():
	"""
	Installation path for the specific libraries: trackpy and pims. Does not include scikit-image.
	For Raspberry Pi OS!
	Call at your own risk (--break-system-packages)!
	"""
	import os
	for lib in ["trackpy", "pims", "numba"]:
		os.system(f"sudo pip install {lib} --break-system-packages")




import numpy as np
import errno
import os

import matplotlib.pyplot as plt
import trackpy as tp
#tp.enable_numba()
import pims
import pandas as pd
import datetime


from skimage import measure
from skimage.filters import threshold_otsu
from skimage.filters import threshold_local

from rich.pretty import Pretty
from rich.panel import Panel

## Trappy-Scopes Imports
from hive.physical import PhysicalObject

global __live_cell_save__path__
__live_cell_save__path__ = "."

def add_cell_object():
	"""Add a cell object to the ScopeAssembly."""
	global scope
	cell = PhysicalObject("cell", no_cells=0, tracks=None, speeds={}, sizes={}, gauss_fits={})
	scope.add_device("cell", cell)
	print("Added cell(s) object:", scope.cell)



def record_short_video(filename, time_s=10):
	"""Record a short video to capture moving cells"""
	global exp, scope

	if exp is None:
		raise Exception("No experiment is open.")
	if not exp.active:
		raise Exception("No experiment is open.")

	scope.cam.close()

	### Capture
	try:
		scope.cam.open()
		scope.cam.configure()
		scope.cam.read("vid_mjpeg_tpts", 
					   filename,
					   tsec=time_s, 
					 	show_preview=False,
						quality=100)
		scope.cam.close()
	except Exception as e:
		scope.cam.close()
		exp.note(f"Camera failed to capture video for live tracks")
		print(e)
	finally:
		scope.cam.close()
		scope.cam.open()
		scope.cam.configure()
		print("Camera open for previews.")


	## TOTO Should open the camera maybe?

def track_sample(filename="sample_video.mjpeg", fps=25, time_s=3, no_processes=4, minmass=0.1,
				 pix_size_um=3.1, stub_size_s=2):
	"""Function to track and segment moving cells.
	   If the file is not found, it uses a fixed local path on `MDEv` to test the script. It will fail on other systems.
	   A longer video will be used to calculate the backgrounds, if passed.

	   Involves a conversion step to .avi from .mjpeg.
	""" 
	global __live_cell_save__path__
	## For testing only
	if not os.path.exists(filename):
		filename = "/Users/byatharth/Downloads/55f3930aa3_2026_04_09__12_25_48__1775733948587604583__split_0_10sec.mjpeg"

	## Convert to avi
	print("Converting video to avi...")
	avi_filename = filename.replace(".mjpeg", ".avi")
	os.system(f"ffmpeg -framerate 25 -f mjpeg -i {filename}  -vf yadif -c:v rawvideo {avi_filename} -y")

	if not os.path.exists(avi_filename):
		raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), avi_filename)

	@pims.pipeline
	def gray(image):
		return image[:, :, 0]

	print("Loading frames...")
	frames = gray(pims.open(avi_filename))
	print("Frames in video:", len(frames))
	n_max = len(frames)

	print("Loading BG model...")
	global background
	background = None
	acc, n = None, 0
	for frame in frames:
		frame = frame.astype(np.float32)
		if acc is None:
			acc = np.zeros_like(frame)
		acc += frame
		n += 1
		if n >= n_max:
			break
	background = acc / n / 255.0
	print("BG model calculated...")

	@pims.pipeline
	def bg_subtract(frame):
		frame = frame.astype(np.float32) / 255.0
		frame = frame - background
		frame = frame * (-1.0)
		return np.clip(frame, 0.0, 1.0)


	bgs = bg_subtract(frames)
	bgs = exp.track("Background subtraction", list, bgs[:fps * time_s], description="Doing background subtraction on a subset of frames")
	print("BGS frames:", len(bgs))

	tp.quiet()
	f = exp.track("Live tracking", tp.batch, bgs[:], 21, minmass=minmass, invert=False, processes=no_processes, separation=10, description="Tracking features in every frame")

	t = exp.track("Linking tracks", tp.link, f, 4, memory=3, description="Linking features into trajectories.")

	trajs = exp.track("Filtering srubs", tp.filter_stubs, t, fps * stub_size_s, description=f"Filtering trajectories that are less than {stub_size_s} seconds.")

	trajs = trajs.reset_index(drop=True)
	trajs["particle"] = trajs.groupby("particle").ngroup()
	no_detected = len(trajs.particle.unique())

	if no_detected > 0:

		fig, ax = plt.subplots(figsize=(10, 10))
		ax.set_title(f"Detected tracks: {no_detected}")
		tp.plot_traj(trajs, superimpose=frames[0], ax=ax, label=True)
		fig.savefig(f"{__live_cell_save__path__}/detected_tracks.png")
		print("Detected tracks:", no_detected)

		if "optics" not in scope:
			print("Creating dummy optics object")
			optics = PhysicalObject("optics", magnification=1.5)
			scope.add_device("optics", optics)

		magnification = scope.optics["magnification"]
		um_per_pix = pix_size_um / magnification

		## Speeds
		speeds = {}
		for particle, group in trajs.groupby("particle"):
			group = group.sort_values("frame")
			dx, dy = group["x"].diff(), group["y"].diff()
			dt = group["frame"].diff() / fps
			displacement_um = np.sqrt(dx**2 + dy**2) * um_per_pix
			speeds[particle] = float((displacement_um / dt).mean())

		## sRGB linearisation
		def srgb_to_linear(img):
			mask = img <= 0.04045
			linear = np.empty_like(img, dtype=np.float32)
			linear[mask]  = img[mask] / 12.92
			linear[~mask] = ((img[~mask] + 0.055) / 1.055) ** 2.4
			return linear

		## Gaussian model
		def gaussian2d(xy, amp, x0, y0, sigma, bg):
			x, y = xy
			return (amp * np.exp(-((x-x0)**2 + (y-y0)**2) / (2*sigma**2)) + bg).ravel()

		## Numerical IC in 6um radius
		radius_px = 6.0 / um_per_pix
		Y, X = np.indices((50, 50))
		circle_mask = (X - 25)**2 + (Y - 25)**2 < radius_px**2

		from scipy.optimize import curve_fit
		yy, xx = np.indices((50, 50))
		t0 = trajs.reset_index(drop=True)

		## Per-frame Gaussian fits
		gauss_fits = {}
		display_patches = {}

		for particle_id, group in t0.groupby("particle"):
			# Store first frame patch for display
			first_row = group.iloc[0]
			cx, cy = int(first_row["x"]), int(first_row["y"])
			first_patch = srgb_to_linear(frames[int(first_row["frame"])][cy-25:cy+25, cx-25:cx+25].astype(np.float32))
			if first_patch.shape == (50, 50):
				display_patches[particle_id] = first_patch

			particle_fits = []
			for _, row in group.iterrows():
				cx, cy = int(row["x"]), int(row["y"])
				patch = srgb_to_linear(frames[int(row["frame"])][cy-25:cy+25, cx-25:cx+25].astype(np.float32))
				if patch.shape != (50, 50):
					continue
				p0 = [patch.min() - patch.max(), 25, 25, 3, patch.max()]
				try:
					popt, _ = curve_fit(gaussian2d, (xx, yy), patch.ravel(), p0=p0)
					amp, x0, y0, sigma, bg = popt
					if abs(sigma) > 20 or bg <= 0:
						continue
					# Numerical IC in 6um radius, normalised by bg
					border = np.concatenate([patch[0,:], patch[-1,:], patch[:,0], patch[:,-1]])
					bg_measured = np.median(border)
					ic_numerical = (bg_measured - patch[circle_mask]).sum() / bg_measured if bg_measured > 0 else np.nan
					particle_fits.append({
						"sigma_um":            abs(sigma) * um_per_pix,
						"contrast":            abs(amp) / bg,
						"integrated_contrast": ic_numerical,
					})
				except Exception:
					continue
				if len(particle_fits) >= 100:
					break

			if not particle_fits:
				continue

			df_fits = pd.DataFrame(particle_fits)
			gauss_fits[particle_id] = {
				"sigma_um":                df_fits["sigma_um"].mean(),
				"sigma_um_std":            df_fits["sigma_um"].std(),
				"contrast":                df_fits["contrast"].mean(),
				"contrast_std":            df_fits["contrast"].std(),
				"integrated_contrast":     df_fits["integrated_contrast"].mean(),
				"integrated_contrast_std": df_fits["integrated_contrast"].std(),
				"n_frames":                len(df_fits),
			}

		for pid, fit in gauss_fits.items():
			print(f"p{pid}: σ={fit['sigma_um']:.2f}±{fit['sigma_um_std']:.2f}µm  "
				  f"C={fit['contrast']:.3f}±{fit['contrast_std']:.3f}  "
				  f"IC={fit['integrated_contrast']:.3f}±{fit['integrated_contrast_std']:.3f}  "
				  f"n={fit['n_frames']}")

		## Plot
		n_panels = len(gauss_fits)
		fig, axes = plt.subplots(2, n_panels//2 + 1, figsize=(16, 6))
		axes = axes.flatten()

		for ax, (particle_id, fit) in zip(axes, gauss_fits.items()):
			patch = display_patches.get(particle_id)
			if patch is not None:
				ax.imshow(patch, cmap="gray")

			# Reference circles at 6µm and 12µm
			cx_c, cy_c = 25, 25
			for radius_um, color in [(6, "cyan"), (12, "yellow")]:
				ax.add_patch(plt.Circle((cx_c, cy_c), radius_um / um_per_pix,
										color=color, fill=False, linewidth=0.5))

			# Radius of gyration
			rg_px = trajs[trajs["particle"] == particle_id]["size"].dropna().median()
			ax.add_patch(plt.Circle((cx_c, cy_c), rg_px, color="blue", fill=False, linewidth=0.5))
			color = "black"
			if speeds[particle_id] > 80 and fit['contrast'] < 0.95:
				color = "green"

			if speeds[particle_id] < 80 and fit['contrast'] >= 0.95:
				color = "red"

			ax.set_title(f"p{particle_id}  {speeds[particle_id]:.1f}µm/s\n"
						 f"σ={fit['sigma_um']:.1f}±{fit['sigma_um_std']:.1f}µm\n"
						 f"C={fit['contrast']:.2f}±{fit['contrast_std']:.2f}\n"
						 f"IC={fit['integrated_contrast']:.3f}±{fit['integrated_contrast_std']:.3f}",
						 fontsize=7, color=color)
			ax.axis("off")

		for ax in axes[n_panels:]:
			ax.axis("off")
		plt.tight_layout()
		fig.savefig(f"{__live_cell_save__path__}/detected_cells.png")
		#plt.show()

		if not "cell" in scope:
			add_cell_object()
		scope.cell["no_cells"]   = no_detected
		trajs.to_csv(os.path.join(__live_cell_save__path__, "tracks.csv"))
		scope.cell["speeds"]     = speeds
		scope.cell["sizes"]      = {pid: fit["sigma_um"] for pid, fit in gauss_fits.items()}
		scope.cell["gauss_fits"] = gauss_fits

	else:
		scope.cell["no_cells"] = 0
		scope.cell["speeds"]   = {}
		scope.cell["sizes"]    = {}
		scope.cell["gauss_fits"] = {}
		print(Panel("No cells found!", style="white on red"))

def view_cells():
	"""Visualise the generated plots using fim in terminal"""
	paths = [os.path.join(__live_cell_save__path__, img) for img in ["detected_tracks.png", "detected_cells.png"]]
	from core.utilities.fim import fim
	fim(paths)

def view_cells_trapped():
	"""View tracked cells - step 0."""
	paths = [os.path.join("trapped", img) for img in ["detected_tracks.png", "detected_cells.png"]]
	from core.utilities.fim import fim
	fim(paths)

def view_cells_checkpoint1():
	"""View checkpoint1 tracked cells - step 1."""
	paths = [os.path.join("checkpoint1", img) for img in ["detected_tracks.png", "detected_cells.png"]]
	from core.utilities.fim import fim
	fim(paths)

def view_cells_checkpoint2():
	"""View checkpoint2 tracked cells - step 2."""
	paths = [os.path.join("checkpoint2", img) for img in ["detected_tracks.png", "detected_cells.png"]]
	from core.utilities.fim import fim
	fim(paths)


def see_cells(filename="sample_video.mjpeg", fps=25, record_time_s=10, time_s=3, 
			   no_processes=4, minmass=0.1, pix_size_um=3.1, 
			   stub_size_s=2, view=True):
	"""
	Add cell object --> Record Video --> Track and Segment --> Open Plots
	"""

	global exp, scope, __live_cell_save__path__
	if exp is None:
		raise Exception("Exp not open")
	if not exp.active:
		raise Exception("Exp not open")

	if "optics" not in scope:
		raise Exception("Optical properties are undefined. Do alignment first.")

	if "cell" not in scope:
		add_cell_object()
	__live_cell_save__path__ = os.path.dirname(filename)
	os.makedirs(os.path.dirname(filename), exist_ok=True)
	record_short_video(filename, record_time_s)

	track_sample(filename, fps=fps, time_s=time_s, 
			   no_processes=no_processes, minmass=minmass, pix_size_um=pix_size_um, 
			   stub_size_s=stub_size_s)
	if view:
		view_cells()


## Higher order functions
def open_trap():
	"""Mark the trap open and trigger cancellation of checkpoints"""
	global exp, scope
	exp.log("open_trap")
	exp.schedule.clear()
	if "cell" in scope:
		scope.cell["speed_log"] = []
	scope.beacon.off()
	exp.__save__()

def checkpoint(name, single_cell_exception=False):
	"""Checkpoint cell count and cell speed."""
	from expframework.experiment import Experiment
	from hive.assembly import ScopeAssembly
	exp = Experiment.current
	scope = ScopeAssembly.current
	exp.clocks = name
	see_cells(filename=f"{name}/sample_video.mjpeg", view=False)

	scope.beacon.off()

	no_cells = scope.cell["no_cells"]
	if single_cell_exception:
		if no_cells > 1:
			scope.beacon.blink()
			print(Panel(Pretty("MORE THAN ONE CELL!"), title="Live track", style="white on red"))
		if no_cells == 1:
			if not "speed_log" in scope.cell.attribs:
				scope.cell["speed_log"] = []
			scope.cell["speed_log"].append(next(iter(scope.cell["speeds"].values())))

	if no_cells == 0:
		scope.beacon.blink()
		print(Panel(Pretty("No CELL DETECTED!"), title="Live track", style="white on red"))

	else:
		print(Panel(Pretty({k:v for k, v in scope.cell.params.items() if k in ["no_cells", "sizes", "speeds"]}), title=f"Cell list -- {name}", style="white on red"))


def trapped_many(single_cell_exception=False, schedule_checkpoint_mins=10):
	"""Mark that the cell is trapped and trigger cell count and speed calculation."""
	global exp, scope
	exp.clocks = "trapped"
	exp.log("trap_closed")
	see_cells(filename="trapped/sample_video.mjpeg", view=False)

	scope.beacon.off()

	no_cells = scope.cell["no_cells"]
	if single_cell_exception:
		if no_cells > 1:
			scope.beacon.blink()
			print(Panel(Pretty("MORE THAN ONE CELL!"), title="Live track", style="white on red"))
		if no_cells == 1:
			if not "speed_log" in scope.cell.attribs:
				scope.cell["speed_log"] = []
			scope.cell["speed_log"].append(next(iter(scope.cell["speeds"].values())))

	if no_cells == 0:
		scope.beacon.blink()
		print(Panel(Pretty("No CELL DETECTED!"), title="Live track", style="white on red"))

	else:
		print(Panel(Pretty({k:v for k, v in scope.cell.params.items() if k in ["no_cells", "sizes", "speeds"]}), title="Cell list", style="white on red"))

	if schedule_checkpoint_mins > 0:
		exp.schedule.every(10).minutes.until(datetime.timedelta(minutes=schedule_checkpoint_mins + 1)).do(checkpoint, "checkpoint1", single_cell_exception=single_cell_exception).tag("checkpoint1")
		exp.schedule.every(20).minutes.until(datetime.timedelta(minutes=schedule_checkpoint_mins*2 + 1)).do(checkpoint, "checkpoint2", single_cell_exception=single_cell_exception).tag("checkpoint2")
		print("Scheduled 2 checkpoints")


def trapped_one(schedule_checkpoint_mins=10):
	"""Just a single cell version of trapped_many."""
	trapped_many(single_cell_exception=True, schedule_checkpoint_mins=schedule_checkpoint_mins)



