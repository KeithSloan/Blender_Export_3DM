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
    export_flatpatch: BoolProperty(
        name='Export FlatPatch boundaries',
        description='Export SP FlatPatch objects as closed boundary polylines. '
                    'Disable to omit trimming/boundary curves from the 3DM file.',
        default=True,
    )

    def execute(self, context):
        filepath = self.filepath
        if not self.export_flatpatch and filepath.endswith('.3dm'):
            filepath = filepath[:-4] + '_nofp.3dm'
        return export_nurbs_3dm.save(
            context,
            filepath,
            self.use_selection,
            self.mesh_fallback,
            self.export_flatpatch,
        )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, 'use_selection')
        layout.prop(self, 'mesh_fallback')
        layout.prop(self, 'export_flatpatch')


def menu_func_export(self, context):
    self.layout.operator(EXPORT_OT_nurbs_3dm.bl_idname, text='NURBS Rhino 3DM (.3dm)')


def register():
    bpy.utils.register_class(EXPORT_OT_nurbs_3dm)
    bpy.types.TOPBAR_MT_file_export.append(menu_func_export)


def unregister():
    bpy.utils.unregister_class(EXPORT_OT_nurbs_3dm)
    bpy.types.TOPBAR_MT_file_export.remove(menu_func_export)
