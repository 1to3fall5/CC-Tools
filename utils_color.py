import bpy
import numpy as np

def create_image(name, width, height, color=(0, 0, 0, 1), alpha=True):
    """创建新的图像"""
    image = bpy.data.images.new(name=name, width=width, height=height, alpha=alpha)
    pixels = [color[0], color[1], color[2], color[3]] * (width * height)
    image.pixels = pixels
    return image

def get_color_from_ao(ao_value):
    """从AO值获取颜色"""
    return (ao_value, ao_value, ao_value, 1.0)

def get_color_from_normal(normal):
    """从法线获取颜色"""
    return ((normal[0] + 1) / 2, (normal[1] + 1) / 2, (normal[2] + 1) / 2, 1.0)

def blend_colors(color1, color2, factor):
    """混合两种颜色"""
    return tuple(c1 * (1 - factor) + c2 * factor for c1, c2 in zip(color1, color2))
