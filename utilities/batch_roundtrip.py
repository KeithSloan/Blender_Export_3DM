"""
batch_roundtrip.py — Import .3dm files via jesterKing/import_3dm, then
re-export each one to an output directory using the NURBS 3DM exporter.

Usage (run from a terminal):

    /Applications/Blender_4.4.app/Contents/MacOS/Blender --background \\
        --python /path/to/utilities/batch_roundtrip.py -- \\
        --input  /path/to/testCases \\
        --output /path/to/output \\
        [--pattern "*.3dm"]

    # Or process a single file:
    ... --input /path/to/testCases/Surface.3dm --output /path/to/output

Dependencies (Blender 4.2+ extensions, installed via Extensions marketplace):
    - jesterKing/import_3dm       → bl_ext.user_default.import_3dm
    - export_nurbs_3dm (this repo) → bl_ext.user_default.export_nurbs_3dm
"""

import sys
import os
import argparse
import glob

# Blender 4.2+ extensions use the bl_ext.user_default. prefix
_IMPORT_MODULE = "bl_ext.user_default.ks_jk_import_3dm"
_EXPORT_MODULE = "bl_ext.user_default.export_nurbs_3dm"

# Operator bl_idnames (independent of extension prefix)
_IMPORT_OP = "import_3dm.some_data"      # jesterKing Import3dm
_EXPORT_OP = "export_scene.nurbs_3dm"    # NURBS 3DM exporter


def _parse_args():
    """Extract arguments that follow the '--' separator Blender uses."""
    try:
        idx = sys.argv.index("--")
        argv = sys.argv[idx + 1:]
    except ValueError:
        argv = []

    parser = argparse.ArgumentParser(
        prog="batch_roundtrip",
        description="Round-trip .3dm files through Blender (import → export).",
    )
    parser.add_argument(
        "--input", required=True,
        help="Path to a .3dm file or a directory containing .3dm files.",
    )
    parser.add_argument(
        "--output", required=True,
        help="Output directory for exported .3dm files.",
    )
    parser.add_argument(
        "--pattern", default="*.3dm",
        help="Glob pattern when --input is a directory (default: *.3dm).",
    )
    parser.add_argument(
        "--all-objects", action="store_true",
        help="Export all objects (default: selection only).",
    )
    parser.add_argument(
        "--nurbs", action="store_true",
        help="Import Brep surfaces as NURBS Surface objects and curves as NURBS Curve objects.",
    )
    return parser.parse_args(argv)


def _collect_files(input_path, pattern):
    if os.path.isfile(input_path):
        return [input_path]
    if os.path.isdir(input_path):
        found = sorted(glob.glob(os.path.join(input_path, pattern)))
        return [f for f in found if not f.endswith(".3dmbak")]
    print(f"[ERROR] --input path not found: {input_path}")
    return []


def _ensure_extension(module_name, label):
    """Enable a Blender 4.2+ extension by module name if not already active."""
    import bpy
    if module_name in bpy.context.preferences.addons:
        return True
    print(f"[WARN]  '{label}' not enabled — attempting to enable {module_name}")
    try:
        bpy.ops.preferences.addon_enable(module=module_name)
        if module_name in bpy.context.preferences.addons:
            print(f"[INFO]  Enabled {module_name}")
            return True
    except Exception as e:
        print(f"[ERROR] Could not enable {module_name}: {e}")
    return False


def _clear_scene():
    """Delete all objects and meshes — safe alternative to read_factory_settings."""
    import bpy
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in bpy.data.meshes:
        bpy.data.meshes.remove(block)
    for block in bpy.data.curves:
        bpy.data.curves.remove(block)


def _get_op(op_path):
    """Resolve 'category.name' to the bpy.ops callable, or None."""
    import bpy
    try:
        category, name = op_path.split(".", 1)
        return getattr(getattr(bpy.ops, category), name)
    except (AttributeError, ValueError):
        return None


def _import_3dm(filepath, nurbs=False):
    import bpy
    op = _get_op(_IMPORT_OP)
    if op is None:
        print(f"[ERROR] Operator {_IMPORT_OP} not found — is {_IMPORT_MODULE} enabled?")
        return False
    try:
        result = op(filepath=filepath, import_nurbs_surfaces=nurbs, import_curves=nurbs)
        return 'FINISHED' in result
    except Exception as e:
        print(f"[ERROR] Import raised: {e}")
        return False


def _export_3dm(filepath, use_selection=True):
    import bpy
    op = _get_op(_EXPORT_OP)
    if op is None:
        print(f"[ERROR] Operator {_EXPORT_OP} not found — is {_EXPORT_MODULE} enabled?")
        return False
    try:
        result = op(filepath=filepath, use_selection=use_selection)
        return 'FINISHED' in result
    except Exception as e:
        print(f"[ERROR] Export raised: {e}")
        return False


def main():
    import bpy

    args = _parse_args()

    input_files = _collect_files(args.input, args.pattern)
    if not input_files:
        print("[ERROR] No .3dm files found.")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    import_ok = _ensure_extension(_IMPORT_MODULE, "jesterKing import_3dm")
    export_ok = _ensure_extension(_EXPORT_MODULE, "NURBS 3DM exporter")
    if not import_ok or not export_ok:
        print("[ERROR] Required extensions could not be enabled — aborting.")
        sys.exit(1)

    ok = 0
    fail = 0

    for src in input_files:
        stem = os.path.splitext(os.path.basename(src))[0]
        dest = os.path.join(args.output, stem + ".3dm")

        print(f"\n[INFO]  Processing: {os.path.basename(src)}")

        _clear_scene()

        if not _import_3dm(src, nurbs=args.nurbs):
            print(f"[FAIL]  Import failed: {src}")
            fail += 1
            continue

        n_obj = len(bpy.context.scene.objects)
        print(f"[INFO]  Imported {n_obj} object(s)")

        if not args.all_objects:
            bpy.ops.object.select_all(action='SELECT')

        if not _export_3dm(dest, use_selection=not args.all_objects):
            print(f"[FAIL]  Export failed: {dest}")
            fail += 1
            continue

        print(f"[OK]    Exported → {dest}")
        ok += 1

    print(f"\n{'='*50}")
    print(f"Done: {ok} succeeded, {fail} failed  (out of {len(input_files)} files)")
    print(f"Output directory: {args.output}")


main()
