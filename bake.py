import bpy
from bpy.types import Operator

class OBJECT_OT_bake_textures(Operator):
    """烘焙组合贴图（R:黑色, G:AO, B:光照）"""
    bl_idname = "object.bake_textures"
    bl_label = "烘焙贴图"
    bl_options = {'REGISTER', 'UNDO'}
    
    def setup_material(self, context, obj, bake_image):
        # 创建或获取材质
        if not obj.material_slots:
            mat = bpy.data.materials.new(name=f"{obj.name}_bake_material")
            mat.use_nodes = True
            obj.data.materials.append(mat)
        mat = obj.material_slots[0].material
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # 清理现有节点
        nodes.clear()
        
        # 创建节点
        output_node = nodes.new('ShaderNodeOutputMaterial')
        diffuse = nodes.new('ShaderNodeBsdfDiffuse')
        image_node = nodes.new('ShaderNodeTexImage')
        
        # 设置节点位置
        output_node.location = (300, 0)
        diffuse.location = (-100, 0)
        image_node.location = (-300, 0)
        
        # 设置节点属性
        image_node.image = bake_image
        
        # 连接节点
        links.new(diffuse.outputs[0], output_node.inputs['Surface'])
        
        # 设置为活动节点
        image_node.select = True
        nodes.active = image_node
        
        return image_node
    
    def execute(self, context):
        obj = context.active_object
        if obj is None:
            self.report({'ERROR'}, "请选择一个物体")
            return {'CANCELLED'}
        
        # 检查是否有第二UV图层
        if len(obj.data.uv_layers) < 2:
            self.report({'ERROR'}, "物体需要第二UV图层")
            return {'CANCELLED'}
        
        # 存储当前活动的UV图层
        active_uv = obj.data.uv_layers.active
        
        # 设置第二个UV图层为活动图层
        obj.data.uv_layers.active = obj.data.uv_layers[1]
        
        # 获取烘焙设置
        resolution = int(context.scene.bake_resolution)
        
        # 创建光照贴图
        lighting_image = bpy.data.images.new(
            name=f"{obj.name}_lighting",
            width=resolution,
            height=resolution,
            alpha=False,
            float_buffer=True
        )
        
        # 创建AO贴图
        ao_image = bpy.data.images.new(
            name=f"{obj.name}_ao",
            width=resolution,
            height=resolution,
            alpha=False,
            float_buffer=True
        )
        
        # 创建最终的组合贴图
        final_image = bpy.data.images.new(
            name=f"{obj.name}_combined",
            width=resolution,
            height=resolution,
            alpha=False,
            float_buffer=True
        )
        
        # 设置活动的UV图层
        if not obj.data.uv_layers.active:
            self.report({'ERROR'}, "物体需要UV展开")
            return {'CANCELLED'}
        
        # 设置渲染引擎为 Cycles
        context.scene.render.engine = 'CYCLES'
        
        # 设置渲染设备为 GPU
        context.scene.cycles.device = 'GPU'
        
        # 确保所有可用的GPU都被启用
        preferences = context.preferences
        cycles_preferences = preferences.addons['cycles'].preferences
        cycles_preferences.compute_device_type = 'CUDA'
        
        # 启用所有可用的GPU设备
        for device in cycles_preferences.devices:
            device.use = True
        
        # 烘焙光照
        image_node = self.setup_material(context, obj, lighting_image)
        bpy.ops.object.bake(
            type='DIFFUSE',
            pass_filter={'DIRECT', 'INDIRECT', 'EMIT'},
            use_clear=True,
            margin=16
        )
        
        # 烘焙AO
        image_node.image = ao_image
        bpy.ops.object.bake(
            type='AO',
            use_clear=True,
            margin=16
        )
        
        # 合并贴图
        lighting_pixels = list(lighting_image.pixels)
        ao_pixels = list(ao_image.pixels)
        final_pixels = []
        
        # 每4个值代表一个像素的RGBA
        for i in range(0, len(lighting_pixels), 4):
            # R通道设为0（黑色）
            final_pixels.append(0)
            # G通道设为AO值
            final_pixels.append(ao_pixels[i])
            # B通道设为光照值
            final_pixels.append(lighting_pixels[i])
            # Alpha通道设为1
            final_pixels.append(1)
        
        # 更新最终贴图
        final_image.pixels = final_pixels
        final_image.update()
        
        # 烘焙完成后恢复原来的UV图层
        obj.data.uv_layers.active = active_uv
        
        # 更新材质节点中的图像
        mat = obj.material_slots[0].material
        nodes = mat.node_tree.nodes
        
        # 清理现有节点
        nodes.clear()
        
        # 创建基础节点
        output_node = nodes.new('ShaderNodeOutputMaterial')
        principled_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        image_node = nodes.new('ShaderNodeTexImage')
        uv_node = nodes.new('ShaderNodeUVMap')  # 添加UV Map节点
        
        # 设置节点位置
        output_node.location = (300, 0)
        principled_bsdf.location = (0, 0)
        image_node.location = (-300, 0)
        uv_node.location = (-500, 0)
        
        # 设置节点属性
        image_node.image = final_image
        uv_node.uv_map = obj.data.uv_layers[1].name  # 设置使用第二UV
        
        # 连接节点
        links = mat.node_tree.links
        links.new(uv_node.outputs[0], image_node.inputs[0])  # 连接UV到图像节点
        links.new(image_node.outputs[0], principled_bsdf.inputs[0])
        links.new(principled_bsdf.outputs[0], output_node.inputs[0])
        
        self.report({'INFO'}, "已完成组合贴图烘焙")
        return {'FINISHED'}

class OBJECT_OT_preview_lighting(Operator):
    """预览灯光贴图"""
    bl_idname = "object.preview_lighting"
    bl_label = "预览灯光"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if obj is None or not obj.material_slots:
            self.report({'ERROR'}, "请选择有材质的物体")
            return {'CANCELLED'}
        
        # 获取灯光贴图
        lighting_image = bpy.data.images.get(f"{obj.name}_lighting")
        if not lighting_image:
            self.report({'ERROR'}, "未找到灯光贴图")
            return {'CANCELLED'}
        
        mat = obj.material_slots[0].material
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # 清理现有节点
        nodes.clear()
        
        # 创建预览节点
        output_node = nodes.new('ShaderNodeOutputMaterial')
        emission = nodes.new('ShaderNodeEmission')
        image_node = nodes.new('ShaderNodeTexImage')
        uv_node = nodes.new('ShaderNodeUVMap')
        
        # 设置节点位置
        output_node.location = (300, 0)
        emission.location = (0, 0)
        image_node.location = (-300, 0)
        uv_node.location = (-500, 0)
        
        # 设置节点属性
        image_node.image = lighting_image
        uv_node.uv_map = obj.data.uv_layers[1].name
        
        # 连接节点
        links.new(uv_node.outputs[0], image_node.inputs[0])
        links.new(image_node.outputs[0], emission.inputs[0])
        links.new(emission.outputs[0], output_node.inputs[0])
        
        return {'FINISHED'}

class OBJECT_OT_preview_ao(Operator):
    """预览AO贴图"""
    bl_idname = "object.preview_ao"
    bl_label = "预览AO"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if obj is None or not obj.material_slots:
            self.report({'ERROR'}, "请选择有材质的物体")
            return {'CANCELLED'}
        
        # 获取AO贴图
        ao_image = bpy.data.images.get(f"{obj.name}_ao")
        if not ao_image:
            self.report({'ERROR'}, "未找到AO贴图")
            return {'CANCELLED'}
        
        mat = obj.material_slots[0].material
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        # 清理现有节点
        nodes.clear()
        
        # 创建预览节点
        output_node = nodes.new('ShaderNodeOutputMaterial')
        emission = nodes.new('ShaderNodeEmission')
        image_node = nodes.new('ShaderNodeTexImage')
        uv_node = nodes.new('ShaderNodeUVMap')
        
        # 设置节点位置
        output_node.location = (300, 0)
        emission.location = (0, 0)
        image_node.location = (-300, 0)
        uv_node.location = (-500, 0)
        
        # 设置节点属性
        image_node.image = ao_image
        uv_node.uv_map = obj.data.uv_layers[1].name
        
        # 连接节点
        links.new(uv_node.outputs[0], image_node.inputs[0])
        links.new(image_node.outputs[0], emission.inputs[0])
        links.new(emission.outputs[0], output_node.inputs[0])
        
        return {'FINISHED'}

class OBJECT_OT_restore_material(Operator):
    """恢复原始材质显示"""
    bl_idname = "object.restore_material"
    bl_label = "恢复显示"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        obj = context.active_object
        if obj is None or not obj.material_slots:
            self.report({'ERROR'}, "请选择有材质的物体")
            return {'CANCELLED'}
        
        # 获取组合贴图
        final_image = bpy.data.images.get(f"{obj.name}_combined")
        if not final_image:
            self.report({'ERROR'}, "未找到组合贴图")
            return {'CANCELLED'}
        
        mat = obj.material_slots[0].material
        nodes = mat.node_tree.nodes
        
        # 清理现有节点
        nodes.clear()
        
        # 创建基础节点
        output_node = nodes.new('ShaderNodeOutputMaterial')
        principled_bsdf = nodes.new('ShaderNodeBsdfPrincipled')
        image_node = nodes.new('ShaderNodeTexImage')
        uv_node = nodes.new('ShaderNodeUVMap')
        
        # 设置节点位置
        output_node.location = (300, 0)
        principled_bsdf.location = (0, 0)
        image_node.location = (-300, 0)
        uv_node.location = (-500, 0)
        
        # 设置节点属性
        image_node.image = final_image
        uv_node.uv_map = obj.data.uv_layers[1].name
        
        # 连接节点
        links = mat.node_tree.links
        links.new(uv_node.outputs[0], image_node.inputs[0])
        links.new(image_node.outputs[0], principled_bsdf.inputs[0])
        links.new(principled_bsdf.outputs[0], output_node.inputs[0])
        
        return {'FINISHED'}

def register():
    bpy.utils.register_class(OBJECT_OT_bake_textures)
    bpy.utils.register_class(OBJECT_OT_preview_lighting)
    bpy.utils.register_class(OBJECT_OT_preview_ao)
    bpy.utils.register_class(OBJECT_OT_restore_material)
    
    # 添加存储原始节点信息的属性
    bpy.types.Scene.original_nodes = bpy.props.CollectionProperty(
        type=bpy.types.PropertyGroup
    )
    bpy.types.Scene.original_links = bpy.props.CollectionProperty(
        type=bpy.types.PropertyGroup
    )

def unregister():
    bpy.utils.unregister_class(OBJECT_OT_bake_textures)
    bpy.utils.unregister_class(OBJECT_OT_preview_lighting)
    bpy.utils.unregister_class(OBJECT_OT_preview_ao)
    bpy.utils.unregister_class(OBJECT_OT_restore_material)
    
    # 删除属性
    del bpy.types.Scene.original_nodes
    del bpy.types.Scene.original_links