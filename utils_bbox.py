import math
from mathutils import Vector


class BBox:
	@classmethod
	def calc_bbox(cls, coords):
		xmin = math.inf
		xmax = -math.inf
		ymin = math.inf
		ymax = -math.inf

		for x, y in coords:
			if xmin > x:
				xmin = x
			if xmax < x:
				xmax = x
			if ymin > y:
				ymin = y
			if ymax < y:
				ymax = y
		return cls(xmin, xmax, ymin, ymax)

	@classmethod
	def calc_bbox_uv(cls, faces, uv_layer, are_loops=False):
		coords = []
		if are_loops:
			for loop in faces:
				coords.append(loop[uv_layer].uv)
		else:
			for face in faces:
				for loop in face.loops:
					coords.append(loop[uv_layer].uv)
		return cls.calc_bbox(coords)

	def __init__(self, xmin=math.inf, xmax=-math.inf, ymin=math.inf, ymax=-math.inf):
		self.xmin = xmin
		self.xmax = xmax
		self.ymin = ymin
		self.ymax = ymax

	@property
	def min(self):
		return Vector((self.xmin, self.ymin))

	@property
	def max(self):
		return Vector((self.xmax, self.ymax))

	@property
	def center(self):
		"""返回边界框的中心点"""
		return Vector(((self.xmin + self.xmax) / 2, (self.ymin + self.ymax) / 2))

	@property
	def width(self):
		return self.xmax - self.xmin

	@property
	def height(self):
		return self.ymax - self.ymin

	@property
	def max_lenght(self):
		return max(self.width, self.height)

	def union(self, other):
		"""合并两个边界框"""
		self.xmin = min(self.xmin, other.xmin)
		self.xmax = max(self.xmax, other.xmax)
		self.ymin = min(self.ymin, other.ymin)
		self.ymax = max(self.ymax, other.ymax)

	def update_point(self, xy):
		"""更新边界框以包含新的点"""
		if xy[0] < self.xmin:
			self.xmin = xy[0]
		if xy[0] > self.xmax:
			self.xmax = xy[0]
		if xy[1] < self.ymin:
			self.ymin = xy[1]
		if xy[1] > self.ymax:
			self.ymax = xy[1]

	def update(self, coords):
		"""更新边界框以包含一组新的点"""
		for x, y in coords:
			if x < self.xmin:
				self.xmin = x
			if x > self.xmax:
				self.xmax = x
			if y < self.ymin:
				self.ymin = y
			if y > self.ymax:
				self.ymax = y
