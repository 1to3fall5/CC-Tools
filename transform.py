# SPDX-FileCopyrightText: 2024 Oxicid
# SPDX-License-Identifier: GPL-3.0-or-later

if 'bpy' in locals():
    from .. import reload
    reload.reload(globals())

import bpy
import math
import random
import bl_math

import numpy as np

from bpy.types import Operator
from bpy.props import *

from math import pi, sin, cos, atan2
from mathutils import Vector
from collections import defaultdict

from bmesh.types import BMLoop

from .. import utils
from .. import types  # noqa: F401 # pylint:disable=unused-import
from .. import info
from ..utils import UMeshes
from ..types import BBox, Islands, AdvIslands, AdvIsland, FaceIsland, UnionIslands, LoopGroup


class UNIV_OT_Crop(Operator):
    bl_idname = 'uv.univ_crop'
    bl_label = 'Crop'
    bl_description = info.operator.crop_info
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(name='Axis', default='XY', items=(('XY', 'Both', ''), ('X', 'X', ''), ('Y', 'Y', '')))
    to_cursor: BoolProperty(name='To Cursor', default=False)
    individual: BoolProperty(name='Individual', default=False)
    inplace: BoolProperty(name='Inplace', default=False)
    padding: FloatProperty(name='Padding', description='Padding=1/TextureSize (1/256=0.0039)', default=0, soft_min=0, soft_max=1/256*4, max=0.49)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and (obj := context.active_object) and obj.type == 'MESH'  # noqa # pylint:disable=used-before-assignment

    def draw(self, context):
        layout = self.layout
        layout.row(align=True).prop(self, 'axis', expand=True)
        layout.prop(self, 'to_cursor')
        layout.prop(self, 'individual')
        if not self.to_cursor:
            layout.prop(self, 'inplace')
        layout.prop(self, 'padding', slider=True)

    def __init__(self):
        self.mode: str = 'DEFAULT'

    def invoke(self, context, event):
        if event.value == 'PRESS':
            return self.execute(context)

        self.to_cursor = event.ctrl
        self.individual = event.shift
        self.inplace = event.alt

        if all((event.ctrl, event.alt)):
            self.report({'INFO'}, f"Event: {info.event_to_string(event)} not implement. \n\n"
                                  f"See all variations:\n\n{self.get_event_info()}")
            self.to_cursor = False
        return self.execute(context)

    def execute(self, context):
        if all((self.to_cursor, self.inplace)):
            self.inplace = False

        match self.to_cursor, self.individual, self.inplace:
            case False, False, False:
                self.mode = 'DEFAULT'
            case True, False, False:
                self.mode = 'TO_CURSOR'
            case True, True, False:
                self.mode = 'TO_CURSOR_INDIVIDUAL'
            case False, True, False:
                self.mode = 'INDIVIDUAL'
            case False, False, True:
                self.mode = 'INPLACE'
            case False, True, True:
                self.mode = 'INDIVIDUAL_INPLACE'

        sync = context.scene.tool_settings.use_uv_select_sync
        return self.crop(self.mode, self.axis, self.padding, proportional=True, sync=sync, report=self.report)

    @staticmethod
    def crop(mode, axis, padding, proportional, sync, report=None):
        umeshes = utils.UMeshes(report=report)
        crop_args = [axis, padding, umeshes, proportional, sync]

        match mode:
            case 'DEFAULT':
                UNIV_OT_Crop.crop_default(*crop_args, extended=True)
                if not umeshes.final():
                    UNIV_OT_Crop.crop_default(*crop_args, extended=False)
            case 'TO_CURSOR':
                if not (offset := utils.get_tile_from_cursor()):
                    if report:
                        report({'INFO'}, "Cursor not found")
                    return {'CANCELLED'}
                UNIV_OT_Crop.crop_default(*crop_args, offset=offset, extended=True)
                if not umeshes.final():
                    UNIV_OT_Crop.crop_default(*crop_args, offset=offset, extended=False)
            case 'TO_CURSOR_INDIVIDUAL':
                if not (offset := utils.get_tile_from_cursor()):
                    if report:
                        report({'INFO'}, "Cursor not found")
                    return {'CANCELLED'}
                UNIV_OT_Crop.crop_individual(*crop_args, offset=offset, extended=True)
                if not umeshes.final():
                    UNIV_OT_Crop.crop_individual(*crop_args, offset=offset, extended=False)
            case 'INDIVIDUAL':
                UNIV_OT_Crop.crop_individual(*crop_args, extended=True)
                if not umeshes.final():
                    UNIV_OT_Crop.crop_individual(*crop_args, extended=False)
            case 'INDIVIDUAL_INPLACE':
                UNIV_OT_Crop.crop_individual(*crop_args, inplace=True, extended=True)
                if not umeshes.final():
                    UNIV_OT_Crop.crop_individual(*crop_args, inplace=True, extended=False)
            case 'INPLACE':
                UNIV_OT_Crop.crop_inplace(*crop_args, extended=True)
                if not umeshes.final():
                    UNIV_OT_Crop.crop_inplace(*crop_args, extended=False)
            case _:
                raise NotImplementedError(mode)

        return umeshes.update()

    @staticmethod
    def crop_default(axis, padding, umeshes, proportional, sync, offset=Vector((0, 0)), inplace=False, extended=True):
        islands_of_mesh = []
        general_bbox = BBox()
        for umesh in umeshes:
            if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, sync, extended=extended):
                general_bbox.union(islands.calc_bbox())
                islands_of_mesh.append(islands)
            umesh.update_tag = bool(islands)

        if not islands_of_mesh:
            return

        UNIV_OT_Crop.crop_ex(axis, general_bbox, inplace, islands_of_mesh, offset, padding, proportional)

    @staticmethod
    def crop_individual(axis, padding, umeshes, proportional, sync, offset=Vector((0, 0)), inplace=False, extended=True):
        for umesh in umeshes:
            if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, sync, extended=extended):
                for island in islands:
                    UNIV_OT_Crop.crop_ex(axis, island.calc_bbox(), inplace, (island, ), offset, padding, proportional)
            umesh.update_tag = bool(islands)

    @staticmethod
    def crop_inplace(axis, padding, umeshes, proportional, sync, inplace=True, extended=True):
        islands_of_tile: dict[int | list[tuple[FaceIsland | BBox]]] = {}
        for umesh in umeshes:
            if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, sync, extended=extended):
                for island in islands:
                    bbox = island.calc_bbox()
                    islands_of_tile.setdefault(bbox.tile_from_center, []).append((island, bbox))
            umesh.update_tag = bool(islands)

        if not islands_of_tile:
            return

        for tile, islands_and_bboxes in islands_of_tile.items():
            islands = []
            general_bbox = BBox()
            for island, bbox in islands_and_bboxes:
                islands.append(island)
                general_bbox.union(bbox)

            UNIV_OT_Crop.crop_ex(axis, general_bbox, inplace, islands, Vector((0, 0)), padding, proportional)

    @staticmethod
    def crop_ex(axis, bbox, inplace, islands_of_mesh, offset, padding, proportional):
        scale_x = ((1.0 - padding) / w) if (w := bbox.width) else 1
        scale_y = ((1.0 - padding) / h) if (h := bbox.height) else 1
        if proportional:
            if axis == 'XY':
                scale_x = scale_y = min(scale_x, scale_y)
            elif axis == 'X':
                scale_x = scale_y = scale_x
            else:
                scale_x = scale_y = scale_y
        else:
            if axis == 'X':
                scale_y = 1
            if axis == 'Y':
                scale_x = 1

        scale = Vector((scale_x, scale_y))
        bbox.scale(scale)
        delta = Vector((padding, padding)) / 2 - bbox.min + offset
        if axis == 'XY':
            if inplace:
                delta += Vector(math.floor(val) for val in bbox.center)
        elif axis == 'X':
            delta.y = 0
            if inplace:
                delta.x += math.floor(bbox.center_x)
        else:
            delta.x = 0
            if inplace:
                delta.y += math.floor(bbox.center_y)
        for islands in islands_of_mesh:
            islands.scale(scale, bbox.center)
            islands.move(delta)

    @staticmethod
    def get_event_info():
        return info.operator.crop_event_info_ex


class UNIV_OT_Fill(UNIV_OT_Crop):
    bl_idname = 'uv.univ_fill'
    bl_label = 'Fill'
    bl_description = info.operator.fill_info
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        sync = context.scene.tool_settings.use_uv_select_sync
        return self.crop(self.mode, self.axis, self.padding, proportional=False, sync=sync, report=self.report)

    @staticmethod
    def get_event_info():
        return info.operator.fill_event_info_ex


align_align_direction_items = (
    ('UPPER', 'Upper', ''),
    ('BOTTOM', 'Bottom', ''),
    ('LEFT', 'Left', ''),
    ('RIGHT', 'Right', ''),
    ('CENTER', 'Center', ''),
    ('HORIZONTAL', 'Horizontal', ''),
    ('VERTICAL', 'Vertical', ''),
    ('LEFT_UPPER', 'Left upper', ''),
    ('RIGHT_UPPER', 'Right upper', ''),
    ('LEFT_BOTTOM', 'Left bottom', ''),
    ('RIGHT_BOTTOM', 'Right bottom', ''),
)
class UNIV_OT_Align(Operator):
    bl_idname = 'uv.univ_align'
    bl_label = 'Align'
    bl_description = info.operator.align_info
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name="Mode", default='MOVE', items=(
        ('ALIGN', 'Align', ''),
        ('MOVE', 'Move', ''),
        ('ALIGN_CURSOR', 'Move cursor to selected', ''),
        ('ALIGN_TO_CURSOR', 'Align to cursor', ''),
        ('ALIGN_TO_CURSOR_UNION', 'Align to cursor union', ''),
        ('CURSOR_TO_TILE', 'Align cursor to tile', ''),
        # ('MOVE_COLLISION', 'Collision move', '')
    ))

    direction: EnumProperty(name="Direction", default='UPPER', items=align_align_direction_items)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and (obj := context.active_object) and obj.type == 'MESH'  # noqa # pylint:disable=used-before-assignment

    def draw(self, context):
        self.layout.prop(self, 'direction')
        self.layout.column(align=True).prop(self, 'mode', expand=True)

    def invoke(self, context, event):
        match event.ctrl, event.shift, event.alt:
            case False, False, False:
                self.mode = 'ALIGN'
            case True, False, False:
                self.mode = 'ALIGN_TO_CURSOR'
            case True, True, True:
                self.mode = 'ALIGN_TO_CURSOR_UNION'
            case False, False, True:
                self.mode = 'ALIGN_CURSOR'
            case True, False, True:
                self.mode = 'CURSOR_TO_TILE'
            case False, True, False:
                self.mode = 'MOVE'
            case _:
                self.report({'INFO'}, f"Event: {info.event_to_string(event)} not implement. \n\n"
                                      f"See all variations:\n\n{info.operator.align_event_info_ex}")
                return {'CANCELLED'}
        return self.execute(context)

    def execute(self, context):
        return self.align(self.mode, self.direction, sync=context.scene.tool_settings.use_uv_select_sync, report=self.report)

    @staticmethod
    def align(mode, direction, sync, report=None):
        umeshes = utils.UMeshes(report=report)

        match mode:
            case 'ALIGN':
                UNIV_OT_Align.align_ex(direction, sync,  umeshes, selected=True)
                if not umeshes.final():
                    UNIV_OT_Align.align_ex(direction, sync,  umeshes,  selected=False)

            case 'ALIGN_TO_CURSOR':
                if not (cursor_loc := utils.get_cursor_location()):
                    umeshes.report({'INFO'}, "Cursor not found")
                    return {'CANCELLED'}
                UNIV_OT_Align.move_to_cursor_ex(cursor_loc, direction, umeshes, sync, selected=True)
                if not umeshes.final():
                    UNIV_OT_Align.move_to_cursor_ex(cursor_loc, direction, umeshes, sync, selected=False)

            case 'ALIGN_TO_CURSOR_UNION':
                if not (cursor_loc := utils.get_cursor_location()):
                    umeshes.report({'INFO'}, "Cursor not found")
                    return {'CANCELLED'}
                UNIV_OT_Align.move_to_cursor_union_ex(cursor_loc, direction, umeshes, sync, selected=True)
                if not umeshes.final():
                    UNIV_OT_Align.move_to_cursor_union_ex(cursor_loc, direction, umeshes, sync, selected=False)

            case 'ALIGN_CURSOR':
                if not (cursor_loc := utils.get_cursor_location()):
                    umeshes.report({'INFO'}, "Cursor not found")
                    return {'CANCELLED'}
                general_bbox = UNIV_OT_Align.align_cursor_ex(umeshes, sync, selected=True)
                if not general_bbox.is_valid:
                    general_bbox = UNIV_OT_Align.align_cursor_ex(umeshes, sync, selected=False)
                if not general_bbox.is_valid:
                    umeshes.report()
                    return {'CANCELLED'}
                UNIV_OT_Align.align_cursor(direction, general_bbox, cursor_loc)
                return {'FINISHED'}

            case 'CURSOR_TO_TILE':
                if not (cursor_loc := utils.get_cursor_location()):
                    umeshes.report({'INFO'}, "Cursor not found")
                    return {'CANCELLED'}
                UNIV_OT_Align.align_cursor_to_tile(direction, cursor_loc)
                return {'FINISHED'}

            case 'MOVE':
                UNIV_OT_Align.move_ex(direction, sync, umeshes, selected=True)
                if not umeshes.final():
                    UNIV_OT_Align.move_ex(direction, sync, umeshes, selected=False)

            case _:
                raise NotImplementedError(mode)

        return umeshes.update()

    @staticmethod
    def move_to_cursor_ex(cursor_loc, direction, umeshes, sync, selected=True):
        all_groups = []  # islands, bboxes, uv_layer or corners, uv_layer
        island_mode = utils.is_island_mode()
        general_bbox = BBox.init_from_minmax(cursor_loc, cursor_loc)
        for umesh in umeshes:
            if island_mode:
                if islands := Islands.calc(umesh, selected=selected):
                    for island in islands:
                        bbox = island.calc_bbox()
                        all_groups.append((island, bbox, umesh.uv_layer))
                umesh.update_tag = bool(islands)
            else:
                if corners := utils.calc_uv_corners(umesh.bm, umesh.uv_layer, sync, selected=selected):
                    all_groups.append((corners, umesh.uv_layer))
                umesh.update_tag = bool(corners)
        if island_mode:
            UNIV_OT_Align.align_islands(all_groups, direction, general_bbox, invert=True)
        else:  # Vertices or Edges UV selection mode
            UNIV_OT_Align.align_corners(all_groups, direction, general_bbox)

    @staticmethod
    def move_to_cursor_union_ex(cursor_loc, direction, umeshes, sync, selected=True):
        all_groups = []  # islands, bboxes, uv_layer or corners, uv_layer
        target_bbox = BBox.init_from_minmax(cursor_loc, cursor_loc)
        general_bbox = BBox()
        for umesh in umeshes:
            if faces := utils.calc_uv_faces(umesh.bm, umesh.uv_layer, sync, selected=selected):
                island = FaceIsland(faces, umesh.bm, umesh.uv_layer)
                bbox = island.calc_bbox()
                general_bbox.union(bbox)
                all_groups.append([island, bbox, umesh.uv_layer])
            umesh.update_tag = bool(faces)
        for group in all_groups:
            group[1] = general_bbox
        UNIV_OT_Align.align_islands(all_groups, direction, target_bbox, invert=True)

    @staticmethod
    def align_cursor_ex(umeshes, sync, selected):
        all_groups = []  # islands, bboxes, uv_layer or corners, uv_layer
        general_bbox = BBox()
        for umesh in umeshes:
            if corners := utils.calc_uv_corners(umesh.bm, umesh.uv_layer, sync, selected=selected):  # TODO: Implement bbox by individual modes
                all_groups.append((corners, umesh.uv_layer))
                bbox = BBox.calc_bbox_uv_corners(corners, umesh.uv_layer)
                general_bbox.union(bbox)
        return general_bbox

    @staticmethod
    def align_ex(direction, sync, umeshes, selected=True):
        all_groups = []  # islands, bboxes, uv_layer or corners, uv_layer
        general_bbox = BBox()
        island_mode = utils.is_island_mode()
        for umesh in umeshes:
            if island_mode:
                if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, sync, extended=selected):
                    for island in islands:
                        bbox = island.calc_bbox()
                        general_bbox.union(bbox)

                        all_groups.append((island, bbox, umesh.uv_layer))
                umesh.update_tag = bool(islands)
            else:
                if corners := utils.calc_uv_corners(umesh.bm, umesh.uv_layer, sync, selected=selected):
                    bbox = BBox.calc_bbox_uv_corners(corners, umesh.uv_layer)
                    general_bbox.union(bbox)

                    all_groups.append((corners, umesh.uv_layer))
                umesh.update_tag = bool(corners)
        if island_mode:
            UNIV_OT_Align.align_islands(all_groups, direction, general_bbox)
        else:  # Vertices or Edges UV selection mode
            UNIV_OT_Align.align_corners(all_groups, direction, general_bbox)  # TODO Individual ALign for Vertical and Horizontal or all

    @staticmethod
    def move_ex(direction, sync, umeshes, selected=True):
        island_mode = utils.is_island_mode()
        for umesh in umeshes:
            if island_mode:
                if islands := Islands.calc(umesh, selected=selected):
                    match direction:
                        case 'CENTER':
                            for island in islands:
                                bbox = island.calc_bbox()
                                delta = Vector((0.5, 0.5)) - bbox.center
                                island.move(delta)  # ToDO: Implement update flags for return state move
                        case 'HORIZONTAL':
                            for island in islands:
                                bbox = island.calc_bbox()
                                delta_y = 0.5 - bbox.center.y
                                island.move(Vector((0.0, delta_y)))
                        case 'VERTICAL':
                            for island in islands:
                                bbox = island.calc_bbox()
                                delta_x = 0.5 - bbox.center.x
                                island.move(Vector((delta_x, 0.0)))
                        case _:
                            move_value = Vector(UNIV_OT_Align.get_move_value(direction))
                            for island in islands:
                                island.move(move_value)
                umesh.update_tag = bool(islands)
            else:
                if corners := utils.calc_uv_corners(umesh.bm, umesh.uv_layer, sync, selected=selected):
                    match direction:
                        case 'CENTER':
                            for corner in corners:
                                corner[umesh.uv_layer].uv = 0.5, 0.5
                        case 'HORIZONTAL':
                            for corner in corners:
                                corner[umesh.uv_layer].uv.x = 0.5
                        case 'VERTICAL':
                            for corner in corners:
                                corner[umesh.uv_layer].uv.y = 0.5
                        case _:
                            move_value = Vector(UNIV_OT_Align.get_move_value(direction))
                            for corner in corners:
                                corner[umesh.uv_layer].uv += move_value
                umesh.update_tag = bool(corners)

    @staticmethod
    def align_islands(groups, direction, general_bbox, invert=False):
        for island, bounds, uv_layer in groups:
            center = bounds.center
            match direction:
                case 'UPPER':
                    delta = (0, (general_bbox.min - bounds.min).y) if invert else (0, (general_bbox.max - bounds.max).y)
                case 'BOTTOM':
                    delta = (0, (general_bbox.max - bounds.max).y) if invert else (0, (general_bbox.min - bounds.min).y)
                case 'LEFT':
                    delta = ((general_bbox.max - bounds.max).x, 0) if invert else ((general_bbox.min - bounds.min).x, 0)
                case 'RIGHT':
                    delta = ((general_bbox.min - bounds.min).x, 0) if invert else ((general_bbox.max - bounds.max).x, 0)
                case 'CENTER':
                    delta = general_bbox.center - center
                case 'HORIZONTAL':
                    delta = (0, (general_bbox.center - center).y)
                case 'VERTICAL':
                    delta = (general_bbox.center - center).x, 0
                case 'RIGHT_UPPER':
                    delta = general_bbox.min - bounds.min if invert else general_bbox.max - bounds.max
                case 'LEFT_UPPER':
                    if invert:
                        delta = (general_bbox.max - bounds.max).x, (general_bbox.min - bounds.min).y
                    else:
                        delta = (general_bbox.min - bounds.min).x, (general_bbox.max - bounds.max).y
                case 'LEFT_BOTTOM':
                    delta = general_bbox.max - bounds.max if invert else general_bbox.min - bounds.min
                case 'RIGHT_BOTTOM':
                    if invert:
                        delta = (general_bbox.min - bounds.min).x, (general_bbox.max - bounds.max).y
                    else:
                        delta = (general_bbox.max - bounds.max).x, (general_bbox.min - bounds.min).y
                case _:
                    raise NotImplementedError(direction)
            island.move(Vector(delta))

    @staticmethod
    def align_corners(groups, direction, general_bbox):

        match direction:
            case 'LEFT' | 'RIGHT' | 'VERTICAL':
                if direction == 'LEFT':
                    destination = general_bbox.min.x
                elif direction == 'RIGHT':
                    destination = general_bbox.max.x
                else:
                    destination = general_bbox.center.x

                for luvs, uv_layer in groups:
                    for luv in luvs:
                        luv[uv_layer].uv[0] = destination
            case 'UPPER' | 'BOTTOM' | 'HORIZONTAL':
                if direction == 'UPPER':
                    destination = general_bbox.max.y
                elif direction == 'BOTTOM':
                    destination = general_bbox.min.y
                else:
                    destination = general_bbox.center.y

                for luvs, uv_layer in groups:
                    for luv in luvs:
                        luv[uv_layer].uv[1] = destination
            case _:
                if direction == 'CENTER':
                    destination = general_bbox.center
                elif direction == 'LEFT_BOTTOM':
                    destination = general_bbox.left_bottom
                elif direction == 'RIGHT_UPPER':
                    destination = general_bbox.right_upper
                elif direction == 'LEFT_UPPER':
                    destination = general_bbox.left_upper
                elif direction == 'RIGHT_BOTTOM':
                    destination = general_bbox.right_bottom
                else:
                    raise NotImplementedError(direction)

                for luvs, uv_layer in groups:
                    for luv in luvs:
                        luv[uv_layer].uv = destination

    @staticmethod
    def align_cursor(direction: str, general_bbox, cursor_loc):

        if direction in ('UPPER', 'BOTTOM'):
            loc = getattr(general_bbox, direction.lower())
            loc.x = cursor_loc.x
            utils.set_cursor_location(loc)
        elif direction in ('RIGHT', 'LEFT'):
            loc = getattr(general_bbox, direction.lower())
            loc.y = cursor_loc.y
            utils.set_cursor_location(loc)
        elif loc := getattr(general_bbox, direction.lower(), False):
            utils.set_cursor_location(loc)
        elif direction == 'VERTICAL':
            utils.set_cursor_location(Vector((general_bbox.center.x, cursor_loc.y)))
        elif direction == 'HORIZONTAL':
            utils.set_cursor_location(Vector((cursor_loc.x, general_bbox.center.y)))
        else:
            raise NotImplementedError(direction)

    @staticmethod
    def align_cursor_to_tile(direction: str, cursor_loc):
        def pad_floor(value):
            f = np.floor(np.float16(value))
            return np.nextafter(f, f + np.float16(1.0))

        def pad_ceil(value):
            f = np.floor(np.float16(value))
            return np.nextafter(f + np.float16(1.0), f)

        x, y = cursor_loc
        match direction:
            case 'UPPER':
                y = pad_ceil(y)
            case 'BOTTOM':
                y = pad_floor(y)
            case 'LEFT':
                x = pad_floor(x)
            case 'RIGHT':
                x = pad_ceil(x)
            case 'RIGHT_UPPER':
                x = pad_ceil(x)
                y = pad_ceil(y)
            case 'LEFT_UPPER':
                x = pad_floor(x)
                y = pad_ceil(y)
            case 'LEFT_BOTTOM':
                x = pad_floor(x)
                y = pad_floor(y)
            case 'RIGHT_BOTTOM':
                x = pad_ceil(x)
                y = pad_floor(y)
            case 'CENTER':
                x = np.floor(x) + 0.5
                y = np.floor(y) + 0.5
            case 'HORIZONTAL':
                y = np.floor(y) + 0.5
            case 'VERTICAL':
                x = np.floor(x) + 0.5
            case _:
                raise NotImplementedError(direction)
        utils.set_cursor_location((x, y))

    @staticmethod
    def get_move_value(direction):
        match direction:
            case 'UPPER':
                return 0, 1
            case 'BOTTOM':
                return 0, -1
            case 'LEFT':
                return -1, 0
            case 'RIGHT':
                return 1, 0
            case 'RIGHT_UPPER':
                return 1, 1
            case 'LEFT_UPPER':
                return -1, 1
            case 'LEFT_BOTTOM':
                return -1, -1
            case 'RIGHT_BOTTOM':
                return 1, -1
            case _:
                raise NotImplementedError(direction)
        return

class UNIV_OT_Flip(Operator):
    bl_idname = 'uv.univ_flip'
    bl_label = 'Flip'
    bl_description = 'FlipX and FlipY'
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name='Mode', default='DEFAULT', items=(
        ('DEFAULT', 'Default', ''),
        ('BY_CURSOR', 'By cursor', ''),
        ('INDIVIDUAL', 'Individual', ''),
        ('FLIPPED', 'Flipped', ''),
    ))

    axis: EnumProperty(name='Axis', default='X', items=(('X', 'X', ''), ('Y', 'Y', '')))

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and (obj := context.active_object) and obj.type == 'MESH'  # noqa # pylint:disable=used-before-assignment

    def draw(self, context):
        self.layout.row(align=True).prop(self, 'axis', expand=True)
        self.layout.column(align=True).prop(self, 'mode', expand=True)

    def invoke(self, context, event):
        if event.value == 'PRESS':
            return self.execute(context)
        match event.ctrl, event.shift, event.alt:
            case False, False, False:
                self.mode = 'DEFAULT'
            case True, False, False:
                self.mode = 'BY_CURSOR'
            case False, True, False:
                self.mode = 'INDIVIDUAL'
            case False, False, True:
                self.mode = 'FLIPPED'
            case _:
                self.report({'INFO'}, f"Event: {info.event_to_string(event)} not implement. \n\n")
                return {'CANCELLED'}
        return self.execute(context)

    def __init__(self):
        self.umeshes = []
        self.scale = Vector((1, 1))

    def execute(self, context):
        self.umeshes = utils.UMeshes(report=self.report)
        self.scale = self.get_flip_scale_from_axis(self.axis)

        match self.mode:
            case 'DEFAULT':
                self.flip_ex(extended=self.umeshes.has_selected_uv_faces)
            case 'BY_CURSOR':
                if not (cursor_loc := utils.get_cursor_location()):
                    self.umeshes.report({'INFO'}, "Cursor not found")
                self.flip_by_cursor(cursor=cursor_loc, extended=self.umeshes.has_selected_uv_faces)
            case 'INDIVIDUAL':
                self.flip_individual(extended=self.umeshes.has_selected_uv_faces)
            case 'FLIPPED':
                self.flip_flipped(extended=self.umeshes.has_selected_uv_faces)
            case _:
                raise NotImplementedError(self.mode)

        return self.umeshes.update()

    def flip_ex(self, extended):
        islands_of_mesh = []
        general_bbox = BBox()
        for umesh in self.umeshes:
            if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, umesh.sync, extended=extended):
                general_bbox.union(islands.calc_bbox())
                islands_of_mesh.append(islands)
            umesh.update_tag = bool(islands)

        if not islands_of_mesh:
            return

        pivot = general_bbox.center
        for islands in islands_of_mesh:
            islands.scale(scale=self.scale, pivot=pivot)

    def flip_by_cursor(self, cursor, extended):
        for umesh in self.umeshes:
            if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, umesh.sync, extended=extended):
                islands.scale(scale=self.scale, pivot=cursor)
            umesh.update_tag = bool(islands)

    def flip_individual(self, extended):
        for umesh in self.umeshes:
            if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, umesh.sync, extended=extended):
                for island in islands:
                    island.scale(scale=self.scale, pivot=island.calc_bbox().center)
            umesh.update_tag = bool(islands)

    def flip_flipped(self, extended):
        islands_count = 0

        for umesh in self.umeshes:
            if islands := self.calc_extended_or_visible_flipped_islands(umesh, extended=extended):
                for island in islands:
                    island.scale(scale=self.scale, pivot=island.calc_bbox().center)
                islands_count += len(islands)
            umesh.update_tag = bool(islands)

        if not islands_count:
            return self.report({'INFO'}, 'Flipped islands not found')
        return self.report({'INFO'}, f'Found {islands_count} Flipped islands')

    @staticmethod
    def calc_extended_or_visible_flipped_islands(umesh_: utils.UMesh, extended):
        uv = umesh_.uv_layer
        if extended:
            if umesh_.is_full_face_deselected:
                return Islands([], None, None)

        Islands.tag_filter_visible(umesh_.bm, umesh_.sync)

        for f_ in umesh_.bm.faces:
            if f_.tag:
                f_.tag = utils.is_flipped_uv(f_, uv)

        if extended:
            islands_ = [Islands.island_type(i, umesh_.bm, uv) for i in Islands.calc_iter_ex(umesh_.bm, uv) if
                       Islands.island_filter_is_any_face_selected(i, uv, umesh_.sync)]
        else:
            islands_ = [Islands.island_type(i, umesh_.bm, uv) for i in Islands.calc_iter_ex(umesh_.bm, uv)]
        return Islands(islands_, umesh_.bm, umesh_.uv_layer)

    @staticmethod
    def get_flip_scale_from_axis(axis):
        return Vector((-1, 1)) if axis == 'X' else Vector((1, -1))


class UNIV_OT_Rotate(Operator):
    bl_idname = 'uv.univ_rotate'
    bl_label = 'Rotate'
    bl_description = 'Rotate CW and Rotate CCW'
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name='Mode',
                       default='DEFAULT',
                       items=(('DEFAULT', 'Default', ''),
                              ('INDIVIDUAL', 'Individual', ''),
                              ('BY_CURSOR', 'By Cursor', ''))
                       )
    rot_dir: EnumProperty(name='Direction of rotation', default='CW', items=(('CW', 'CW', ''), ('CCW', 'CCW', '')))
    user_angle: FloatProperty(name='Angle', default=pi*0.5, min=0, max=pi, soft_min=math.radians(5.0), subtype='ANGLE')
    use_correct_aspect: BoolProperty(name='Correct Aspect', default=True)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and (obj := context.active_object) and obj.type == 'MESH'  # noqa # pylint:disable=used-before-assignment

    def draw(self, context):
        self.layout.prop(self, 'user_angle', slider=True)
        self.layout.prop(self, 'use_correct_aspect', toggle=1)
        self.layout.row(align=True).prop(self, 'rot_dir', expand=True)
        self.layout.row(align=True).prop(self, 'mode', expand=True)

    def invoke(self, context, event):
        if event.value == 'PRESS':
            return self.execute(context)

        self.rot_dir = 'CCW' if event.alt else 'CW'
        if event.shift:
            self.mode = 'INDIVIDUAL'
        elif event.ctrl:
            self.mode = 'BY_CURSOR'
        else:
            self.mode = 'DEFAULT'
        return self.execute(context)

    def __init__(self):
        self.umeshes = []
        self.angle = 0.0
        self.aspect = 1.0

    def execute(self, context):
        self.umeshes = utils.UMeshes(report=self.report)
        self.angle = (-self.user_angle) if self.rot_dir == 'CCW' else self.user_angle
        self.aspect = utils.get_aspect_ratio() if self.use_correct_aspect else 1.0

        if self.mode == 'DEFAULT':
            self.rotate(extended=self.umeshes.has_selected_uv_faces)

        elif self.mode == 'BY_CURSOR':
            if not (cursor_loc := utils.get_cursor_location()):
                self.report({'INFO'}, "Cursor not found")
                return {'CANCELLED'}
            self.rotate_by_cursor(cursor=cursor_loc, extended=self.umeshes.has_selected_uv_faces)

        elif self.mode == 'INDIVIDUAL':
            self.rotate_individual(extended=self.umeshes.has_selected_uv_faces)
        else:
            raise NotImplementedError()

        return self.umeshes.update()

    def rotate(self, extended):
        islands_of_mesh = []
        general_bbox = BBox()
        for umesh in self.umeshes:
            if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, umesh.sync, extended=extended):
                general_bbox.union(islands.calc_bbox())
                islands_of_mesh.append(islands)
            umesh.update_tag = bool(islands)

        pivot = general_bbox.center
        for islands in islands_of_mesh:
            islands.rotate(self.angle, pivot=pivot, aspect=self.aspect)

    def rotate_by_cursor(self, cursor, extended):
        for umesh in self.umeshes:
            if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, umesh.sync, extended=extended):
                islands.rotate(self.angle, pivot=cursor, aspect=self.aspect)
            umesh.update_tag = bool(islands)

    def rotate_individual(self,  extended):
        for umesh in self.umeshes:
            if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, umesh.sync, extended=extended):
                for island in islands:
                    island.rotate(self.angle, pivot=island.calc_bbox().center, aspect=self.aspect)
            umesh.update_tag = bool(islands)


class UNIV_OT_Sort(Operator):
    bl_idname = 'uv.univ_sort'
    bl_label = 'Sort'
    bl_description = 'Sort'
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(name='Axis', default='AUTO', items=(('AUTO', 'Auto', ''), ('X', 'X', ''), ('Y', 'Y', '')))
    padding: FloatProperty(name='Padding', default=1/2048, min=0, soft_max=0.1,)
    sub_padding: FloatProperty(name='Sub Padding', default=0.1, min=0, soft_max=0.2,)
    area_subgroups: IntProperty(name='Area Subgroups', default=4, min=1, max=200, soft_max=8)
    reverse: BoolProperty(name='Reverse', default=True)
    to_cursor: BoolProperty(name='To Cursor', default=False)
    align: BoolProperty(name='Orient', default=False)  # TODO: Rename align to orient
    overlapped: BoolProperty(name='Overlapped', default=False)
    subgroup_type: EnumProperty(name='Subgroup Type', default='NONE', items=(
        ('NONE', 'None', ''),
        ('AREA', 'Area', ''),
        ('OBJECTS', 'Objects', ''),
        ('MATERIALS', 'Materials', '')))

    def draw(self, context):
        layout = self.layout.row()
        layout.prop(self, 'axis', expand=True)
        layout = self.layout
        layout.prop(self, 'reverse')
        layout.prop(self, 'to_cursor')
        layout.prop(self, 'align')
        if self.subgroup_type == 'NONE':
            layout.prop(self, 'overlapped')
        layout.prop(self, 'padding', slider=True)
        if self.subgroup_type != 'NONE':
            layout.prop(self, 'sub_padding', slider=True)
        if self.subgroup_type == 'AREA':
            layout.prop(self, 'area_subgroups')
        layout = self.layout.row()
        layout.prop(self, 'subgroup_type', expand=True)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and (obj := context.active_object) and obj.type == 'MESH'  # noqa # pylint:disable=used-before-assignment

    def invoke(self, context, event):
        if event.value == 'PRESS':
            return self.execute(context)
        self.to_cursor = event.ctrl
        self.overlapped = event.shift
        self.align = event.alt
        return self.execute(context)

    def __init__(self):
        self.sync: bool = bpy.context.scene.tool_settings.use_uv_select_sync
        self.update_tag: bool = False
        self.cursor_loc: Vector | None = None
        self.umeshes: UMeshes | None = None

    def execute(self, context):
        self.update_tag = False
        self.umeshes = utils.UMeshes(report=self.report)
        if self.to_cursor:
            if not (cursor_loc := utils.get_cursor_location()):
                self.report({'INFO'}, "Cursor not found")
                return {'CANCELLED'}
            self.cursor_loc = cursor_loc
        else:
            self.cursor_loc = None

        if self.subgroup_type != 'NONE':
            self.overlapped = False

        if not self.overlapped:
            self.sort_individual_preprocessing(extended=True)
            if not self.umeshes.final():
                self.sort_individual_preprocessing(extended=False)
        else:
            self.sort_overlapped_preprocessing(extended=True)
            if not self.umeshes.final():
                self.sort_overlapped_preprocessing(extended=False)

        if not self.update_tag:
            return self.umeshes.cancel_with_report(info='Islands is sorted')
        return self.umeshes.update()

    def sort_overlapped_preprocessing(self, extended=True):
        _islands: list[AdvIsland] = []
        for umesh in self.umeshes:
            if adv_islands := AdvIslands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, self.sync, extended=extended):
                adv_islands.calc_tris()
                adv_islands.calc_flat_coords()
                _islands.extend(adv_islands)
            umesh.update_tag = bool(adv_islands)

        if not _islands:
            return

        general_bbox = BBox()
        union_islands_groups = UnionIslands.calc_overlapped_island_groups(_islands)
        for union_island in union_islands_groups:
            if self.align:
                isl_coords = union_island.calc_convex_points()
                general_bbox.union(union_island.bbox)
                angle = utils.calc_min_align_angle(isl_coords)

                if not math.isclose(angle, 0, abs_tol=0.0001):
                    union_island.rotate_simple(angle)
                    union_island.calc_bbox()
            else:
                bb = union_island.bbox
                general_bbox.union(bb)

        is_horizontal = self.is_horizontal(general_bbox)
        margin = general_bbox.min if (self.cursor_loc is None) else self.cursor_loc
        self.sort_islands(is_horizontal, margin, union_islands_groups)

    def sort_individual_preprocessing(self, extended=True):
        _islands: list[AdvIsland] | list[AdvIslands] = []
        general_bbox = BBox()
        for umesh in self.umeshes:
            if adv_islands := AdvIslands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, self.sync, extended=extended):
                if self.align:
                    for island in adv_islands:
                        isl_coords = island.calc_convex_points()
                        general_bbox.union(island.bbox)
                        angle = utils.calc_min_align_angle(isl_coords)
                        if not math.isclose(angle, 0, abs_tol=0.0001):
                            island.rotate_simple(angle)
                            island.calc_bbox()
                else:
                    for island in adv_islands:
                        general_bbox.union(island.bbox)
                if self.subgroup_type == 'OBJECTS':
                    _islands.append(adv_islands)  # noqa
                elif self.subgroup_type == 'MATERIALS':
                    adv_islands.calc_materials(umesh)
                    _islands.extend(adv_islands)
                elif self.subgroup_type == 'AREA':
                    adv_islands.calc_tris()
                    adv_islands.calc_flat_coords()
                    adv_islands.calc_area()
                    _islands.extend(adv_islands)
                else:
                    _islands.extend(adv_islands)

            umesh.update_tag = bool(adv_islands)

        if not _islands:
            return

        is_horizontal = self.is_horizontal(general_bbox)
        margin = general_bbox.min if (self.cursor_loc is None) else self.cursor_loc

        if self.subgroup_type == 'NONE':
            self.sort_islands(is_horizontal, margin, _islands)
        elif self.subgroup_type == 'OBJECTS':
            for islands in _islands:
                self.sort_islands(is_horizontal, margin, islands.islands)  # noqa
        elif self.subgroup_type == 'MATERIALS':
            subgroups = defaultdict(list)
            for island in _islands:
                subgroups[island.info.materials].append(island)  # noqa
            for islands in subgroups.values():
                self.sort_islands(is_horizontal, margin, islands)
        else:  # 'AREA'
            subgroups = self.calc_area_subgroups(_islands)
            if self.reverse:
                for islands in reversed(subgroups):
                    self.sort_islands(is_horizontal, margin, islands)
            else:
                for islands in subgroups:
                    self.sort_islands(is_horizontal, margin, islands)

    def calc_area_subgroups(self, islands: list[AdvIsland]):
        islands.sort(reverse=True, key=lambda a: a.info.area_uv)
        splitted = []
        if len(islands) > 1:
            start = islands[0].info.area_uv
            end = islands[-1].info.area_uv
            segment = (start - end) / self.area_subgroups
            end += 0.00001

            for i in range(self.area_subgroups):
                seg = []
                end += segment
                if not islands:
                    break

                for j in range(len(islands) - 1, -1, -1):
                    if islands[j].info.area_uv <= end:
                        seg.append(islands.pop())
                    else:
                        break
                if seg:
                    splitted.append(seg)

            assert (not islands), 'Extremal Values'
        else:
            splitted = [islands]
        return splitted

    def sort_islands(self, is_horizontal: bool, margin: Vector, islands: list[AdvIsland | UnionIslands] | AdvIslands):
        islands.sort(key=lambda x: x.bbox.max_length, reverse=self.reverse)
        if is_horizontal:
            for island in islands:
                width = island.bbox.width
                if self.align and island.bbox.height < width:
                    width = island.bbox.height
                    self.update_tag |= island.rotate(pi * 0.5, island.bbox.center)
                    island.calc_bbox()
                self.update_tag |= island.set_position(margin, _from=island.bbox.min)
                margin.x += self.padding + width
            margin.x += self.sub_padding
        else:
            for island in islands:
                height = island.bbox.height
                if self.align and island.bbox.width < height:
                    height = island.bbox.width
                    self.update_tag |= island.rotate(pi * 0.5, island.bbox.center)
                    island.calc_bbox()  # TODO: Optimize this
                self.update_tag |= island.set_position(margin, _from=island.bbox.min)
                margin.y += self.padding + height
            margin.y += self.sub_padding

    def is_horizontal(self, bbox):
        if self.axis == 'AUTO':
            return bbox.width * 2 > bbox.height
        else:
            return self.axis == 'X'


class UNIV_OT_Distribute(Operator):
    bl_idname = 'uv.univ_distribute'
    bl_label = 'Distribute'
    bl_description = 'Distribute'
    bl_options = {'REGISTER', 'UNDO'}

    axis: EnumProperty(name='Axis', default='AUTO', items=(('AUTO', 'Auto', ''), ('X', 'X', ''), ('Y', 'Y', '')))
    space: EnumProperty(name='Space', default='ALIGN', items=(('ALIGN', 'Align', ''), ('SPACE', 'Space', '')),
                        description='Distribution of islands at equal distances')
    padding: FloatProperty(name='Padding', default=1/2048, min=0, soft_max=0.1,)
    to_cursor: BoolProperty(name='To Cursor', default=False)
    overlapped: BoolProperty(name='Overlapped', default=False)
    break_: BoolProperty(name='Break', default=False)
    angle: FloatProperty(name='Smooth Angle', default=math.radians(66.0), subtype='ANGLE', min=math.radians(5.0), max=math.radians(180.0))

    def draw(self, context):
        if not self.break_:
            layout = self.layout.row()
            layout.prop(self, 'space', expand=True)
            layout = self.layout
            layout.prop(self, 'overlapped')
            layout.prop(self, 'to_cursor')
            layout.prop(self, 'break_')
        else:
            layout = self.layout.row()
            layout.prop(self, 'break_')
            layout.prop(self, 'angle', slider=True)

        layout = self.layout
        layout.prop(self, 'padding', slider=True)
        layout = self.layout.row()
        layout.prop(self, 'axis', expand=True)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and (obj := context.active_object) and obj.type == 'MESH'  # noqa # pylint:disable=used-before-assignment

    def invoke(self, context, event):
        if event.value == 'PRESS':
            return self.execute(context)
        self.to_cursor = event.ctrl
        self.overlapped = event.shift
        self.break_ = event.alt
        return self.execute(context)

    def __init__(self):
        self.sync = bpy.context.scene.tool_settings.use_uv_select_sync
        self.umeshes: utils.UMeshes | None = None
        self.cursor_loc: Vector | None = None
        self.update_tag = False

    def execute(self, context):
        self.umeshes = utils.UMeshes(report=self.report)
        if self.to_cursor and not self.break_:
            if not (cursor_loc := utils.get_cursor_location()):
                self.report({'INFO'}, "Cursor not found")
                return {'CANCELLED'}
            self.cursor_loc = cursor_loc
        else:
            self.cursor_loc = None

        if self.break_:
            max_angle = max(umesh.smooth_angle for umesh in self.umeshes)
            self.angle = min(self.angle, max_angle)  # clamp for angle

            self.distribute_break_preprocessing(extended=True)
            if not self.umeshes.final():
                self.distribute_break_preprocessing(extended=False)
        elif self.space == 'SPACE':
            self.distribute_space(extended=True)
            if not self.umeshes.final():
                self.distribute_space(extended=False)
        else:
            self.distribute(extended=True)
            if not self.umeshes.final():
                self.distribute(extended=False)
        self.umeshes.update()
        return {'FINISHED'}

    def distribute_break_preprocessing(self, extended):
        cancel = False
        for umesh in self.umeshes:
            self.update_tag = False
            angle = min(self.angle, umesh.smooth_angle)
            if adv_islands := AdvIslands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, self.sync, extended=extended):
                for isl in adv_islands:
                    if len(isl) == 1:
                        continue
                    sub_islands = isl.calc_sub_islands_all(angle)
                    if len(sub_islands) > 1:
                        self.distribute_ex(list(sub_islands), isl.bbox)
            umesh.update_tag = self.update_tag
            cancel |= bool(adv_islands)
        if cancel and not any(umesh.update_tag for umesh in self.umeshes):
            self.umeshes.cancel_with_report(info=f"Islands for break not found")

    def distribute_ex(self, _islands, general_bbox):
        if len(_islands) < 2:
            if len(_islands) == 1:
                self.umeshes.cancel_with_report(info=f"The number of islands must be greater than one")
            return

        cursor_offset = 0
        if self.is_horizontal(general_bbox):
            _islands.sort(key=lambda a: a.bbox.xmin)
            if self.cursor_loc is None:
                margin = general_bbox.min.x
            else:
                margin = self.cursor_loc.x
                cursor_offset += general_bbox.min.y - self.cursor_loc.y

            for island in _islands:
                width = island.bbox.width
                self.update_tag |= island.set_position(Vector((margin, island.bbox.ymin - cursor_offset)), _from=island.bbox.min)
                margin += self.padding + width
        else:
            _islands.sort(key=lambda a: a.bbox.ymin)
            if self.cursor_loc is None:
                margin = general_bbox.min.y
            else:
                margin = self.cursor_loc.y
                cursor_offset += general_bbox.min.x - self.cursor_loc.x

            for island in _islands:
                height = island.bbox.height
                self.update_tag |= island.set_position(Vector((island.bbox.xmin - cursor_offset, margin)), _from=island.bbox.min)
                margin += self.padding + height

    def distribute(self, extended=True):
        self.update_tag = False
        if self.overlapped:
            func = self.distribute_preprocessing_overlap
        else:
            func = self.distribute_preprocessing
        self.distribute_ex(*func(extended))

        if not self.update_tag and any(umesh.update_tag for umesh in self.umeshes):
            self.umeshes.cancel_with_report(info='Islands is Distributed')

    def distribute_space(self, extended=True):
        if self.overlapped:
            func = self.distribute_preprocessing_overlap
        else:
            func = self.distribute_preprocessing
        _islands, general_bbox = func(extended)

        if len(_islands) <= 2:
            if len(_islands) != 0:
                self.umeshes.cancel_with_report(info=f"The number of islands must be greater than two, {len(_islands)} was found")
            return

        update_tag = False
        cursor_offset = 0
        if self.is_horizontal(general_bbox):
            _islands.sort(key=lambda a: a.bbox.xmin)

            general_bbox.xmax += self.padding * (len(_islands) - 1)
            start_space = general_bbox.xmin + _islands[0].bbox.half_width
            end_space = general_bbox.xmax - _islands[-1].bbox.half_width
            if start_space == end_space:
                self.umeshes.cancel_with_report(info=f"No distance to place UV")
                return

            if self.cursor_loc:
                diff = end_space - start_space
                start_space += self.cursor_loc.x - start_space
                end_space = start_space + diff
                cursor_offset += general_bbox.ymin - self.cursor_loc.y
            space_points = np.linspace(start_space, end_space, len(_islands))

            for island, space_point in zip(_islands, space_points):
                update_tag |= island.set_position(Vector((space_point, island.bbox.center_y - cursor_offset)), _from=island.bbox.center)
        else:
            _islands.sort(key=lambda a: a.bbox.ymin)
            general_bbox.ymax += self.padding * (len(_islands) - 1)
            start_space = general_bbox.ymin + _islands[0].bbox.half_height
            end_space = general_bbox.ymax - _islands[-1].bbox.half_height
            if start_space == end_space:
                self.umeshes.cancel_with_report(info=f"No distance to place UV")
                return
            if self.cursor_loc:
                start_space += start_space - self.cursor_loc.y
                end_space += end_space - self.cursor_loc.y

            if self.cursor_loc:
                diff = end_space - start_space
                start_space += self.cursor_loc.y - start_space
                end_space = start_space + diff
                cursor_offset += general_bbox.xmin - self.cursor_loc.x

            space_points = np.linspace(start_space, end_space, len(_islands))

            for island, space_point in zip(_islands, space_points):
                update_tag |= island.set_position(Vector((island.bbox.center_x - cursor_offset, space_point)), _from=island.bbox.center)

        if not update_tag:
            self.umeshes.cancel_with_report(info='Islands is Distributed')

    def distribute_preprocessing(self, extended):
        _islands: list[AdvIsland] = []
        general_bbox = BBox()
        for umesh in self.umeshes:
            if adv_islands := AdvIslands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, self.sync, extended=extended):
                general_bbox.union(adv_islands.calc_bbox())
                _islands.extend(adv_islands)
            umesh.update_tag = bool(adv_islands)
        return _islands, general_bbox

    def distribute_preprocessing_overlap(self, extended):
        _islands: list[AdvIsland] = []
        for umesh in self.umeshes:
            if adv_islands := AdvIslands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, self.sync, extended=extended):
                adv_islands.calc_tris()
                adv_islands.calc_flat_coords()
                _islands.extend(adv_islands)
            umesh.update_tag = bool(adv_islands)

        general_bbox = BBox()
        union_islands_groups = UnionIslands.calc_overlapped_island_groups(_islands)
        for union_island in union_islands_groups:
            general_bbox.union(union_island.bbox)
        return union_islands_groups, general_bbox

    def is_horizontal(self, bbox):
        if self.axis == 'AUTO':
            if self.break_:
                return bbox.width > bbox.height
            else:
                return bbox.width * 2 > bbox.height
        else:
            return self.axis == 'X'


class UNIV_OT_Home(Operator):
    bl_idname = 'uv.univ_home'
    bl_label = 'Home'
    bl_description = info.operator.home_info
    bl_options = {'REGISTER', 'UNDO'}

    mode: EnumProperty(name='Mode', default='DEFAULT', items=(
        ('DEFAULT', 'Default', ''),
        ('TO_CURSOR', 'To Cursor', ''),
    ))

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and (obj := context.active_object) and obj.type == 'MESH'  # noqa # pylint:disable=used-before-assignment

    def invoke(self, context, event):
        if event.value == 'PRESS':
            return self.execute(context)
        match event.ctrl, event.shift, event.alt:
            case False, False, False:
                self.mode = 'DEFAULT'
            case True, False, False:
                self.mode = 'TO_CURSOR'
            # case False, True, False:
            #     self.mode = 'OVERLAPPED'
            case _:
                self.report({'INFO'}, f"Event: {info.event_to_string(event)} not implement.\n\n"
                                      f"See all variations: {info.operator.home_event_info_ex}\n\n")
                return {'CANCELLED'}
        return self.execute(context)

    def execute(self, context):
        return UNIV_OT_Home.home(self.mode, sync=context.scene.tool_settings.use_uv_select_sync, report=self.report)

    @staticmethod
    def home(mode, sync, report):
        umeshes = utils.UMeshes(report=report)
        match mode:
            case 'DEFAULT':
                UNIV_OT_Home.home_ex(umeshes, sync, extended=True)
                if not umeshes.final():
                    UNIV_OT_Home.home_ex(umeshes, sync, extended=False)

            case 'TO_CURSOR':
                if not (cursor_loc := utils.get_tile_from_cursor()):
                    umeshes.report({'WARNING'}, "Cursor not found")
                    return {'CANCELLED'}
                UNIV_OT_Home.home_ex(umeshes, sync, extended=True, cursor=cursor_loc)
                if not umeshes.final():
                    UNIV_OT_Home.home_ex(umeshes, sync, extended=False, cursor=cursor_loc)

            case _:
                raise NotImplementedError(mode)

        return umeshes.update()

    @staticmethod
    def home_ex(umeshes, sync, extended, cursor=Vector((0, 0))):
        for umesh in umeshes:
            changed = False
            if islands := Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, sync, extended=extended):
                for island in islands:
                    center = island.calc_bbox().center
                    delta = Vector(round(-i + 0.5) for i in center) + cursor
                    changed |= island.move(delta)
            umesh.update_tag = changed


class UNIV_OT_Random(Operator):
    bl_idname = "uv.univ_random"
    bl_label = "Random"
    bl_description = "Randomize selected UV islands or faces"
    bl_options = {'REGISTER', 'UNDO'}

    overlapped: BoolProperty(name='Overlapped', default=False)
    between: BoolProperty(name='Between', default=False)
    bound_between: EnumProperty(name='Bound Between', default='OFF', items=(('OFF', 'Off', ''), ('CROP', 'Crop', ''), ('CLAMP', 'Clamp', '')))
    round_mode: EnumProperty(name='Round Mode', default='OFF', items=(('OFF', 'Off', ''), ('INT', 'Int', ''), ('STEPS', 'Steps', '')))
    steps: FloatVectorProperty(name='Steps', description="Incorrectly works with Within Image Bounds",
                               default=(0, 0), min=0, max=10, soft_min=0, soft_max=1, size=2, subtype='XYZ')
    strength: FloatVectorProperty(name='Strength', default=(1, 1), min=-10, max=10, soft_min=0, soft_max=1, size=2, subtype='XYZ')
    use_correct_aspect: BoolProperty(name='Correct Aspect', default=True)
    rotation: FloatProperty(name='Rotation Range', default=0, min=0, soft_max=math.pi * 2, subtype='ANGLE',
        update=lambda self, _: setattr(self, 'rotation_steps', self.rotation) if self.rotation < self.rotation_steps else None)
    rotation_steps: FloatProperty(name='Rotation Steps', default=0, min=0, max=math.pi, subtype='ANGLE',
        update=lambda self, _: setattr(self, 'rotation', self.rotation_steps) if self.rotation < self.rotation_steps else None)
    scale_factor: FloatProperty(name="Scale Factor", default=0, min=0, soft_max=1, subtype='FACTOR')
    min_scale: FloatProperty(name='Min Scale', default=0.5, min=0, max=10, soft_min=0.1, soft_max=2,
                             update=lambda self, _: setattr(self, 'max_scale', self.min_scale) if self.max_scale < self.min_scale else None)
    max_scale: FloatProperty(name='Max Scale', default=2, min=0, max=10, soft_min=0.1, soft_max=2,
                             update=lambda self, _: setattr(self, 'min_scale', self.max_scale) if self.max_scale < self.min_scale else None)
    bool_bounds: BoolProperty(name="Within Image Bounds", default=False, description="Keep the UV faces/islands within the 0-1 UV domain.", )
    rand_seed: IntProperty(name='Seed', default=0)

    @classmethod
    def poll(cls, context):
        return (obj := context.active_object) and obj.type == 'MESH'

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'rand_seed')

        if not self.between:
            layout.prop(self, 'round_mode', slider=True)
            if self.round_mode == 'STEPS':
                layout.prop(self, 'steps', slider=True)
            layout.prop(self, 'strength', slider=True)

        if self.bound_between != 'CROP':
            layout.prop(self, 'scale_factor', slider=True)
            if self.scale_factor != 0:
                layout.prop(self, 'min_scale', slider=True)
                layout.prop(self, 'max_scale', slider=True)

        layout.prop(self, 'rotation', slider=True)
        if self.rotation != 0:
            layout.prop(self, 'rotation_steps', slider=True)
            layout.prop(self, 'use_correct_aspect', toggle=1)  # TODO: Implement for crop and clamp

        if not self.between:
            layout.prop(self, 'bool_bounds')

        layout = self.layout.row()
        if self.between:
            layout.prop(self, 'bound_between', expand=True)
        layout = self.layout.row()
        layout.prop(self, 'overlapped', toggle=1)
        layout.prop(self, 'between', toggle=1)

    def invoke(self, context, event):
        if event.value == 'PRESS':
            return self.execute(context)
        self.overlapped = event.shift
        self.between = event.alt
        self.bound_between = 'CROP' if event.ctrl else 'OFF'
        return self.execute(context)

    def __init__(self):
        self.seed = 1000
        self.aspect = 1.0
        self.non_valid_counter = 0
        self.umeshes: utils.UMeshes | None = None
        self.is_edit_mode: bool = bpy.context.mode == 'EDIT_MESH'
        self.all_islands: list[UnionIslands | AdvIsland] | None = None
        self.sync = bpy.context.scene.tool_settings.use_uv_select_sync

    def execute(self, context):
        self.non_valid_counter = 0
        self.umeshes = utils.UMeshes(report=self.report)
        self.aspect = utils.get_aspect_ratio() if self.use_correct_aspect else 1.0

        if not self.is_edit_mode:
            self.umeshes.ensure(face=True)

        self.random_preprocessing()
        if self.is_edit_mode:
            if not self.all_islands:
                self.random_preprocessing(extended=False)

        if self.between:
            self.random_between()
        else:
            self.random()
        if self.non_valid_counter:
            self.report({'INFO'}, f"Found {self.non_valid_counter} zero-sized islands that will not be affected by some effects")
        self.umeshes.update(info="No object for randomize.")

        if not self.is_edit_mode:
            self.umeshes.free()
            utils.update_by_area_type('VIEW_3D')
        return {'FINISHED'}

    def random_preprocessing(self, extended=True):
        self.seed = sum(id(umesh.obj) for umesh in self.umeshes) // len(self.umeshes) + self.rand_seed

        self.all_islands = []
        _islands = []
        for umesh in self.umeshes:
            if self.is_edit_mode:
                islands = AdvIslands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, self.sync, extended=extended)
            else:
                islands = AdvIslands.calc_with_hidden(umesh)
            if islands:
                if self.overlapped:
                    islands.calc_tris()
                    islands.calc_flat_coords()
                    _islands.extend(islands)
                else:
                    self.all_islands.extend(islands)
            umesh.update_tag = bool(islands)

        if self.overlapped:
            self.all_islands = UnionIslands.calc_overlapped_island_groups(_islands)

    def random(self):
        bb_general = BBox()
        for e_seed, island in enumerate(self.all_islands, start=100):
            seed = e_seed + self.seed
            random.seed(seed)
            rand_rotation = random.uniform(-self.rotation, self.rotation)
            random.seed(seed + 1000)
            rand_scale = random.uniform(self.min_scale, self.max_scale)

            if self.bool_bounds or self.rotation or self.scale_factor != 0:

                bb = island.bbox
                if bb.min_length == 0:
                    self.non_valid_counter += 1
                    continue

                vec_origin = bb.center

                if self.rotation:
                    angle = rand_rotation
                    if self.rotation_steps:
                        angle = self.round_threshold(angle, self.rotation_steps)
                        # clamp angle in self.rotation
                        if angle > self.rotation:
                            angle -= self.rotation_steps
                        elif angle < -self.rotation:
                            angle += self.rotation_steps

                    if island.rotate(angle, vec_origin, self.aspect):
                        bb.rotate_expand(angle, self.aspect)

                scale = bl_math.lerp(1.0, rand_scale, self.scale_factor)

                new_scale = 100
                # Reset the scale to 0.5 to fit in the tile.
                if self.bool_bounds:
                    max_length = bb.max_length
                    max_length_lock = 1.0
                    if max_length * scale > max_length_lock:
                        new_scale = max_length_lock / max_length

                if self.scale_factor != 0 or new_scale < 1:
                    # If the scale from random is smaller, we choose it
                    scale = min(scale, new_scale)
                    scale = Vector((scale, scale))
                    island.scale(scale, pivot=vec_origin)
                    bb.scale(scale)

                if self.bool_bounds:
                    to_center_delta = Vector((0.5, 0.5)) - vec_origin
                    island.move(to_center_delta)
                    bb.move(to_center_delta)
                    bb_general.union(bb)

            if self.bool_bounds:
                move = Vector((
                    min(bb_general.xmin, abs(1 - bb_general.xmax)) * max(min(self.strength.x, 1), -1),
                    min(bb_general.ymin, abs(1 - bb_general.ymax)) * max(min(self.strength.y, 1), -1)
                ))
            else:
                move = Vector((self.strength.x, self.strength.y))

            if not (move.x or move.y):
                continue

            random.seed(seed + 2000)
            rand_move_x = 2 * (random.random() - 0.5)
            random.seed(seed + 3000)
            rand_move_y = 2 * (random.random() - 0.5)

            randmove = Vector((rand_move_x, rand_move_y)) * move

            if self.round_mode == 'INT':
                randmove = Vector([round(i) for i in randmove])
            elif self.round_mode == 'STEPS':
                # TODO bool_bounds for steps
                if self.steps.x > 1e-05:
                    randmove.x = self.round_threshold(randmove.x, self.steps.x)
                if self.steps.y > 1e-05:
                    randmove.y = self.round_threshold(randmove.y, self.steps.y)

            if not self.bool_bounds:
                island.move(randmove)

    def random_between(self):
        shaffle_island_bboxes: list[BBox] = [isl.bbox.copy() for isl in self.all_islands]
        random.seed(self.seed)
        random.shuffle(shaffle_island_bboxes)

        for e_seed, island in enumerate(self.all_islands, start=100):
            seed = e_seed + self.seed
            random.seed(seed)
            rand_rotation = random.uniform(-self.rotation, self.rotation)
            random.seed(seed + 1000)
            rand_scale = random.uniform(self.min_scale, self.max_scale)

            bb = island.bbox
            if self.rotation or self.scale_factor != 0:
                if bb.min_length == 0:
                    self.non_valid_counter += 1
                    continue

                vec_origin = bb.center

                if self.rotation:
                    angle = rand_rotation
                    if self.rotation_steps:
                        angle = self.round_threshold(angle, self.rotation_steps)
                        # clamp angle in self.rotation
                        if angle > self.rotation:
                            angle -= self.rotation_steps
                        elif angle < -self.rotation:
                            angle += self.rotation_steps

                    island.rotate(angle, vec_origin, self.aspect)
                    # if island.rotate(angle, vec_origin):
                    #     bb.rotate_expand(angle)
                if self.bound_between != 'CROP':
                    scale = bl_math.lerp(1.0, rand_scale, self.scale_factor)
                    vector_scale = Vector((scale, scale))
                    island.scale(vector_scale, vec_origin)
                    # bb.scale(vector_scale, vec_origin)

            protege = shaffle_island_bboxes[e_seed-100]
            island.set_position(protege.center, _from=island.bbox.center)

            if self.bound_between == 'OFF':
                continue

            if self.overlapped:
                bb = island.calc_bbox(force=True)
            else:
                bb = island.calc_bbox()

            if protege.min_length < 2e-07 or bb.min_length < 2e-07:
                self.non_valid_counter += 1
                continue

            if self.bound_between == 'CLAMP':
                if bb.width <= protege.width:
                    width_scale = 1
                else:
                    width_scale = protege.width / bb.width

                if bb.height <= protege.height:
                    height_scale = 1
                else:
                    height_scale = protege.height / bb.height
            else:  # 'CROP'
                width_scale = protege.width / bb.width
                height_scale = protege.height / bb.height

            crop_scale = min(width_scale, height_scale)
            island.scale(Vector((crop_scale, crop_scale)), bb.center)

    @staticmethod
    def round_threshold(a, min_clip):
        return round(float(a) / min_clip) * min_clip

class UNIV_OT_Orient(Operator):
    bl_idname = 'uv.univ_orient'
    bl_label = 'Orient'
    bl_description = "Orient selected UV islands or edges"
    bl_options = {'REGISTER', 'UNDO'}

    edge_dir: EnumProperty(name='Direction', default='HORIZONTAL', items=(
        ('BOTH', 'Both', ''),
        ('HORIZONTAL', 'Horizontal', ''),
        ('VERTICAL', 'Vertical', ''),
    ))

    mode: EnumProperty(name='Mode', default='ISLAND', items=(
        ('ISLAND', 'Island', ''),
        ('EDGE', 'Edge', ''),
    ))
    use_correct_aspect: BoolProperty(name='Correct Aspect', default=True)

    def draw(self, context):
        self.layout.row().prop(self, 'mode', expand=True)
        self.layout.row().prop(self, 'edge_dir', expand=True)
        self.layout.prop(self, 'use_correct_aspect', toggle=1)

    def invoke(self, context, event):
        if not (event.value == 'PRESS'):
            self.mode = 'EDGE' if event.alt else 'ISLAND'
        return self.execute(context)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and (obj := context.active_object) and obj.type == 'MESH'  # noqa # pylint:disable=used-before-assignment

    def __init__(self):
        self.skip_count: int = 0
        self.aspect: float = 1.0
        self.sync = bpy.context.scene.tool_settings.use_uv_select_sync
        self.umeshes: utils.UMeshes | None = None

    def execute(self, context):
        self.aspect = utils.get_aspect_ratio() if self.use_correct_aspect else 1.0
        self.umeshes = utils.UMeshes(report=self.report)
        # Island Orient
        if self.mode == 'ISLAND':
            self.orient_island(extended=True)
            if self.skip_count == len(self.umeshes):
                self.orient_island(extended=False)
                if self.skip_count == len(self.umeshes):
                    return self.umeshes.update(info="No uv for manipulate")
            return self.umeshes.update(info="All islands oriented")

        # Edge Orient
        if self.sync:
            self.orient_edge_sync()
        else:
            self.orient_edge()

        if self.skip_count == len(self.umeshes):
            return self.umeshes.update(info="No selected edges")
        return self.umeshes.update(info="All islands aligned")

    def orient_edge(self):
        self.skip_count = 0
        for umesh in self.umeshes:
            uv_layer = umesh.uv_layer
            umesh.update_tag = False

            if umesh.is_full_face_deselected or \
                    not any(l[uv_layer].select_edge for f in umesh.bm.faces for l in f.loops):
                self.skip_count += 1
                continue

            for island in Islands.calc_visible(umesh.bm, umesh.uv_layer, self.sync):
                luvs = (l for f in island for l in f.loops if l[uv_layer].select_edge)

                for l in luvs:
                    diff: Vector = (v1 := l[uv_layer].uv) - (v2 := l.link_loop_next[uv_layer].uv)
                    if not any(diff):
                        continue
                    if self.edge_dir == 'BOTH':
                        current_angle = atan2(*diff)
                        angle_to_rotate = -utils.find_min_rotate_angle(current_angle)
                    elif self.edge_dir == 'HORIZONTAL':
                        vec = diff.normalized()
                        angle_to_rotate = a if abs(a := vec.angle_signed(Vector((-1, 0)))) < abs(b := vec.angle_signed(Vector((1, 0)))) else b
                    else:
                        vec = diff.normalized()
                        angle_to_rotate = a if abs(a := vec.angle_signed(Vector((0, -1)))) < abs(b := vec.angle_signed(Vector((0, 1)))) else b

                    pivot: Vector = (v1 + v2) / 2
                    umesh.update_tag |= island.rotate(angle_to_rotate, pivot, self.aspect)
                    break

    def orient_edge_sync(self):
        self.skip_count = 0
        for umesh in self.umeshes:
            uv_layer = umesh.uv_layer
            umesh.update_tag = False

            if umesh.is_full_edge_deselected:
                self.skip_count += 1
                continue

            _islands = Islands.calc_visible(umesh.bm, umesh.uv_layer, self.sync)
            _islands.indexing()
            for idx, island in enumerate(_islands):
                luvs = (l for f in island for e in f.edges if e.select for l in e.link_loops if l.face.index == idx and l.face.tag)

                for l in luvs:
                    diff: Vector = (v1 := l[uv_layer].uv) - (v2 := l.link_loop_next[uv_layer].uv)
                    if not any(diff):
                        continue
                    if self.edge_dir == 'BOTH':
                        current_angle = atan2(*diff)
                        angle_to_rotate = -utils.find_min_rotate_angle(current_angle)
                    elif self.edge_dir == 'HORIZONTAL':
                        vec = diff.normalized()
                        angle_to_rotate = a if abs(a := vec.angle_signed(Vector((-1, 0)))) < abs(b := vec.angle_signed(Vector((1, 0)))) else b
                    else:
                        vec = diff.normalized()
                        angle_to_rotate = a if abs(a := vec.angle_signed(Vector((0, -1)))) < abs(b := vec.angle_signed(Vector((0, 1)))) else b

                    pivot: Vector = (v1 + v2) / 2
                    umesh.update_tag |= island.rotate(angle_to_rotate, pivot, self.aspect)
                    break

    def orient_island(self, extended):
        self.skip_count = 0
        for umesh in self.umeshes:
            if adv_islands := AdvIslands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, self.sync, extended=extended):
                for island in adv_islands:
                    points = island.calc_convex_points()

                    angle = -utils.calc_min_align_angle(points, self.aspect)
                    umesh.update_tag |= island.rotate(angle, island.bbox.center, self.aspect)
                    island._bbox = None

                    if self.edge_dir == 'HORIZONTAL':
                        if island.bbox.width*self.aspect < island.bbox.height:
                            end_angle = pi/2 if angle < 0 else -pi/2
                            umesh.update_tag |= island.rotate(end_angle, island.bbox.center, self.aspect)

                    elif self.edge_dir == 'VERTICAL':
                        if island.bbox.width*self.aspect > island.bbox.height:
                            end_angle = pi / 2 if angle < 0 else -pi / 2
                            umesh.update_tag |= island.rotate(end_angle, island.bbox.center, self.aspect)
            else:
                self.skip_count += 1


# The code was taken and modified from the TexTools addon: https://github.com/Oxicid/TexTools-Blender/blob/master/op_island_align_world.py
class UNIV_OT_Orient_VIEW3D(Operator):
    bl_idname = 'mesh.univ_orient_view3d'
    bl_label = 'Orient'
    bl_description = "Align selected UV islands or faces to world / gravity directions"
    bl_options = {'REGISTER', 'UNDO'}

    axis: bpy.props.EnumProperty(name="Axis", default='AUTO', items=(
                                    ('AUTO', 'Auto', 'Detect World axis to align to.'),
                                    ('U', 'X', 'Align to the X axis of the World.'),
                                    ('V', 'Y', 'Align to the Y axis of the World.'),
                                    ('W', 'Z', 'Align to the Z axis of the World.')))
    additional_angle: FloatProperty(name='Additional Angle', default=0.0, soft_min=-pi/2, soft_max=pi, subtype='ANGLE')
    use_correct_aspect: BoolProperty(name='Correct Aspect', default=True, description='Gets Aspect Correct from the active image from the shader node editor')

    def draw(self, context):
        self.layout.prop(self, 'additional_angle', slider=True)
        self.layout.prop(self, 'use_correct_aspect', toggle=1)
        self.layout.row().prop(self, 'axis', expand=True)

    @classmethod
    def poll(cls, context):
        return (obj := context.active_object) and obj.type == 'MESH'

    def __init__(self):
        self.skip_count: int = 0
        self.is_edit_mode: bool = bpy.context.mode == 'EDIT_MESH'
        self.umeshes: utils.UMeshes | None = None

    def execute(self, context):
        self.umeshes = utils.UMeshes(report=self.report)
        self.umeshes.set_sync(True)

        if not self.is_edit_mode:
            self.umeshes.ensure(face=True)
            self.world_orient(extended=False)
            if self.skip_count == len(self.umeshes):
                self.umeshes.free()
                return self.umeshes.update(info="Faces not found")
        else:
            self.world_orient(extended=True)
            if self.skip_count == len(self.umeshes):
                self.world_orient(extended=False)
                if self.skip_count == len(self.umeshes):
                    return self.umeshes.update(info="No uv for manipulate")

        self.umeshes.update(info="All islands oriented")

        if not self.is_edit_mode:
            self.umeshes.free()
            bpy.context.area.tag_redraw()

        return {'FINISHED'}

    def world_orient(self, extended):
        self.skip_count = 0
        for umesh in self.umeshes:
            aspect = utils.get_aspect_ratio(umesh) if self.use_correct_aspect else 1.0
            umesh.update_tag = False
            if self.is_edit_mode:
                islands = Islands.calc_extended_or_visible(umesh.bm, umesh.uv_layer, umesh.sync, extended=extended)
            else:
                islands = Islands.calc_with_hidden(umesh)

            if islands:
                uv = islands.uv_layer
                _, r, _ = umesh.obj.matrix_world.decompose()
                mtx = r.to_matrix()

                for island in islands:
                    if extended:
                        pre_calc_faces = (f for f in island if f.select)
                    else:
                        pre_calc_faces = island

                        # Get average viewport normal of UV island
                    calc_loops = []
                    avg_normal = Vector()
                    for face in pre_calc_faces:
                        avg_normal += face.normal * face.calc_area()
                        calc_loops.extend(face.loops)
                    avg_normal.rotate(mtx)

                    # Which Side
                    x, y, z = 0, 1, 2
                    max_size = max(avg_normal, key=lambda v: abs(v))

                    if (self.axis == 'AUTO' and avg_normal.z == max_size) or self.axis == 'W':
                        angle = self.calc_world_orient_angle(uv, mtx, calc_loops, x, y, False, avg_normal.z < 0, aspect)
                    elif (self.axis == 'AUTO' and avg_normal.y == max_size) or self.axis == 'V':
                        angle = self.calc_world_orient_angle(uv, mtx, calc_loops, x, z, avg_normal.y > 0, False, aspect)
                    else:  # (self.axis == 'AUTO' and avg_normal.x == max_size) or self.axis == 'U':
                        angle = self.calc_world_orient_angle(uv, mtx, calc_loops, y, z, avg_normal.x < 0, False, aspect)

                    if angle := (angle + self.additional_angle):
                        umesh.update_tag |= island.rotate(angle, pivot=island.calc_bbox().center, aspect=aspect)
            else:
                self.skip_count += 1

    @staticmethod
    def calc_world_orient_angle(uv, mtx, loops, x=0, y=1, flip_x=False, flip_y=False, aspect=1.0):
        vec_aspect = Vector((aspect, 1.0))

        n_edges = 0
        avg_angle = 0
        for loop in loops:
            co0 = mtx @ loop.vert.co
            co1 = mtx @ loop.link_loop_next.vert.co

            delta = co1 - co0
            max_side = max(map(abs, delta))

            # Check edges dominant in active axis
            if abs(delta[x]) == max_side or abs(delta[y]) == max_side:
                n_edges += 1
                uv0 = loop[uv].uv
                uv1 = loop.link_loop_next[uv].uv

                delta_verts = Vector((0, 0))
                if not flip_x:
                    delta_verts.x = co1[x] - co0[x]
                else:
                    delta_verts.x = co0[x] - co1[x]
                if not flip_y:
                    delta_verts.y = co1[y] - co0[y]
                else:
                    delta_verts.y = co0[y] - co1[y]

                delta_uvs = uv1 - uv0
                delta_uvs *= vec_aspect

                a0 = atan2(*delta_verts)
                a1 = atan2(*delta_uvs)

                a_delta = atan2(sin(a0 - a1), cos(a0 - a1))

                # Consolidation (atan2 gives the lower angle between -Pi and Pi,
                # this triggers errors when using the average avg_angle /= n_edges for rotation angles close to Pi)
                if n_edges > 1:
                    if abs((avg_angle / (n_edges - 1)) - a_delta) > 3.12:
                        if a_delta > 0:
                            avg_angle += (a_delta - pi * 2)
                        else:
                            avg_angle += (a_delta + pi * 2)
                    else:
                        avg_angle += a_delta
                else:
                    avg_angle += a_delta

        return avg_angle / n_edges


class UNIV_OT_Weld(Operator):
    bl_idname = "uv.univ_weld"
    bl_label = "Weld"
    bl_description = "Weld"
    bl_options = {'REGISTER', 'UNDO'}

    use_by_distance: BoolProperty(name='By Distance', default=False)
    distance: FloatProperty(name='Distance', default=0.0005, min=0, soft_max=0.05, step=0.0001)  # noqa
    weld_by_distance_type: EnumProperty(name='Weld by', default='BY_ISLANDS', items=(
        ('ALL', 'All', ''),
        ('BY_ISLANDS', 'By Islands', '')
    ))

    flip: BoolProperty(name='Flip', default=False, options={'HIDDEN'})

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and (obj := context.active_object) and obj.type == 'MESH'  # noqa # pylint:disable=used-before-assignment

    def draw(self, context):
        layout = self.layout
        if self.use_by_distance:
            layout.row(align=True).prop(self, 'weld_by_distance_type', expand=True)
        row = layout.row(align=True)
        row.prop(self, "use_by_distance", text="")
        row.active = self.use_by_distance
        row.prop(self, 'distance', slider=True)

    def invoke(self, context, event):
        if event.value == 'PRESS':
            if context.area.ui_type == 'UV':
                self.mouse_position = Vector(context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y))
            return self.execute(context)
        self.use_by_distance = event.alt

        return self.execute(context)

    def __init__(self):
        self.sync = bpy.context.scene.tool_settings.use_uv_select_sync
        self.umeshes: utils.UMeshes | None = None
        self.global_counter = 0
        self.seam_clear_counter = 0
        self.edge_weld_counter = 0
        self.mouse_position: Vector | None = None
        self.stitched_islands = 0

    def execute(self, context):
        self.umeshes = utils.UMeshes(report=self.report)
        self.global_counter = 0
        self.seam_clear_counter = 0
        self.edge_weld_counter = 0
        self.stitched_islands = 0

        if self.use_by_distance:
            if self.weld_by_distance_type == 'BY_ISLANDS':
                self.weld_by_distance_island(extended=True)
                if not self.umeshes.final():
                    self.weld_by_distance_island(extended=False)
            else:
                self.weld_by_distance_all(selected=True)
                if not self.umeshes.final():
                    self.weld_by_distance_all(selected=False)
        else:
            self.weld()

            if self.stitched_islands:
                self.report({'INFO'}, f"Stitched {self.stitched_islands} ")
            else:
                if self.edge_weld_counter and self.seam_clear_counter:
                    self.report({'INFO'}, f"Welded {self.edge_weld_counter} edges. Cleared mark seams edges = {self.seam_clear_counter} ")
                elif self.edge_weld_counter:
                    self.report({'INFO'}, f"Welded {self.edge_weld_counter} edges.")
                elif self.seam_clear_counter:
                    self.report({'INFO'}, f"Cleared seams edges = {self.seam_clear_counter} ")

        self.umeshes.update(info='Not found verts for weld')
        return {'FINISHED'}

    @utils.timer()
    def weld(self):
        from ..utils import weld_crn_edge_by_idx
        islands_of_mesh = []
        for umesh in reversed(self.umeshes):
            uv = umesh.uv_layer
            if not umesh.sync:
                if umesh.is_full_face_deselected or \
                        not any(l[uv].select_edge for f in umesh.bm.faces if f.select for l in f.loops):
                    self.umeshes.umeshes.remove(umesh)
                    continue
            else:
                if umesh.is_full_edge_deselected:
                    self.umeshes.umeshes.remove(umesh)
                    continue

            local_seam_clear_counter = 0
            local_edge_weld_counter = 0

            if islands := Islands.calc_extended_any_edge_non_manifold(umesh):
                umesh.set_corners_tag(False)
                islands.indexing(force=True)

                for idx, isl in enumerate(islands):
                    isl.set_selected_crn_edge_tag(umesh)

                    idx = isl[0].index
                    for crn in isl.iter_corners_by_tag():
                        shared = crn.link_loop_radial_prev
                        if shared == crn:
                            crn.tag = False
                            continue

                        if shared.face.index != idx:  # island boundary skip
                            crn.tag = False
                            shared.tag = False
                            continue

                        if not shared.tag:  # single select preserve system
                            continue

                        # CPU Bound
                        crn_next = crn.link_loop_next
                        shared_next = shared.link_loop_next

                        is_splitted_a = crn[uv].uv != shared_next[uv].uv
                        is_splitted_b = crn_next[uv].uv != shared[uv].uv

                        if is_splitted_a and is_splitted_b:
                            weld_crn_edge_by_idx(crn, shared_next, idx, uv)
                            weld_crn_edge_by_idx(crn_next, shared, idx, uv)
                            local_edge_weld_counter += 1
                        elif is_splitted_a:
                            weld_crn_edge_by_idx(crn, shared_next, idx, uv)
                            local_edge_weld_counter += 1
                        elif is_splitted_b:
                            weld_crn_edge_by_idx(crn_next, shared, idx, uv)
                            local_edge_weld_counter += 1

                        edge = crn.edge
                        if edge.seam:
                            edge.seam = False
                            local_seam_clear_counter += 1

                        crn.tag = False
                        shared.tag = False

            self.seam_clear_counter += local_seam_clear_counter
            self.edge_weld_counter += local_edge_weld_counter
            umesh.update_tag = bool(local_seam_clear_counter + local_edge_weld_counter)

            if islands:
                islands_of_mesh.append((umesh, islands))

        if not self.umeshes or (self.seam_clear_counter + self.edge_weld_counter):
            return

        if not self.umeshes.sync:
            for umesh, islands in islands_of_mesh:
                uv = islands.uv_layer

                local_seam_clear_counter = 0
                local_edge_weld_counter = 0

                for idx, isl in enumerate(islands):
                    for crn in isl.iter_corners_by_tag():
                        utils.copy_pos_to_target_with_select(crn, uv, idx)

                        edge = crn.edge
                        if crn.edge.seam:
                            edge.seam = False
                            local_seam_clear_counter += 1
                        local_edge_weld_counter += 1

                self.seam_clear_counter += local_seam_clear_counter
                self.edge_weld_counter += local_edge_weld_counter
                umesh.update_tag = bool(local_seam_clear_counter + local_edge_weld_counter)

            if self.seam_clear_counter + self.edge_weld_counter:
                return

        UNIV_OT_Stitch.stitch(self)  # noqa TODO: Implement inheritance

    def weld_by_distance_island(self, extended):
        for umesh in self.umeshes:
            uv = umesh.uv_layer
            local_counter = 0
            if islands := Islands.calc_any_extended_or_visible_non_manifold(umesh, extended=extended):
                # Tagging
                for f in umesh.bm.faces:
                    for crn in f.loops:
                        crn.tag = False
                for isl in islands:
                    if extended:
                        isl.tag_selected_corner_verts_by_verts(umesh)
                    else:
                        isl.set_corners_tag(True)

                    corners = (crn for f in isl for crn in f.loops if crn.tag)
                    for crn in corners:
                        crn_in_vert = [crn_v for crn_v in crn.vert.link_loops if crn_v.tag]
                        local_counter += self.weld_corners_in_vert(crn_in_vert, uv)

            if local_counter:
                for _isl in islands:
                    _isl.mark_seam()
            umesh.update_tag = bool(islands)
            self.global_counter += local_counter

        if self.umeshes.final() and self.global_counter == 0:
            self.umeshes.cancel_with_report(info='Not found verts for weld')

        if self.global_counter:
            self.report({'INFO'}, f"Found {self.global_counter} vertices for weld")

    def weld_by_distance_all(self, selected):
        # TODO: Refactor this, use iterator
        for umesh in self.umeshes:
            umesh.tag_visible_corners()
            uv = umesh.uv_layer
            local_counter = 0
            if selected:
                init_corners = utils.calc_selected_uv_corners(umesh.bm, umesh.uv_layer, umesh.sync)
            else:
                init_corners = utils.calc_visible_uv_corners(umesh.bm, umesh.sync)
            if init_corners:
                # Tagging
                is_face_mesh_mode = (self.sync and utils.get_select_mode_mesh() == 'FACE')
                if not is_face_mesh_mode:
                    for f in umesh.bm.faces:
                        for crn in f.loops:
                            crn.tag = False

                for crn in init_corners:
                    crn.tag = True

                if is_face_mesh_mode:
                    if selected:
                        for f in umesh.bm.faces:
                            for crn in f.loops:
                                if not crn.face.select:
                                    crn.tag = False

                corners = (crn for crn in init_corners if crn.tag)
                for crn in corners:
                    crn_in_vert = [crn_v for crn_v in crn.vert.link_loops if crn_v.tag]
                    local_counter += self.weld_corners_in_vert(crn_in_vert, uv)

            if local_counter:
                umesh.tag_visible_faces()
                umesh.mark_seam_tagged_faces()

            umesh.update_tag = bool(init_corners)
            self.global_counter += local_counter

        if self.umeshes.final() and self.global_counter == 0:
            self.umeshes.cancel_with_report(info='Not found verts for weld')

        if self.global_counter:
            self.report({'INFO'}, f"Found {self.global_counter} vertices for weld")

    def weld_corners_in_vert(self, crn_in_vert, uv):
        if utils.all_equal(_crn[uv].uv for _crn in crn_in_vert):
            for crn_t in crn_in_vert:
                crn_t.tag = False
            return 0
        sub_local_counter = 0
        for group in self.calc_distance_groups(crn_in_vert, uv):
            value = Vector((0, 0))
            for c in group:
                value += c[uv].uv
            size = len(group)
            avg = value / size
            for c in group:
                c[uv].uv = avg
            sub_local_counter += size
        return sub_local_counter

    def calc_distance_groups(self, crn_in_vert: list[BMLoop], uv) -> list[list[BMLoop]]:
        corners_groups = []
        union_corners = []
        for corner_first in crn_in_vert:
            if not corner_first.tag:
                continue
            corner_first.tag = False

            union_corners.append(corner_first)
            compare_index = 0
            while True:
                if compare_index > len(union_corners) - 1:
                    if utils.all_equal(_crn[uv].uv for _crn in union_corners):
                        union_corners = []
                        break
                    corners_groups.append(union_corners)
                    union_corners = []
                    break

                for isl in crn_in_vert:
                    if not isl.tag:
                        continue

                    if (union_corners[compare_index][uv].uv - isl[uv].uv).length <= self.distance:
                        isl.tag = False
                        union_corners.append(isl)
                compare_index += 1
        return corners_groups

class UNIV_OT_Stitch(Operator):
    bl_idname = "uv.univ_stitch"
    bl_label = 'Stitch'
    bl_description = 'Stitch'
    bl_options = {'REGISTER', 'UNDO'}

    between: BoolProperty(name='Between', default=False, description='Attention, it is unstable')
    flip: BoolProperty(name='Flip', default=False)

    @classmethod
    def poll(cls, context):
        return context.mode == 'EDIT_MESH' and (obj := context.active_object) and obj.type == 'MESH'  # noqa # pylint:disable=used-before-assignment

    def invoke(self, context, event):
        if event.value == 'PRESS':
            if context.area.ui_type == 'UV':
                self.mouse_position = Vector(context.region.view2d.region_to_view(event.mouse_region_x, event.mouse_region_y))
            return self.execute(context)
        self.between = event.alt
        return self.execute(context)

    def __init__(self):
        self.sync = utils.sync()
        self.umeshes: utils.UMeshes | None = None
        self.global_counter = 0
        self.mouse_position: Vector | None = None
        self.stitched_islands = 0

    def execute(self, context):
        self.umeshes = utils.UMeshes(report=self.report)
        self.global_counter = 0
        self.stitched_islands = 0
        if self.between:
            self.stitch_between()
        else:
            self.stitch()
            if self.stitched_islands:
                self.report({'INFO'}, f"Stitched {self.stitched_islands} ")

        return self.umeshes.update(info='Not found edges for stitch')

    def stitch(self):
        for umesh in self.umeshes:
            if self.sync and umesh.is_full_edge_deselected or (not self.sync and umesh.is_full_face_deselected):
                umesh.update_tag = False
                continue

            uv = umesh.uv_layer
            adv_islands = AdvIslands.calc_extended_or_visible(umesh.bm, uv, self.sync, extended=False)
            if len(adv_islands) < 2:
                umesh.update_tag = False
                continue

            adv_islands.indexing(force=True)

            for f in umesh.bm.faces:
                for crn in f.loops:
                    crn.tag = False

            if self.sync:
                target_islands = [isl for isl in adv_islands if any(crn.edge.select for f in isl for crn in f.loops)]
            else:
                target_islands = [isl for isl in adv_islands if any(crn[uv].select_edge for f in isl for crn in f.loops)]

            if self.sync and self.mouse_position:
                def sort_by_nearest_to_mouse(__island: AdvIsland) -> float:
                    nonlocal uv
                    nonlocal mouse_position

                    min_dist = math.inf
                    for _ff in __island:
                        for crn_ in _ff.loops:
                            if crn_.edge.select:
                                min_dist = min((min_dist,
                                                (mouse_position - crn_[uv].uv).length_squared,
                                                (mouse_position - crn_.link_loop_next[uv].uv).length_squared))
                    return min_dist

                mouse_position = self.mouse_position
                target_islands.sort(key=sort_by_nearest_to_mouse)

            else:
                for _isl in target_islands:
                    _isl.calc_selected_edge_length()

                target_islands.sort(key=lambda a: a.info.edge_length, reverse=True)

                for _isl in reversed(target_islands):
                    if _isl.info.edge_length < 1e-06:
                        target_islands.remove(_isl)

            if not target_islands:
                umesh.update_tag = False
                continue

            update_tag = False
            while True:
                stitched = False
                for target_isl in target_islands:
                    tar = LoopGroup(umesh)

                    while True:
                        local_stitched = False
                        for _ in tar.calc_first(target_isl):
                            source = tar.calc_shared_group()
                            res = UNIV_OT_Stitch.stitch_ex(self, tar, source, adv_islands)
                            local_stitched |= res
                        stitched |= local_stitched
                        if not local_stitched:
                            break
                update_tag |= stitched
                if not stitched:
                    break
            if update_tag:
                for adv in adv_islands:
                    adv.mark_seam()
            self.stitched_islands += len(adv_islands) - sum(bool(isl) for isl in adv_islands)
            umesh.update_tag = update_tag

    def stitch_between(self):
        for umesh in self.umeshes:
            if umesh.is_full_face_deselected:
                umesh.update_tag = False
                continue
            uv = umesh.uv_layer
            _islands = AdvIslands.calc_extended_or_visible(umesh.bm, uv, self.sync, extended=True)
            if len(_islands) < 2:
                umesh.update_tag = False
                continue

            _islands.indexing(force=True)

            for f in umesh.bm.faces:
                for crn in f.loops:
                    crn.tag = False

            target_islands = _islands.islands[:]
            if self.sync and self.mouse_position:
                def sort_by_nearest_to_mouse(__island: AdvIsland) -> float:
                    from mathutils.geometry import intersect_point_line
                    nonlocal uv
                    nonlocal mouse_position

                    min_dist = math.inf
                    for _ff in __island:
                        for __crn_sort in _ff.loops:
                            intersect = intersect_point_line(mouse_position, __crn_sort[uv].uv, __crn_sort.link_loop_next[uv].uv)
                            dist = (mouse_position - intersect[0]).length
                            if min_dist > dist:
                                min_dist = dist
                    return min_dist

                mouse_position = self.mouse_position
                target_islands.sort(key=sort_by_nearest_to_mouse)

            else:
                for _isl in target_islands:
                    _isl.calc_selected_edge_length(selected=False)

                target_islands.sort(key=lambda a: a.info.edge_length, reverse=True)

                for _isl in reversed(target_islands):
                    if _isl.info.edge_length < 1e-06:
                        target_islands.remove(_isl)

            if not target_islands:
                umesh.update_tag = False
                continue

            update_tag = False
            while True:
                stitched = False
                for target_isl in target_islands:
                    tar = LoopGroup(umesh)

                    while True:
                        local_stitched = False
                        for _ in tar.calc_first(target_isl, selected=False):
                            source = tar.calc_shared_group()
                            res = self.stitch_ex(tar, source, _islands, selected=False)
                            local_stitched |= res
                        stitched |= local_stitched
                        if not local_stitched:
                            break
                update_tag |= stitched
                if not stitched:
                    break
            if update_tag:
                for adv in target_islands:
                    adv.mark_seam()
            umesh.update_tag = update_tag

    @staticmethod
    def has_zero_length(crn_a1, crn_a2, crn_b1, crn_b2, uv):
        return (crn_a1[uv].uv - crn_a2[uv].uv).length < 1e-06 or \
            (crn_b1[uv].uv - crn_b2[uv].uv).length < 1e-06

    @staticmethod
    def calc_begin_end_points(tar, source):
        if not tar or not source:
            return False
        uv = tar.uv

        crn_a1 = tar[0]
        crn_a2 = tar[-1].link_loop_next
        crn_b1 = source[-1].link_loop_next
        crn_b2 = source[0]

        if UNIV_OT_Stitch.has_zero_length(crn_a1, crn_a2, crn_b1, crn_b2, uv):
            bbox, bbox_margin_corners = BBox.calc_bbox_with_corners(tar, tar.uv)
            xmin_crn, xmax_crn, ymin_crn, ymax_crn = bbox_margin_corners
            if bbox.max_length < 1e-06:
                return False

            if bbox.width > bbox.height:
                crn_a1 = xmin_crn
                crn_a2 = xmax_crn

                crn_b1 = utils.shared_crn(xmin_crn).link_loop_next
                crn_b2 = utils.shared_crn(xmax_crn).link_loop_next
            else:
                crn_a1 = ymin_crn
                crn_a2 = ymax_crn

                crn_b1 = utils.shared_crn(ymin_crn).link_loop_next
                crn_b2 = utils.shared_crn(ymax_crn).link_loop_next

            if UNIV_OT_Stitch.has_zero_length(crn_a1, crn_a2, crn_b1, crn_b2, uv):
                return False

        return crn_a1, crn_a2, crn_b1, crn_b2

    @staticmethod
    def copy_pos(crn, uv):
        co_a = crn[uv].uv
        shared_a = utils.shared_crn(crn).link_loop_next
        source_corners = utils.linked_crn_uv_by_face_index(shared_a, uv)
        for _crn in source_corners:
            _crn[uv].uv = co_a

        co_b = crn.link_loop_next[uv].uv
        shared_b = utils.shared_crn(crn)
        source_corners = utils.linked_crn_uv_by_face_index(shared_b, uv)
        for _crn in source_corners:
            _crn[uv].uv = co_b

    def stitch_ex(self, tar, source, adv_islands, selected=True):
        uv = tar.uv
        # Equal indices occur after merging on non-stitch edges
        if tar[0].face.index == source[0].face.index:
            for target_crn in tar:
                UNIV_OT_Stitch.copy_pos(target_crn, uv)
            return True

        if (corners := UNIV_OT_Stitch.calc_begin_end_points(tar, source)) is False:
            tar.tag = False
            return False

        target_isl = adv_islands[corners[0].face.index]
        source_isl = adv_islands[corners[2].face.index]

        # if not (target_isl.is_full_flipped != source_isl.is_full_flipped):  # TODO: Implement auto flip (reverse LoopGroup?)
        #     source_isl.scale_simple(Vector((1, -1)))
        if self.flip:
            source_isl.scale_simple(Vector((1, -1)))
        pt_a1, pt_a2, pt_b1, pt_b2 = [c[uv].uv for c in corners]

        normal_a = pt_a1 - pt_a2
        normal_b = pt_b1 - pt_b2

        # Scale
        scale = normal_a.length / normal_b.length
        source_isl.scale_simple(Vector((scale, scale)))

        # Rotate
        rotate_angle = normal_a.angle_signed(normal_b)
        source_isl.rotate_simple(rotate_angle)

        # Move
        source_isl.move(pt_a1 - pt_b1)

        adv_islands.weld_selected(target_isl, source_isl, selected=selected)
        return True
