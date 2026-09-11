import numpy as np

class ColorIterator:
	def __init__(self, levels=5, ch=["r", "g", "b"]):
		self.levels = levels
		self.ch_list = ch

		self.it_list = []
		self.it = 0
		## Calculate all levels
		colortup = (0,0,0)

		for ch in self.ch_list:
			### Generate levels: rgb only
			if ch in "rgb":
				colors = {"r":0.0, "g":0.0, "b":0.0}	
				for i in range(levels):
					colors[ch] = np.round((3.3/levels)*i, 2)
					self.it_list.append((colors["r"], colors["g"], colors["b"]))

			if ch in "w":
				colors = {"r":0.0, "g":0.0, "b":0.0}	
				for i in range(levels):
					color = np.round((3.3/levels)*i, 2)
					self.it_list.append((color, color, color))
	def __iter__(self):
		return self

	def __next__(self):
		if self.it < len(self.it_list):
			color = self.it_list[self.it]
			self.it += 1
			return color
		else:
			raise StopIteration