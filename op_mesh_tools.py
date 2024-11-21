import bpy
import bmesh
from bpy.props import FloatProperty

class op(bpy.types.Operator):
    bl_idname = "cc.mesh_tools"
    bl_label = "网格工具"
    bl_description = "网格处理工具集"
    bl_options = {'REGISTER', 'UNDO'}
    
    sharp_angle: FloatProperty(
        name="锐边角度",
        description="大于此角度的边将被标记为锐边",
        default=30.0,
        min=0.0,
        max=180.0,
        subtype='ANGLE'
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
        
        try:
            # 获取选中的边
            selected_edges = [e for e in bm.edges if e.select]
            
            if not selected_edges:
                self.report({'WARNING'}, "没有选中的边")
                return {'CANCELLED'}
            
            # 设置锐边
            for edge in selected_edges:
                if edge.calc_face_angle() > self.sharp_angle:
                    edge.smooth = False
                else:
                    edge.smooth = True
            
            # 更新网格
            bmesh.update_edit_mesh(me)
            me.show_edge_sharp = True
            
            self.report({'INFO'}, f"处理了 {len(selected_edges)} 条边")
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"处理失败: {str(e)}")
            return {'CANCELLED'}

def register():
    bpy.utils.register_class(op)

def unregister():
    bpy.utils.unregister_class(op)

if __name__ == "__main__":
    register() 