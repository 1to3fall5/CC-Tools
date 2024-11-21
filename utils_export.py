import bpy
import os
import json

def get_config_path():
    """获取配置文件路径"""
    return os.path.join(bpy.utils.user_resource('CONFIG'), "cc_tools_export_history.json")

def load_directories():
    """加载历史目录"""
    config_path = get_config_path()
    if os.path.exists(config_path):
        with open(config_path, 'r') as f:
            return json.load(f)
    return []

def save_directories(directories):
    """保存历史目录"""
    config_path = get_config_path()
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    with open(config_path, 'w') as f:
        json.dump(directories, f)

def update_enum(self, context):
    """更新枚举属性的选项"""
    items = []
    directories = load_directories()
    
    if not directories:
        return [('', '无历史记录', '', 0)]
        
    for i, path in enumerate(directories):
        name = os.path.basename(path.rstrip(os.sep)) or path
        items.append((path, name, path, i))
    
    return items 