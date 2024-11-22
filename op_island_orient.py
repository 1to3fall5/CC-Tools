import bpy
import bmesh
import math
from mathutils import Vector, Matrix
from . import utils_uv

class op(bpy.types.Operator):
    bl_idname = "cc.uv_island_orient"
    bl_label = "自动旋转"
    bl_description = "将UV岛按选中的边旋转到最接近的轴向"
    bl_options = {'REGISTER', 'UNDO'}
    
    @classmethod
    def poll(cls, context):
        if not context.active_object:
            return False
        if context.active_object.type != 'MESH':
            return False
        if context.active_object.mode != 'EDIT':
            return False
        if context.scene.tool_settings.use_uv_select_sync:
            return False
        if context.scene.tool_settings.uv_select_mode != 'EDGE':
            return False
        return True

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        uv_layer = bm.loops.layers.uv.verify()

        # 存储选择状态
        selected_uvs = []
        for face in bm.faces:
            for loop in face.loops:
                if loop[uv_layer].select:
                    selected_uvs.append(loop)

        # 获取选中的UV边
        selected_edges = []
        for face in bm.faces:
            for loop in face.loops:
                if loop[uv_layer].select and loop.link_loop_next[uv_layer].select:
                    selected_edges.append((loop, loop.link_loop_next))

        if not selected_edges:
            self.report({'WARNING'}, "请选择UV边")
            return {'CANCELLED'}

        # 处理每个选中的边
        for edge_start, edge_end in selected_edges:
            # 获取边的UV坐标
            uv_start = edge_start[uv_layer].uv
            uv_end = edge_end[uv_layer].uv
            
            # 计算边的方向向量
            edge_vector = uv_end - uv_start
            edge_length = edge_vector.length
            
            if edge_length < 0.0001:  # 避免处理过短的边
                continue
                
            # 计算与X轴和Y轴的夹角
            angle = math.atan2(edge_vector.y, edge_vector.x)
            
            # 计算到四个主要方向的角度差的绝对值
            angles = [
                (0, abs(angle)),                    # 到X轴正向的角度
                (math.pi/2, abs(angle - math.pi/2)),   # 到Y轴正向的角度
                (math.pi, abs(abs(angle) - math.pi)),  # 到X轴负向的角度
                (-math.pi/2, abs(angle + math.pi/2)),  # 到Y轴负向的角度
            ]
            
            # 找到最小角度差对应的目标角度
            target_angle, min_diff = min(angles, key=lambda x: x[1])
            angle_diff = target_angle - angle

            # 获取边的中点作为旋转中心
            pivot = (uv_start + uv_end) / 2

            # 选择整个UV岛
            bpy.ops.uv.select_all(action='DESELECT')
            edge_start[uv_layer].select = True
            edge_end[uv_layer].select = True
            bpy.ops.uv.select_linked()  # 选择相连的UV
            
            # 获取选中的UV点并进行旋转
            selected_points = []
            for face in bm.faces:
                for loop in face.loops:
                    if loop[uv_layer].select:
                        selected_points.append(loop)
            
            # 创建旋转矩阵
            rot_mat = Matrix.Rotation(angle_diff, 2)
            
            # 应用旋转
            for loop in selected_points:
                uv = loop[uv_layer].uv
                # 相对于pivot点进行旋转
                uv_local = uv - pivot
                uv_rotated = rot_mat @ uv_local
                loop[uv_layer].uv = uv_rotated + pivot

        # 恢复原始选择
        bpy.ops.uv.select_all(action='DESELECT')
        for loop in selected_uvs:
            loop[uv_layer].select = True

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}

def register():
    bpy.utils.register_class(op)

def unregister():
    bpy.utils.unregister_class(op)

if __name__ == "__main__":
    register()