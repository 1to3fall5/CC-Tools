import bpy
from bpy.props import EnumProperty, IntProperty
from . import utils_bake

class op(bpy.types.Operator):
    bl_idname = "cc.bake_textures"
    bl_label = "烘焙贴图"
    bl_description = "烘焙选中物体的贴图"
    bl_options = {'REGISTER', 'UNDO'}
    
    resolution: EnumProperty(
        name="分辨率",
        items=[
            ('512', "512", "512x512"),
            ('1024', "1024", "1024x1024"),
            ('2048', "2048", "2048x2048"),
            ('4096', "4096", "4096x4096")
        ],
        default='1024'
    )
    
    samples: IntProperty(
        name="采样数",
        description="烘焙时的采样数量",
        default=128,
        min=1,
        max=4096
    )
    
    margin: IntProperty(
        name="边缘扩展",
        description="烘焙贴图的边缘扩展像素",
        default=16,
        min=0,
        max=64
    )
    
    bake_type: EnumProperty(
        name="烘焙类型",
        items=[
            ('COMBINED', "组合", "烘焙组合贴图"),
            ('AO', "AO", "烘焙环境光遮蔽"),
            ('LIGHT', "光照", "烘焙光照贴图")
        ],
        default='COMBINED'
    )

    @classmethod
    def poll(cls, context):
        return context.active_object is not None and context.active_object.type == 'MESH'

    def execute(self, context):
        settings = utils_bake.BakeSettings()
        settings.resolution = int(self.resolution)
        settings.samples = self.samples
        settings.margin = self.margin
        settings.bake_type = self.bake_type
        
        try:
            utils_bake.bake_textures(context, settings)
            self.report({'INFO'}, "烘焙完成")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"烘焙失败: {str(e)}")
            return {'CANCELLED'}

def register():
    bpy.utils.register_class(op)

def unregister():
    bpy.utils.unregister_class(op)

if __name__ == "__main__":
    register() 