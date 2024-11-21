import bpy

# UV选择设置
selection_mode = (True, False, False)  # 顶点、边、面选择模式
selection_uv_mode = 'VERTEX'  # UV选择模式
selection_uv_sync = False  # UV同步选择
selection_uv_pivot = 'CENTER'  # UV枢轴点
selection_uv_pivot_pos = (0, 0)  # UV枢轴点位置

# 选择存储
selection_vert_indexies = set()  # 选中的顶点索引
selection_edge_indexies = set()  # 选中的边索引
selection_face_indexies = set()  # 选中的面索引
selection_uv_loops = set()  # 选中的UV循环
seam_edges = set()  # 缝合边

# 版本信息
try:
    version_str = bpy.app.version_string.split('.')
    bversion = float(f"{version_str[0]}.{version_str[1]}")
except:
    bversion = 4.0  # 默认版本号

# UV工具设置
use_uv_sync = False 