import bpy
from bpy.props import EnumProperty

class op(bpy.types.Operator):
    bl_idname = "object.preview_bake"
    bl_label = "预览烘焙"
    bl_description = "预览烘焙结果"
    bl_options = {'REGISTER', 'UNDO'}
    
    bake_type: EnumProperty(
        name="预览类型",
        items=[
            ('COMBINED', "组合", "预览组合贴图"),
            ('AO', "AO", "预览环境光遮蔽"),
            ('LIGHT', "光照", "预览光照贴图")
        ],
        default='COMBINED'
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        try:
            # 这里添加预览逻辑
            self.report({'INFO'}, f"预览 {self.bake_type} 贴图")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"预览失败: {str(e)}")
            return {'CANCELLED'}

def register():
    bpy.utils.register_class(op)

def unregister():
    bpy.utils.unregister_class(op)

if __name__ == "__main__":
    register() 