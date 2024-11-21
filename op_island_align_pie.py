import bpy
from bpy.types import Menu

# 存储快捷键，以便后续删除
addon_keymaps = []

class VIEW3D_MT_PIE_uv_align(Menu):
    bl_label = "UV对齐"
    bl_idname = "UV_MT_PIE_align"

    def draw(self, context):
        layout = self.layout
        pie = layout.menu_pie()
        
        # 左 - 4
        op = pie.operator("uv.textools_island_align", text="左对齐")
        op.direction = 'LEFT'
        
        # 右 - 6
        op = pie.operator("uv.textools_island_align", text="右对齐")
        op.direction = 'RIGHT'
        
        # 下 - 2
        op = pie.operator("uv.textools_island_align", text="下对齐")
        op.direction = 'BOTTOM'
        
        # 上 - 8
        op = pie.operator("uv.textools_island_align", text="上对齐")
        op.direction = 'TOP'
        
        # 其余位置留空
        pie.separator()  # 7
        pie.separator()  # 3
        pie.separator()  # 1
        pie.separator()  # 9

def register():
    global addon_keymaps
    bpy.utils.register_class(VIEW3D_MT_PIE_uv_align)
    
    # 注册快捷键
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    
    if kc:
        # UV编辑器快捷键
        km = kc.keymaps.new(name='Image', space_type='IMAGE_EDITOR')
        kmi = km.keymap_items.new('wm.call_menu_pie', 'A', 'PRESS', alt=True)
        kmi.properties.name = "UV_MT_PIE_align"
        addon_keymaps.append((km, kmi))
        
        # 3D视图快捷键（可选）
        km = kc.keymaps.new(name='UV Editor')
        kmi = km.keymap_items.new('wm.call_menu_pie', 'A', 'PRESS', alt=True)
        kmi.properties.name = "UV_MT_PIE_align"
        addon_keymaps.append((km, kmi))

def unregister():
    global addon_keymaps
    # 注销快捷键
    for km, kmi in addon_keymaps:
        km.keymap_items.remove(kmi)
    addon_keymaps.clear()
    
    bpy.utils.unregister_class(VIEW3D_MT_PIE_uv_align)

if __name__ == "__main__":
    register() 