import bpy
from bpy.types import Operator
from bpy.props import FloatProperty

class MESH_OT_smooth_selected_faces(Operator):
    """清除所选面的锐边并设置区域环为锐边"""
    bl_idname = "mesh.smooth_selected_faces"
    bl_label = "平滑所选面并设置边界"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "请选择一个网格物体")
            return {'CANCELLED'}
        
        # 设置物体为 Shade Smooth
        bpy.ops.object.shade_smooth()
            
        bpy.ops.object.mode_set(mode='EDIT')
        # 存储当前选择模式
        current_mode = tuple(context.tool_settings.mesh_select_mode)
        
        # 切换到面选择模式
        bpy.ops.mesh.select_mode(type='FACE')
        
        # 清除所选面的锐边
        bpy.ops.mesh.mark_sharp(clear=True)
        
        # 选择区域边界环
        bpy.ops.mesh.region_to_loop()
        
        # 将边界设为锐边
        bpy.ops.mesh.mark_sharp()
        
        # 恢复原来的选择模式
        context.tool_settings.mesh_select_mode = current_mode
        
        return {'FINISHED'}

class MESH_OT_mark_sharp_by_angle(Operator):
    """基于角度设置锐边"""
    bl_idname = "mesh.mark_sharp_by_angle"
    bl_label = "按角度设置锐边"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "请选择一个网格物体")
            return {'CANCELLED'}
        
        # 设置物体为 Shade Smooth
        bpy.ops.object.mode_set(mode='OBJECT')
        bpy.ops.object.shade_smooth()
        
        # 存储当前模式
        current_mode = obj.mode
        if current_mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        # 存储当前选择模式
        current_select_mode = tuple(context.tool_settings.mesh_select_mode)
        
        # 获取角度值
        angle = context.scene.sharp_angle
        
        # 切换到对象模式以访问网格数据
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh = obj.data
        
        # 创建面到边的映射
        face_to_edges = {}
        edge_to_faces = {}
        
        # 获取所有面的法线和边的信息
        for face in mesh.polygons:
            face_to_edges[face.index] = set(face.edge_keys)
            for edge_key in face.edge_keys:
                if edge_key not in edge_to_faces:
                    edge_to_faces[edge_key] = []
                edge_to_faces[edge_key].append((face.index, face.normal))
        
        # 检查是否有选中的面
        selected_faces = set()
        for face in mesh.polygons:
            if face.select:
                selected_faces.add(face.index)
        
        # 如果没有选中的面，处理所有面
        if not selected_faces:
            selected_faces = set(face.index for face in mesh.polygons)
        
        # 处理选中面的边
        edges_to_process = set()
        for face_index in selected_faces:
            edges_to_process.update(face_to_edges[face_index])
        
        # 清除并设置锐边
        for edge in mesh.edges:
            edge_key = tuple(sorted((edge.vertices[0], edge.vertices[1])))
            if edge_key in edges_to_process:
                # 默认清除锐边
                edge.use_edge_sharp = False
                
                # 获取相邻面的信息
                connected_faces = edge_to_faces.get(edge_key, [])
                max_angle = 0
                
                # 计算这条边邻面之间的最大角度
                for i, (face1_idx, normal1) in enumerate(connected_faces):
                    for face2_idx, normal2 in connected_faces[i+1:]:
                        angle_rad = normal1.angle(normal2)
                        max_angle = max(max_angle, angle_rad)
                
                # 如果最大角度超过阈值，设置为锐边
                if max_angle > angle:
                    edge.use_edge_sharp = True
        
        # 切换回编辑模式
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 恢复选择模式
        context.tool_settings.mesh_select_mode = current_select_mode
        
        return {'FINISHED'}

class MESH_OT_sharp_to_seam(Operator):
    """将锐边设置为缝合线"""
    bl_idname = "mesh.sharp_to_seam"
    bl_label = "锐边转缝合线"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "请选择一个网格物体")
            return {'CANCELLED'}
        
        # 存储当前模式
        current_mode = obj.mode
        if current_mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        # 切换到对象模式以访问网格数据
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh = obj.data
        
        # 找到所有锐边并设置为缝合线
        for edge in mesh.edges:
            if edge.use_edge_sharp:
                edge.use_seam = True
        
        # 切换回编辑模式
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 恢复原始模式
        if current_mode != 'EDIT':
            bpy.ops.object.mode_set(mode=current_mode)
        
        return {'FINISHED'}

class MESH_OT_uv_boundary_to_sharp(Operator):
    """将UV边界设置为锐边"""
    bl_idname = "mesh.uv_boundary_to_sharp"
    bl_label = "UV边界转锐边"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if obj is None or obj.type != 'MESH':
            self.report({'ERROR'}, "请选择一个网格物体")
            return {'CANCELLED'}
        
        # 检查是否有UV
        if not obj.data.uv_layers:
            self.report({'ERROR'}, "物体没有UV贴图")
            return {'CANCELLED'}
        
        # 存储当前模式
        current_mode = obj.mode
        if current_mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
        
        # 切换到对象模式以访问网格数据
        bpy.ops.object.mode_set(mode='OBJECT')
        mesh = obj.data
        
        # 获取UV层
        uv_layer = mesh.uv_layers.active.data
        
        # 创建边到UV坐标的映射
        edge_to_uvs = {}
        
        # 遍历所有面的UV数据
        for poly in mesh.polygons:
            for i in range(poly.loop_total):
                current_loop_idx = poly.loop_start + i
                next_loop_idx = poly.loop_start + ((i + 1) % poly.loop_total)
                
                # 获取边的顶点索引
                current_vert = mesh.loops[current_loop_idx].vertex_index
                next_vert = mesh.loops[next_loop_idx].vertex_index
                edge_key = tuple(sorted((current_vert, next_vert)))
                
                # 获取UV坐标并进行舍入以避免浮点误差
                uv1 = tuple(round(x, 6) for x in uv_layer[current_loop_idx].uv)
                uv2 = tuple(round(x, 6) for x in uv_layer[next_loop_idx].uv)
                uv_edge = tuple(sorted([uv1, uv2]))
                
                # 存储UV边
                if edge_key not in edge_to_uvs:
                    edge_to_uvs[edge_key] = set()
                edge_to_uvs[edge_key].add(uv_edge)
        
        # 清除所有锐边
        for edge in mesh.edges:
            edge.use_edge_sharp = False
        
        # 检查并标记UV边界
        for edge in mesh.edges:
            edge_key = tuple(sorted((edge.vertices[0], edge.vertices[1])))
            if edge_key in edge_to_uvs:
                # 如果一条边在UV空间中有多个不同的位置，它就是UV边界
                if len(edge_to_uvs[edge_key]) > 1:
                    edge.use_edge_sharp = True
        
        # 切换回编辑模式
        bpy.ops.object.mode_set(mode='EDIT')
        
        # 恢复原始模式
        if current_mode != 'EDIT':
            bpy.ops.object.mode_set(mode=current_mode)
        
        return {'FINISHED'}

def register():
    bpy.utils.register_class(MESH_OT_smooth_selected_faces)
    bpy.utils.register_class(MESH_OT_mark_sharp_by_angle)
    bpy.utils.register_class(MESH_OT_sharp_to_seam)
    bpy.utils.register_class(MESH_OT_uv_boundary_to_sharp)

def unregister():
    bpy.utils.unregister_class(MESH_OT_smooth_selected_faces)
    bpy.utils.unregister_class(MESH_OT_mark_sharp_by_angle)
    bpy.utils.unregister_class(MESH_OT_sharp_to_seam)
    bpy.utils.unregister_class(MESH_OT_uv_boundary_to_sharp)
