
import numpy as np
import os
from skimage import draw, morphology
from skimage.measure import centroid
from matplotlib.gridspec import GridSpec

from scripts.alignmenttools.__alignmentfuncs__ import *

SAMPLE_IMAGE_PATH = os.path.join(os.path.dirname(__file__), "scripts", "alignmenttools", "sample_frame.png")

global calib_image
calib_image = None


from core.utilities.fim import fim

def create_calib_exp():
	global exp
	exp = Experiment.Construct(["frame_alignment", "calibration"])

def take_calib_image():
	global scope
	scope.cam.read("img", "calib_image.png", tsec=3, show_preview=True)
	print(f"Calibration image taken: \"calib_image.png\"")

def load_calib_image(path=SAMPLE_IMAGE_PATH, channel_no=0):
	from PIL import Image
	calib_path = "calib_image.png"
	if os.path.exists(calib_path):
		return np.array(Image.open(calib_path))[:,:,channel_no]
	else:
		return np.array(Image.open(path))

def view_all(filenames=["alignment/centroids_plot.png", "alignment/trap_wall_profile.png", 
					    "alignment/intensity_homogeneity.png", "alignment/contrast_histogram.png"]):
	fim(filenames)


def start_alignment(path=SAMPLE_IMAGE_PATH, show=False):
	global scope
	
	take_calib_image()
	calib_image = load_calib_image(path=path)

	print("Beginning frame alignement tests")

	print("Step 1: Trap detection")
	thresholds = iterate_thresholds(calib_image, 400)
	print(thresholds)
	circles, regions = detect_circles(calib_image, 2, min_diameter=400, **thresholds)
	print(circles)
	fig, ax = trap_detection_plot(calib_image, circles, regions)
	radii = [circles[1][2], circles[0][2]]
	reff = (radii[0]+radii[1])/2
	xc = circles[0][0]
	yc = circles[0][1]
	ax.set_title(fr"Trap radii: {radii[0]}px to {radii[1]}px; $r_e$ : {reff:.1f}\nThresholds: {str(thresholds)}")
	center_dev_x = np.abs(xc - calib_image.shape[0]/2)
	center_dev_y = np.abs(yc - calib_image.shape[1]/2)

	magnification = define_magnification(reff)
	ax.scatter([xc], [yc], marker="x", label="Trap center", color="red")
	ax.scatter([calib_image.shape[0]/2], [calib_image.shape[1]/2], marker="x", label="FOV center", color="blue")
	
	_, intensity_centroid = image_centroid(calib_image)
	ax.scatter([intensity_centroid[1]], [intensity_centroid[0]], marker="x", label="Intensity center", color="yellow")
	
	## Add the deviation circle
	deviation_threshold = 50
	dev_circle = plt.Circle((int(calib_image.shape[0]/2), int(calib_image.shape[1]/2)), deviation_threshold, color='blue', fill=False)
	ax.add_patch(dev_circle)

	ax.legend(loc='upper right')
	fig.suptitle(fr"""Trap centring errors: $\Delta_x$:{center_dev_x}; $\Delta_y$:{center_dev_y}
		Magnification:{magnification:.2f}X;
		Centering-threshold-radius: {deviation_threshold}px""")
	scope.optics["magnification"] = magnification
	print(f"Magnification: {magnification:.2f}X")
	print("Emitting: centroids_plot.png")
	os.makedirs("alignment", exist_ok=True)
	fig.savefig("alignment/centroids_plot.png")
	if show:
		fig.show()
	## Add scope information


	print("Step 2: Profile trap boundaries for angular misalignment")
	fig, ax, packet = profile_trap_boundaries(calib_image, int(xc), int(yc), int(reff))
	print("Emitting: trap_wall_profile.png")
	fig.savefig("alignment/trap_wall_profile.png")
	if show:
		fig.show()
	## Update information in the scope settings


	print("Step 3: Intensity centroid and illumination homogeneity")
	fig, centroid_ = image_centroid(calib_image, reff=int(reff))
	print("Emitting: intensity_homogeneity.png")
	fig.savefig("alignment/intensity_homogeneity.png")
	if show:
		fig.show()

	print("Step 4: Intensity histograms and contrast")
	fig = contrast_histogram(calib_image, bins=256, lower_percentile_threshold=1.0)
	print("Emitting: contrast_histogram.png")
	fig.savefig("alignment/contrast_histogram.png")
	if show:
		fig.show()



if __name__ == "__main__":
	print("Please take the calibration image using: take_calib_image()")
	print("Then load the image using: `calib_image = load_calib_image()`")
	print("It is recommended to create a Calibration experiment using: create_calib_exp()")
	print("Start alignment using: start_alignment()")
	print("Use `view_all()` to view all images in fim.")

