import bpy
import bmesh
from mathutils import Vector
from bpy.props import BoolProperty, IntProperty, FloatProperty

class op(bpy.types.Operator):
    bl_idname = "uv.textools_island_relax"
    bl_label = "松弛UV"
    bl_description = "平滑UV岛的分布"
    bl_options = {'REGISTER', 'UNDO'}
    
    iterations: IntProperty(
        name="迭代次数",
        description="松弛操作的迭代次数",
        default=50,
        min=5,
        max=600,
        soft_min=50,
        soft_max=200
    )
    
    border_blend: FloatProperty(
        name="边界混合",
        description="边界点的混合强度",
        default=0.1,
        min=0,
        soft_min=0,
        soft_max=1
    )

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and context.active_object and context.active_object.type == 'MESH'

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        uv_layer = bm.loops.layers.uv.verify()
        
        # 存储原始UV坐标
        original_uvs = {}
        for face in bm.faces:
            for loop in face.loops:
                if loop[uv_layer].select:
                    uv_key = (round(loop[uv_layer].uv.x, 6), round(loop[uv_layer].uv.y, 6))
                    if uv_key not in original_uvs:
                        original_uvs[uv_key] = []
                    original_uvs[uv_key].append(loop)

        # 使用minimize_stretch进行松弛
        bpy.ops.uv.minimize_stretch(iterations=self.iterations)
        
        # 如果有边界点，进行混合
        if original_uvs:
            # 对边界点进行混合
            for uv_key, loops in original_uvs.items():
                is_boundary = False
                for loop in loops:
                    if loop.edge.is_boundary:
                        is_boundary = True
                        break
                
                if is_boundary:
                    # 获取当前位置
                    current_pos = loops[0][uv_layer].uv.copy()
                    original_pos = Vector(uv_key)
                    
                    # 混合位置
                    blended_pos = original_pos.lerp(current_pos, self.border_blend)
                    
                    # 应用混合后的位置
                    for loop in loops:
                        loop[uv_layer].uv = blended_pos

            # 再次应用minimize_stretch
            bpy.ops.uv.minimize_stretch(iterations=self.iterations)

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}

def register():
    bpy.utils.register_class(op)

def unregister():
    bpy.utils.unregister_class(op)

if __name__ == "__main__":
    register() 