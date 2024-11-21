import bpy
from bpy.types import Panel
import math
import os
from . import utils_export

class VIEW3D_PT_cc_export(Panel):
    bl_label = "CC Export"
    bl_idname = "VIEW3D_PT_cc_export"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'CC_Tools'

    def draw(self, context):
        layout = self.layout
        
        # FBX导出部分
        row = layout.row(align=True)
        row.prop(context.scene, 'manual_directory', text='')
        if hasattr(bpy.types.Scene, 'directory_enum'):
            row.menu('EXPORT_MT_directory_history', text='', icon='DOWNARROW_HLT')
        row.operator("export.delete_directory", text="", icon='TRASH')
        
        # 导出按钮
        row = layout.row()
        row.operator("cc.batch_export_fbx", text="批量导出FBX", icon='EXPORT')

class VIEW3D_PT_cc_mesh(Panel):
    bl_label = "CC Mesh"
    bl_idname = "VIEW3D_PT_cc_mesh"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'CC_Tools'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        
        # 改进编辑模式检查逻辑
        is_edit_mode = False
        if (context.active_object and 
            context.active_object.type == 'MESH' and 
            context.active_object.mode == 'EDIT'):
            is_edit_mode = True
        
        col = layout.column(align=True)
        col.enabled = is_edit_mode
        
        if not is_edit_mode:
            col.label(text="需要在编辑模式下使用", icon='INFO')
            return
        
        # 平滑工具部分
        box = col.box()
        col1 = box.column(align=True)
        col1.label(text="平滑工具:")
        col1.operator("mesh.smooth_selected_faces", text="平滑所选")
        row = col1.row(align=True)
        row.operator("mesh.mark_sharp_by_angle", text="设置锐边")
        row.prop(context.scene, "sharp_angle", text="")
        
        # 转换工具部分
        box = col.box()
        col2 = box.column(align=True)
        col2.label(text="转换工具:")
        row = col2.row(align=True)
        row.operator("mesh.sharp_to_seam", text="锐边转缝合线")
        row.operator("mesh.seam_to_sharp", text="缝合线转锐边")
        row = col2.row(align=True)
        row.operator("mesh.uv_boundary_to_sharp", text="UV边界转锐边")
        row.operator("mesh.sharp_to_uv_boundary", text="锐边转UV边界")

class VIEW3D_PT_cc_bake(Panel):
    bl_label = "CC Bake"
    bl_idname = "VIEW3D_PT_cc_bake"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'CC_Tools'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        
        if not context.active_object:
            layout.label(text="请选择一个物体", icon='INFO')
            return
        
        # 烘焙设置
        col = layout.column(align=True)
        
        # 基础设置
        box = col.box()
        col1 = box.column(align=True)
        col1.label(text="基础设置:")
        col1.prop(context.scene, "bake_resolution", text="分辨率")
        col1.prop(context.scene, "bake_type", text="烘焙类型")
        
        # 高级设置
        box = col.box()
        col2 = box.column(align=True)
        col2.label(text="高级设置:")
        col2.prop(context.scene, "bake_samples", text="采样数")
        col2.prop(context.scene, "bake_margin", text="边缘扩展")
        
        # 烘焙和预览按钮
        box = col.box()
        col3 = box.column(align=True)
        col3.operator("cc.bake_textures", text="开始烘焙", icon='RENDER_STILL')
        
        row = col3.row(align=True)
        op1 = row.operator("object.preview_bake", text="预览组合")
        op1.bake_type = 'COMBINED'
        op2 = row.operator("object.preview_bake", text="预览AO")
        op2.bake_type = 'AO'
        op3 = row.operator("object.preview_bake", text="预览光照")
        op3.bake_type = 'LIGHT'

class VIEW3D_PT_cc_uv(Panel):
    bl_label = "CC UV"
    bl_idname = "VIEW3D_PT_cc_uv"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'CC_Tools'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        self.draw_uv_tools(context, self.layout)

    @staticmethod
    def draw_uv_tools(context, layout):
        if context.active_object and context.active_object.mode != 'EDIT':
            layout.label(text="请切换到编辑模式", icon='INFO')
            return
            
        col = layout.column(align=True)
        
        # 添加饼菜单按钮
        box = col.box()
        row = box.row(align=True)
        row.operator("wm.call_menu_pie", text="快速对齐 (Alt+A)", icon='ALIGN_CENTER').name = "UV_MT_PIE_align"
        
        # UV对齐工具
        box = col.box()
        col = box.column(align=True)  # 使用列布局使按钮更紧凑
        
        # 第一行对齐工具
        row = col.row(align=True)
        op = row.operator("uv.textools_island_align", text="↖")
        op.direction = 'LEFT_TOP'
        op = row.operator("uv.textools_island_align", text="↑")
        op.direction = 'TOP'
        op = row.operator("uv.textools_island_align", text="↗")
        op.direction = 'RIGHT_TOP'
        
        # 第二行对齐工具
        row = col.row(align=True)
        op = row.operator("uv.textools_island_align", text="←")
        op.direction = 'LEFT'
        op = row.operator("uv.textools_island_align", text="⊙")
        op.direction = 'CENTER'
        op = row.operator("uv.textools_island_align", text="→")
        op.direction = 'RIGHT'
        
        # 第三行对齐工具
        row = col.row(align=True)
        op = row.operator("uv.textools_island_align", text="↙")
        op.direction = 'LEFT_BOTTOM'
        op = row.operator("uv.textools_island_align", text="↓")
        op.direction = 'BOTTOM'
        op = row.operator("uv.textools_island_align", text="↘")
        op.direction = 'RIGHT_BOTTOM'

        # 添加选择模式提示
        box = col.box()
        row = box.row()
        if context.scene.tool_settings.use_uv_select_sync:
            row.label(text="当前模式: 同步选择", icon='UV_SYNC_SELECT')
        else:
            mode = context.scene.tool_settings.uv_select_mode
            row.label(text=f"当前模式: {mode}", icon='UV')

        # UV缩放工具
        box = col.box()
        row = box.row(align=True)
        
        # 左侧组：缩放按钮
        col_left = row.column(align=True)
        col_left.scale_y = 1.5  # 增加按钮高度
        col_left.operator("uv.textools_island_scale", text="放大", icon='FULLSCREEN_ENTER').scale_mode = 'MAX'
        col_left.operator("uv.textools_island_scale", text="缩小", icon='FULLSCREEN_EXIT').scale_mode = 'MIN'
        
        # 添加一点间隔
        row.separator(factor=0.5)
        
        # 右侧组：约束条件
        col_right = row.column(align=True)
        col_right.scale_x = 0.6  # 减小右侧按钮的宽度
        
        # 使用小组来确保三个按钮宽度一致
        sub_col = col_right.column(align=True)
        sub_col.scale_y = 1.0  # 设置基准高度
        
        # 约束条件选择
        sub_col.prop(context.scene, "uv_scale_x", text="X")
        sub_col.prop(context.scene, "uv_scale_y", text="Y")
        sub_col.prop(context.scene, "uv_scale_lock_ratio", text="", icon='LOCKED' if context.scene.uv_scale_lock_ratio else 'UNLOCKED')

class IMAGE_PT_cc_uv(Panel):
    bl_label = "CC UV"
    bl_idname = "IMAGE_PT_cc_uv"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = 'CC_Tools'
    bl_options = {'DEFAULT_CLOSED'}

    @classmethod
    def poll(cls, context):
        return context.space_data.type == 'IMAGE_EDITOR' and context.space_data.mode == 'UV'

    def draw(self, context):
        self.draw_uv_tools(context, self.layout)

    @staticmethod
    def draw_uv_tools(context, layout):
        if context.active_object and context.active_object.mode != 'EDIT':
            layout.label(text="请切换到编辑模式", icon='INFO')
            return
            
        col = layout.column(align=True)
        
        # 添加饼菜单按钮
        box = col.box()
        row = box.row(align=True)
        row.operator("wm.call_menu_pie", text="快速对齐 (Alt+A)", icon='ALIGN_CENTER').name = "UV_MT_PIE_align"
        
        # UV对齐工具
        box = col.box()
        col = box.column(align=True)  # 使用列布局使按钮更紧凑
        
        # 第一行对齐工具
        row = col.row(align=True)
        op = row.operator("uv.textools_island_align", text="↖")
        op.direction = 'LEFT_TOP'
        op = row.operator("uv.textools_island_align", text="↑")
        op.direction = 'TOP'
        op = row.operator("uv.textools_island_align", text="↗")
        op.direction = 'RIGHT_TOP'
        
        # 第二行对齐工具
        row = col.row(align=True)
        op = row.operator("uv.textools_island_align", text="←")
        op.direction = 'LEFT'
        op = row.operator("uv.textools_island_align", text="⊙")
        op.direction = 'CENTER'
        op = row.operator("uv.textools_island_align", text="→")
        op.direction = 'RIGHT'
        
        # 第三行对齐工具
        row = col.row(align=True)
        op = row.operator("uv.textools_island_align", text="↙")
        op.direction = 'LEFT_BOTTOM'
        op = row.operator("uv.textools_island_align", text="↓")
        op.direction = 'BOTTOM'
        op = row.operator("uv.textools_island_align", text="↘")
        op.direction = 'RIGHT_BOTTOM'

        # 添加选择模式提示
        box = col.box()
        row = box.row()
        if context.scene.tool_settings.use_uv_select_sync:
            row.label(text="当前模式: 同步选择", icon='UV_SYNC_SELECT')
        else:
            mode = context.scene.tool_settings.uv_select_mode
            row.label(text=f"当前模式: {mode}", icon='UV')

        # UV缩放工具
        box = col.box()
        row = box.row(align=True)
        
        # 左侧组：缩放按钮
        col_left = row.column(align=True)
        col_left.scale_y = 1.5  # 增加按钮高度
        col_left.operator("uv.textools_island_scale", text="放大", icon='FULLSCREEN_ENTER').scale_mode = 'MAX'
        col_left.operator("uv.textools_island_scale", text="缩小", icon='FULLSCREEN_EXIT').scale_mode = 'MIN'
        
        # 添加一点间隔
        row.separator(factor=0.5)
        
        # 右侧组：约束条件
        col_right = row.column(align=True)
        col_right.scale_x = 0.6  # 减小右侧按钮的宽度
        
        # 使用小组来确保三个按钮宽度一致
        sub_col = col_right.column(align=True)
        sub_col.scale_y = 1.0  # 设置基准高度
        
        # 约束条件选择
        sub_col.prop(context.scene, "uv_scale_x", text="X")
        sub_col.prop(context.scene, "uv_scale_y", text="Y")
        sub_col.prop(context.scene, "uv_scale_lock_ratio", text="", icon='LOCKED' if context.scene.uv_scale_lock_ratio else 'UNLOCKED')

# 添加历史记录菜单类
class EXPORT_MT_directory_history(bpy.types.Menu):
    bl_label = "历史目录"
    bl_idname = "EXPORT_MT_directory_history"

    def draw(self, context):
        layout = self.layout
        directories = utils_export.load_directories()
        
        for path in directories:
            op = layout.operator("export.select_directory", text=os.path.basename(path.rstrip(os.sep)) or path)
            op.path = path

# 添加选择目录操作符
class SelectDirectoryOperator(bpy.types.Operator):
    bl_idname = "export.select_directory"
    bl_label = "���择目录"
    bl_description = "选择历史目录"
    bl_options = {'REGISTER', 'UNDO'}
    
    path: bpy.props.StringProperty()
    
    def execute(self, context):
        context.scene.manual_directory = self.path
        return {'FINISHED'}

def register():
    bpy.utils.register_class(VIEW3D_PT_cc_export)
    bpy.utils.register_class(VIEW3D_PT_cc_mesh)
    bpy.utils.register_class(VIEW3D_PT_cc_bake)
    bpy.utils.register_class(VIEW3D_PT_cc_uv)
    bpy.utils.register_class(IMAGE_PT_cc_uv)
    bpy.utils.register_class(EXPORT_MT_directory_history)
    bpy.utils.register_class(SelectDirectoryOperator)
    
    bpy.types.Scene.manual_directory = bpy.props.StringProperty(subtype='DIR_PATH')
    
    # 角度属性
    bpy.types.Scene.sharp_angle = bpy.props.FloatProperty(
        name="锐边角度",
        description="大于此角度的边将被标记为锐边",
        default=math.radians(90.0),
        min=0.0,
        max=math.radians(180.0),
        precision=1,
        step=100,
        subtype='ANGLE',
        unit='ROTATION'
    )
    
    # 烘焙属性
    bpy.types.Scene.bake_resolution = bpy.props.EnumProperty(
        name="烘焙分辨率",
        description="设置烘焙贴图的分辨率",
        items=[
            ('512', "512", "512 x 512 像素"),
            ('1024', "1024", "1024 x 1024 像素"),
            ('2048', "2048", "2048 x 2048 像素"),
            ('4096', "4096", "4096 x 4096 像素"),
        ],
        default='1024'
    )
    
    bpy.types.Scene.bake_type = bpy.props.EnumProperty(
        name="烘焙类型",
        description="选择要烘焙的贴图类型",
        items=[
            ('NORMAL', "法线", "烘焙法线贴图"),
            ('AO', "环境光遮蔽", "烘焙环境光遮蔽贴图"),
            ('COMBINED', "混合", "烘焙混合贴图"),
        ],
        default='NORMAL'
    )
    
    # UV缩放属性
    bpy.types.Scene.uv_scale_x = bpy.props.BoolProperty(
        name="X轴约束",
        description="在X方向上缩放",
        default=True
    )
    
    bpy.types.Scene.uv_scale_y = bpy.props.BoolProperty(
        name="Y轴约束",
        description="在Y方向上缩放",
        default=False
    )
    
    bpy.types.Scene.uv_scale_lock_ratio = bpy.props.BoolProperty(
        name="锁定比例",
        description="保持UV岛的原始比例",
        default=False
    )

def unregister():
    bpy.utils.unregister_class(VIEW3D_PT_cc_bake)
    bpy.utils.unregister_class(VIEW3D_PT_cc_mesh)
    bpy.utils.unregister_class(VIEW3D_PT_cc_export)
    bpy.utils.unregister_class(VIEW3D_PT_cc_uv)
    bpy.utils.unregister_class(IMAGE_PT_cc_uv)
    bpy.utils.unregister_class(EXPORT_MT_directory_history)
    bpy.utils.unregister_class(SelectDirectoryOperator)
    
    # 删除属性前先检查是否存在
    if hasattr(bpy.types.Scene, 'manual_directory'):
        del bpy.types.Scene.manual_directory
    if hasattr(bpy.types.Scene, 'sharp_angle'):
        del bpy.types.Scene.sharp_angle
    if hasattr(bpy.types.Scene, 'bake_resolution'):
        del bpy.types.Scene.bake_resolution
    if hasattr(bpy.types.Scene, 'bake_type'):
        del bpy.types.Scene.bake_type
    if hasattr(bpy.types.Scene, 'text_file_enum'):
        del bpy.types.Scene.text_file_enum
    if hasattr(bpy.types.Scene, 'uv_scale_x'):
        del bpy.types.Scene.uv_scale_x
    if hasattr(bpy.types.Scene, 'uv_scale_y'):
        del bpy.types.Scene.uv_scale_y
    if hasattr(bpy.types.Scene, 'uv_scale_lock_ratio'):
        del bpy.types.Scene.uv_scale_lock_ratio
