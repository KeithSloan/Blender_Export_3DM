import bpy
import importlib
from bpy_extras.io_utils import ExportHelper
from bpy.props import StringProperty, BoolProperty
from bpy.types import Operator

from . import export_nurbs_3dm

if 'bpy' in locals():
    importlib.reload(export_nurbs_3dm)


class EXPORT_OT_nurbs_3dm(Operator, ExportHelper):
    bl_idname = 'export_scene.nurbs_3dm'
    bl_label = 'Export NURBS 3DM'
    bl_description = 'Export NURBS surfaces to Rhino 3DM format'

    filename_ext = '.3dm'
    filter_glob: StringProperty(default='*.3dm', options={'HIDDEN'})

    use_selection: BoolProperty(
        name='Selection Only',
        description='Export selected objects only',
        default=True,
    )
    mesh_fallback: BoolProperty(
        name='Export Meshes',
        description='Export mesh objects as rhino3dm Mesh when no NURBS available',
        default=False,
    )

    def execute(self, context):
        return export_nurbs_3dm.save(
            context,
            self.filepath,
            self.use_selection,
            self.mesh_fallback,
        )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'use_selection')
        layout.prop(self, 'mesh_fallback')


def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_nurbs_3dm.bl_idname, text='NURBS Rhino 3DM (.3dm)')


def register():
    bpy.utils.register_class(EXPORT_OT_nurbs_3dm)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(EXPORT_OT_nurbs_3dm)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
