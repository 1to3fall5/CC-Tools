import bpy
import bmesh
from mathutils import Vector
from bpy.types import Operator
from bpy.props import EnumProperty
from . import utils_uv
from . import utils_bbox

class op(bpy.types.Operator):
    bl_idname = "uv.textools_island_align"
    bl_label = "对齐"
    bl_description = "对齐选中的UV点或岛"
    bl_options = {'REGISTER', 'UNDO'}
    
    direction: EnumProperty(
        name='方向',
        items=[
            ('LEFT_TOP', "左上", ""),
            ('TOP', "上", ""),
            ('RIGHT_TOP', "右上", ""),
            ('LEFT', "左", ""),
            ('CENTER', "中心", ""),
            ('RIGHT', "右", ""),
            ('LEFT_BOTTOM', "左下", ""),
            ('BOTTOM', "下", ""),
            ('RIGHT_BOTTOM', "右下", ""),
        ],
        default='CENTER'
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
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        uv_layer = bm.loops.layers.uv.verify()
        
        # 获取UV选择模式
        sync = context.scene.tool_settings.use_uv_select_sync
        if sync:
            selection_mode = 'SYNC'
        else:
            selection_mode = context.scene.tool_settings.uv_select_mode

        # 根据选择模式处理对齐
        if selection_mode == 'VERTEX':
            self.align_vertices(bm, uv_layer)
        elif selection_mode == 'EDGE':
            # 边模式也使用顶点对齐
            self.align_vertices(bm, uv_layer)
        else:  # 'FACE', 'ISLAND' 或 'SYNC' 模式
            if selection_mode == 'FACE':
                # 获取选中面所在的完整岛
                selected_islands = utils_uv.getSelectionIslands(bm, uv_layer, extend_selection_to_islands=True)
            else:
                # ISLAND或SYNC模式直接获取选中的岛
                selected_islands = utils_uv.get_selected_islands(bm, uv_layer, selected=True)
            
            self.align_islands(bm, uv_layer, selected_islands)

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}

    def align_vertices(self, bm, uv_layer):
        # 收集选中的UV点
        selected_uvs = []
        for face in bm.faces:
            for loop in face.loops:
                if loop[uv_layer].select:
                    selected_uvs.append(loop[uv_layer])

        if not selected_uvs:
            return

        # 计算边界
        min_x = min(uv.uv.x for uv in selected_uvs)
        max_x = max(uv.uv.x for uv in selected_uvs)
        min_y = min(uv.uv.y for uv in selected_uvs)
        max_y = max(uv.uv.y for uv in selected_uvs)
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2

        # 对齐UV点
        for uv in selected_uvs:
            if self.direction == 'LEFT':
                uv.uv.x = min_x
            elif self.direction == 'RIGHT':
                uv.uv.x = max_x
            elif self.direction == 'TOP':
                uv.uv.y = max_y
            elif self.direction == 'BOTTOM':
                uv.uv.y = min_y
            elif self.direction == 'CENTER':
                uv.uv.x = center_x
                uv.uv.y = center_y
            elif self.direction == 'LEFT_TOP':
                uv.uv.x = min_x
                uv.uv.y = max_y
            elif self.direction == 'RIGHT_TOP':
                uv.uv.x = max_x
                uv.uv.y = max_y
            elif self.direction == 'LEFT_BOTTOM':
                uv.uv.x = min_x
                uv.uv.y = min_y
            elif self.direction == 'RIGHT_BOTTOM':
                uv.uv.x = max_x
                uv.uv.y = min_y

    def align_islands(self, bm, uv_layer, selected_islands):
        if not selected_islands:
            return

        # 使用BBox计算边界
        all_groups = []
        general_bbox = utils_bbox.BBox()
        
        # 计算每个岛的边界和总边界
        for island in selected_islands:
            bbox = utils_bbox.BBox.calc_bbox_uv(island, uv_layer)
            general_bbox.union(bbox)
            all_groups.append((island, bbox, uv_layer))

        # 对齐UV岛
        for island, bounds, uv_layer in all_groups:
            delta = Vector((0, 0))
            
            if self.direction == 'LEFT':
                delta = Vector(((general_bbox.min.x - bounds.min.x), 0))
            elif self.direction == 'RIGHT':
                delta = Vector(((general_bbox.max.x - bounds.max.x), 0))
            elif self.direction == 'TOP':
                delta = Vector((0, (general_bbox.max.y - bounds.max.y)))
            elif self.direction == 'BOTTOM':
                delta = Vector((0, (general_bbox.min.y - bounds.min.y)))
            elif self.direction == 'CENTER':
                delta = general_bbox.center - bounds.center
            elif self.direction == 'LEFT_TOP':
                delta = Vector((general_bbox.min.x - bounds.min.x, 
                              general_bbox.max.y - bounds.max.y))
            elif self.direction == 'RIGHT_TOP':
                delta = Vector((general_bbox.max.x - bounds.max.x, 
                              general_bbox.max.y - bounds.max.y))
            elif self.direction == 'LEFT_BOTTOM':
                delta = Vector((general_bbox.min.x - bounds.min.x, 
                              general_bbox.min.y - bounds.min.y))
            elif self.direction == 'RIGHT_BOTTOM':
                delta = Vector((general_bbox.max.x - bounds.max.x, 
                              general_bbox.min.y - bounds.min.y))

            if delta != Vector((0, 0)):
                utils_uv.translate_island(island, uv_layer, delta)

def register():
    bpy.utils.register_class(op)

def unregister():
    bpy.utils.unregister_class(op)

if __name__ == "__main__":
    register() 