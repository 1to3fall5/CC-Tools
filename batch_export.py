import bpy
import os
from bpy.types import Operator
from ..utils.export_utils import (
    load_directories,
    save_directories,
    update_enum
)

class BatchExportFBXOperator(Operator):
    bl_idname = "export.batch_fbx"
    bl_label = "批量导出FBX"
    bl_description = "将选中的对象批量导出为FBX文件"
    bl_options = {'REGISTER', 'UNDO'}

    def export_single_object(self, obj, export_path):
        # 存储原始状态
        original_location = obj.location.copy()
        original_parent = obj.parent
        
        try:
            # 准备对象
            obj.location = (0, 0, 0)
            obj.parent = None
            
            # 取消选择所有对象并选择当前对象
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj
            
            # 使用简化版本的导出设置
            bpy.ops.export_scene.fbx(
                filepath=export_path, 
                use_selection=True, 
                axis_forward='-Z', 
                axis_up='Y'
            )
            return True
            
        except Exception as e:
            self.report({'ERROR'}, f"导出 {obj.name} 时出错: {str(e)}")
            return False
            
        finally:
            # 恢复原始状态
            obj.location = original_location
            obj.parent = original_parent

    def execute(self, context):
        scene = context.scene
        selected_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        
        if not selected_objects:
            self.report({'ERROR'}, "没有选择任何网格物体")
            return {'CANCELLED'}
        
        if not scene.manual_directory or not os.path.exists(scene.manual_directory):
            self.report({'ERROR'}, "请选择有效的导出目录")
            return {'CANCELLED'}
        
        # 存储当前选择和活动对象
        original_selection = context.selected_objects[:]
        original_active = context.active_object
        
        try:
            # 添加进度显示
            wm = context.window_manager
            wm.progress_begin(0, len(selected_objects))
            
            success_count = 0
            for i, obj in enumerate(selected_objects):
                export_path = os.path.join(scene.manual_directory, f"{obj.name}.fbx")
                if self.export_single_object(obj, export_path):
                    success_count += 1
                wm.progress_update(i)
            
            wm.progress_end()
            
            if success_count < len(selected_objects):
                self.report({'WARNING'}, 
                    f"完成导出 {success_count}/{len(selected_objects)} 个物体")
            else:
                self.report({'INFO'}, f"成功导出所有 {success_count} 个物体")
            
            # 更新目录历史
            if scene.manual_directory:
                directories = load_directories()
                if scene.manual_directory not in directories:
                    directories.append(scene.manual_directory)
                    save_directories(directories)
                    update_enum(None, context)
            
        except Exception as e:
            self.report({'ERROR'}, f"导出过程中出错: {str(e)}")
            return {'CANCELLED'}
            
        finally:
            # 恢复原始选择状态
            bpy.ops.object.select_all(action='DESELECT')
            for obj in original_selection:
                obj.select_set(True)
            if original_active:
                context.view_layer.objects.active = original_active
        
        return {'FINISHED'}

class DeleteDirectoryOperator(Operator):
    bl_idname = "export.delete_directory"
    bl_label = "删除目录"
    bl_description = "从历史记录中删除当前选择的目录"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        if event.shift:
            return self.clear_all_directories(context)
        return self.execute(context)

    def clear_all_directories(self, context):
        save_directories([])
        update_enum(self, context)
        context.scene.manual_directory = ''
        self.report({'INFO'}, "已清空所有保存的目录")
        return {'FINISHED'}

    def execute(self, context):
        current_directory = context.scene.manual_directory
        directories = load_directories()
        if current_directory in directories:
            directories.remove(current_directory)
            save_directories(directories)
            update_enum(self, context)
            context.scene.manual_directory = ''
            self.report({'INFO'}, f"已删除目录: {current_directory}")
        else:
            self.report({'ERROR'}, "当前目录不在历史记录中")
        return {'FINISHED'}

def register():
    bpy.utils.register_class(BatchExportFBXOperator)
    bpy.utils.register_class(DeleteDirectoryOperator)

def unregister():
    bpy.utils.unregister_class(BatchExportFBXOperator)
    bpy.utils.unregister_class(DeleteDirectoryOperator)
