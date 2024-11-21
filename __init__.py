bl_info = {
    "name": "CC Tools",
    "author": "Chen Chen",
    "version": (1, 2, 2),
    "blender": (4, 2, 3),
    "location": "View3D > Tools",
    "description": "批量导出FBX和网格处理工具集",
    "warning": "",
    "wiki_url": "",
    "category": "Import-Export",
}

import bpy
from bpy.props import StringProperty, CollectionProperty, IntProperty, EnumProperty
from bpy.types import PropertyGroup

# 导入所有操作符
from . import op_island_align_sort
from . import op_island_align_edge
from . import op_island_align_world
from . import op_island_align
from . import op_island_align_pie
from . import op_island_scale
from . import op_batch_export
from . import op_bake
from . import op_mesh_tools
from . import op_preview_bake
from . import panels

# 定义目录历史记录的属性组
class DirectoryHistoryItem(PropertyGroup):
    path: StringProperty(name="路径")

def register():
    # 注册属性组
    bpy.utils.register_class(DirectoryHistoryItem)
    
    # 注册所有模块
    modules = (
        op_island_align_sort,
        op_island_align_edge,
        op_island_align_world,
        op_island_align,
        op_island_align_pie,
        op_island_scale,
        op_batch_export,
        op_bake,
        op_mesh_tools,
        op_preview_bake,
        panels
    )
    
    for mod in modules:
        mod.register()
    
    # 导出相关属性
    bpy.types.Scene.directory_history = CollectionProperty(
        type=DirectoryHistoryItem
    )
    bpy.types.Scene.manual_directory = StringProperty(
        name="导出目录",
        description="选择FBX文件导出目录",
        subtype='DIR_PATH'
    )
    bpy.types.Scene.directory_enum = EnumProperty(
        name="历史目录",
        description="选择历史目录",
        items=utils_export.update_enum,
        update=lambda self, context: setattr(context.scene, 'manual_directory', self.directory_enum)
    )
    
    # 烘焙相关属性
    bpy.types.Scene.bake_resolution = EnumProperty(
        name="分辨率",
        items=[
            ('512', "512", "512x512"),
            ('1024', "1024", "1024x1024"),
            ('2048', "2048", "2048x2048"),
            ('4096', "4096", "4096x4096")
        ],
        default='1024'
    )
    bpy.types.Scene.bake_samples = IntProperty(
        name="采样数",
        description="烘焙时的采样数量",
        default=128,
        min=1,
        max=4096
    )
    bpy.types.Scene.bake_margin = IntProperty(
        name="边缘扩展",
        description="烘焙贴图的边缘扩展像素",
        default=16,
        min=0,
        max=64
    )
    bpy.types.Scene.bake_type = EnumProperty(
        name="烘焙类型",
        items=[
            ('COMBINED', "组合", "烘焙组合贴图"),
            ('AO', "AO", "烘焙环境光遮蔽"),
            ('LIGHT', "光照", "烘焙光照贴图")
        ],
        default='COMBINED'
    )

def unregister():
    # 注销所有模块
    modules = (
        op_island_align_sort,
        op_island_align_edge,
        op_island_align_world,
        op_island_align,
        op_island_align_pie,
        op_island_scale,
        op_batch_export,
        op_bake,
        op_mesh_tools,
        op_preview_bake,
        panels
    )
    
    for mod in modules:
        mod.unregister()
    
    # 注销属性组
    bpy.utils.unregister_class(DirectoryHistoryItem)
    
    # 注销属性前先检查是否存在
    if hasattr(bpy.types.Scene, 'directory_history'):
        del bpy.types.Scene.directory_history
    if hasattr(bpy.types.Scene, 'manual_directory'):
        del bpy.types.Scene.manual_directory
    if hasattr(bpy.types.Scene, 'bake_resolution'):
        del bpy.types.Scene.bake_resolution
    if hasattr(bpy.types.Scene, 'bake_samples'):
        del bpy.types.Scene.bake_samples
    if hasattr(bpy.types.Scene, 'bake_margin'):
        del bpy.types.Scene.bake_margin
    if hasattr(bpy.types.Scene, 'bake_type'):
        del bpy.types.Scene.bake_type

if __name__ == "__main__":
    register()
