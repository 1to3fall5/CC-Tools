import bpy
import bmesh
import numpy as np
from mathutils import Vector
from . import utils_uv

precision = 5

class op(bpy.types.Operator):
    bl_idname = "uv.textools_island_align_world"
    bl_label = "对齐世界"
    bl_description = "将选中的UV岛或面对齐到世界/重力方向"
    bl_options = {'REGISTER', 'UNDO'}

    bool_face : bpy.props.BoolProperty(
        name="每个面", 
        default=False, 
        description="独立处理每个面"
    )
    
    axis : bpy.props.EnumProperty(
        items= [
            ('-1', '自动', '检测要对齐的世界轴'), 
            ('0', 'X', '对齐到世界的X轴'), 
            ('1', 'Y', '对齐到世界的Y轴'), 
            ('2', 'Z', '对齐到世界的Z轴'),
        ], 
        name = "轴向", 
        default = '-1'
    )

    @classmethod
    def poll(cls, context):
        if bpy.context.area.ui_type != 'UV':
            return False
        if not bpy.context.active_object:
            return False
        if bpy.context.active_object.mode != 'EDIT':
            return False
        if not bpy.context.object.data.uv_layers:
            return False
        return True

    def execute(self, context):
        utils_uv.multi_object_loop(main, self, context)
        return {'FINISHED'}

def main(context):
    bm = bmesh.from_edit_mesh(bpy.context.active_object.data)
    uv_layer = bm.loops.layers.uv.verify()
    
    # 获取选中的UV岛
    selected_faces = []
    for face in bm.faces:
        if face.select:
            selected_faces.append(face)
    
    if not selected_faces:
        return
        
    # 对齐UV岛
    for face in selected_faces:
        # 计算面的法线
        normal = face.normal
        
        # 确定主轴
        if self.axis == '-1':  # 自动
            abs_normal = [abs(x) for x in normal]
            dominant_axis = abs_normal.index(max(abs_normal))
        else:
            dominant_axis = int(self.axis)
            
        # 计算旋转角度
        angle = utils_uv.calc_rotation_to_axis(normal, dominant_axis)
        
        # 旋转UV
        if self.bool_face:
            utils_uv.rotate_face(face, uv_layer, angle)
        else:
            island = utils_uv.get_island(bm, face, uv_layer)
            utils_uv.rotate_island(island, uv_layer, angle)
    
    bmesh.update_edit_mesh(bpy.context.active_object.data)

def register():
    bpy.utils.register_class(op)

def unregister():
    bpy.utils.unregister_class(op)

if __name__ == "__main__":
    register()
