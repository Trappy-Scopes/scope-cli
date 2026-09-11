from rich import print
import matplotlib.pyplot as plt
import raytracing
import logging as log
from importlib import import_module

from hive.physical import PhysicalObject

class OpticalAssembly(raytracing.OpticalPath):

    def __init__(self, name, units="mm", medium={"medium":"air", "ri":1.0003}, attribs={}, structure={}):
        """
        units: units in which distance is measured.
        attribs: the defining attributes of the optical assembly. Like magnification, resolution, etc
        structure: break down of all the optical components.

        Typical components: 
        1. light : light source
        2. distance: seperation distance
        3. sample: where sample is placed
        4. camera/image: where image forms.
        """
        self.name = name
        self.units = units
        self.medium = medium
        self.attribs = PhysicalObject(name, persistent=True, **dict(attribs))
        self.structure = structure
        self.construct_structure()

    def construct_structure(self, raise_exceptions=False):
        log.info("Scanning optical assembly...")
        import sys
        sys.path.append("'/Users/byatharth/code/Trappy-Scopes/scope-cli/")
        for device in self.structure:
            kind = list(device.keys())[0]
            
            ## Try importing the constructor
            try:
                package = kind.rsplit(".", 1)[0]
                object_ = kind.rsplit(".", 1)[1]
                constructor = getattr(import_module(package),object_)
            except ImportError as e:
                log.error(f"Import failed for device: {kind}")
                if raise_exceptions:
                    raise e
            ## Instantiate constructor
            try:
                build = constructor(*device["args"], **device["kwargs"])
                self.append(device, build)
                log.info(f"Device mounted successfully: {kind}")
            except Exception as e:
                log.error(f"Device mount failed: {kind} :: {str(e)}")
                if raise_exceptions:
                    raise e

    def simple_plot(self):
        """
        Draw a block diagram of lenses with distances between them.
        
        Parameters:
            lenses (list): List of lens names (e.g., ['L1', 'L2', 'L3'])
            distances (list): List of distances between lenses (length should be len(lenses)-1)
        """
        # Calculate cumulative positions
        positions = [0.0]
        
        def draw_distance(d):
            positions.append(positions[-1] + d)
            start = positions[-1]
            end = positions[-2]
            mid = (start + end) / 2
            ax.annotate('', xy=(start, 0.5), xytext=(end, 0.5),
                        arrowprops=dict(arrowstyle='<->', color='red'))
            
            # Label distance
            ax.text(mid, 0.6, f'd={d}', ha='center', 
                    bbox=dict(facecolor='white', alpha=0.8))

        def draw_lens(l):
            pos = positions[-1]
            ax.vlines(pos, -1, 1, lw=2, label=l)
            if len(positions) > 1:
                ax.text(pos, -1.5-(0.05*positions[-1]==positions[-2]), l, ha='center', fontsize=12)
            else:
                ax.text(pos, -1.5, l, ha='center', fontsize=12)

        # Create figure
        fig, ax = plt.subplots(figsize=(10, 3))
        
        
        for opto in self.structure:
            name = list(opto.keys())[0]
            attribs = opto.values()
            if name == "distance":
                dist = float(list(attribs)[0])
                draw_distance(dist)
            else:
                draw_lens(name)

            
        # Draw optical axis and finish
        total_length = positions[-1]
        ax.hlines(0, -0.1, total_length * 1.1, color='black', lw=1)

        # Configure plot
        ax.set_ylim(-2, 1.5)
        ax.set_xlim(-2, total_length + 2)
        ax.set_title('Lens System Diagram')
        ax.set_xlabel(f'Optical Axis [{self.units}]')
        ax.set_yticks([])
        ax.legend(loc='upper right')
        plt.tight_layout()
        plt.show()

    def __repr__(self):
        return self.attribs.__repr__()