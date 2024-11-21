import bpy
import bmesh
from mathutils import Vector
from . import utils_uv
from . import utils_bbox

class op(bpy.types.Operator):
	bl_idname = "uv.textools_island_align_sort"
	bl_label = "排序对齐"
	bl_description = "旋转UV岛到最小边界框并水平或垂直排序"
	bl_options = {'REGISTER', 'UNDO'}

	is_vertical: bpy.props.BoolProperty(
		name='垂直排列', 
		description="垂直或水平方向排列", 
		default=True
	)
	align: bpy.props.BoolProperty(
		name='对齐', 
		description="对齐UV岛方向", 
		default=True
	)
	padding: bpy.props.FloatProperty(
		name='间距', 
		description="UV岛之间的间距", 
		default=0.05
	)

	@classmethod
	def poll(cls, context):
		if not bpy.context.active_object:
			return False
		if bpy.context.active_object.type != 'MESH':
			return False
		if bpy.context.active_object.mode != 'EDIT':
			return False
		return True

	def execute(self, context):
		general_bbox = utils_bbox.BBox()
		all_groups = []
		update_obj = []
		bmeshes = []  # 保存bmesh对象以防止被释放

		# 获取选中的对象
		selected_objs = [obj for obj in context.selected_objects 
						if obj.type == 'MESH' and obj.mode == 'EDIT']

		if not selected_objs:
			self.report({'ERROR_INVALID_INPUT'}, "没有选中的网格物体")
			return {'CANCELLED'}

		for obj in selected_objs:
			bm = bmesh.from_edit_mesh(obj.data)
			uv_layer = bm.loops.layers.uv.verify()
			islands = utils_uv.get_selected_islands(bm, uv_layer, selected=False, extend_selection_to_islands=True)
			
			if not islands:
				continue
				
			for island in islands:
				bbox = utils_bbox.BBox.calc_bbox_uv(island, uv_layer)
				general_bbox.union(bbox)
				
				if self.align:
					angle = utils_uv.calc_min_align_angle(island, uv_layer)
					utils_uv.rotate_island(island, uv_layer, angle)
					bbox = utils_bbox.BBox.calc_bbox_uv(island, uv_layer)
					
				all_groups.append((island, bbox, uv_layer))
				
			bmeshes.append(bm)
			update_obj.append(obj)

		if not all_groups:
			return {'CANCELLED'}

		# 按最大边长排序
		all_groups.sort(key=lambda x: max(x[1].width, x[1].height), reverse=True)

		# 变换UV
		if self.is_vertical:
			margin_x = general_bbox.min.x
			margin_y = general_bbox.min.y

			for island, bbox, uv_layer in all_groups:
				delta = Vector((margin_x, margin_y)) - bbox.left_bottom
				utils_uv.translate_island(island, uv_layer, delta)
				margin_y += self.padding + bbox.height
		else:
			margin_x = general_bbox.min.x
			margin_y = general_bbox.min.y

			for island, bbox, uv_layer in all_groups:
				delta = Vector((margin_x, margin_y)) - bbox.min
				utils_uv.translate_island(island, uv_layer, delta)
				margin_x += self.padding + bbox.width

		# 更新网格
		for obj in update_obj:
			bmesh.update_edit_mesh(obj.data)

		return {'FINISHED'}

def register():
	bpy.utils.register_class(op)

def unregister():
	bpy.utils.unregister_class(op)

if __name__ == "__main__":
	register()
