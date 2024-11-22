import bpy
import bmesh
from mathutils import Vector
from bpy.props import BoolProperty, FloatProperty, EnumProperty
from . import utils_uv
from . import utils_bbox

class op(bpy.types.Operator):
    bl_idname = "uv.textools_island_scale"
    bl_label = "缩放UV岛"
    bl_description = "缩放选中的UV岛"
    bl_options = {'REGISTER', 'UNDO'}
    
    scale_mode: EnumProperty(
        name='缩放模式',
        items=[
            ('MIN', "最小", "缩放到最小岛的大小"),
            ('MAX', "最大", "缩放到最大岛的大小"),
        ],
        default='MAX'
    )
    
    direction: EnumProperty(
        name='方向',
        items=[
            ('X', "X轴", "在X方向缩放"),
            ('Y', "Y轴", "在Y方向缩放"),
            ('BOTH', "XY轴", "在两个方向缩放"),
        ],
        default='BOTH'
    )
    
    keep_proportion: BoolProperty(
        name="保持比例",
        description="保持UV岛的原始比例",
        default=True
    )

    @classmethod
    def poll(cls, context):
        return (context.active_object is not None and
                context.active_object.type == 'MESH' and
                context.active_object.mode == 'EDIT')

    def execute(self, context):
        obj = context.active_object
        me = obj.data
        bm = bmesh.from_edit_mesh(me)
        uv_layer = bm.loops.layers.uv.verify()
        
        # 获取选中的岛
        selected_islands = []
        if context.scene.tool_settings.uv_select_mode == 'FACE':
            selected_islands = utils_uv.getSelectionIslands(bm, uv_layer, extend_selection_to_islands=True)
        else:
            selected_islands = utils_uv.get_selected_islands(bm, uv_layer, selected=True)
            
        if not selected_islands:
            self.report({'WARNING'}, "没有选中的UV岛")
            return {'CANCELLED'}
            
        # 计算所有岛的边界框
        island_bboxes = []
        for island in selected_islands:
            bbox = utils_bbox.BBox.calc_bbox_uv(island, uv_layer)
            island_bboxes.append((island, bbox))
            
        # 获取约束条件
        scale_x = context.scene.uv_scale_x
        scale_y = context.scene.uv_scale_y
        lock_ratio = context.scene.uv_scale_lock_ratio
        
        # 如果没有选择任何约束，默认使用锁定比例的平均缩放
        if not scale_x and not scale_y and not lock_ratio:
            scale_x = True
            scale_y = True
            lock_ratio = True
        
        # 找到目标大小
        if self.scale_mode == 'MAX':
            target_x = max(bbox.width for _, bbox in island_bboxes)
            target_y = max(bbox.height for _, bbox in island_bboxes)
        else:  # MIN
            target_x = min(bbox.width for _, bbox in island_bboxes)
            target_y = min(bbox.height for _, bbox in island_bboxes)
        
        # 缩放每个岛
        for island, bbox in island_bboxes:
            if lock_ratio:
                # 锁定比例时，使用平均缩放比例
                if scale_x and scale_y:
                    # 计算平均缩放比例
                    scale_factor_x = target_x / bbox.width
                    scale_factor_y = target_y / bbox.height
                    scale_factor = (scale_factor_x + scale_factor_y) / 2
                    utils_uv.scale_island(island, uv_layer, scale_factor, scale_factor)
                elif scale_x:
                    scale_factor = target_x / bbox.width
                    utils_uv.scale_island(island, uv_layer, scale_factor, scale_factor)
                elif scale_y:
                    scale_factor = target_y / bbox.height
                    utils_uv.scale_island(island, uv_layer, scale_factor, scale_factor)
            else:
                # 不锁定比例时，分别处理X和Y方向
                scale_factor_x = target_x / bbox.width if scale_x else 1.0
                scale_factor_y = target_y / bbox.height if scale_y else 1.0
                utils_uv.scale_island(island, uv_layer, scale_factor_x, scale_factor_y)

        bmesh.update_edit_mesh(me)
        return {'FINISHED'}

def register():
    bpy.utils.register_class(op)

def unregister():
    bpy.utils.unregister_class(op)

if __name__ == "__main__":
    register() 