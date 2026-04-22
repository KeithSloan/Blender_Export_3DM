"""
batch_3dm_compare.py

For each .3dm file in an input directory:
  1. Import with KS_JK_import_3dm
  2. Re-export with export_nurbs_3dm
  3. Compare original vs roundtrip using compare_3dm.compare()

Prints a summary table of pass/fail results.

Usage:
    /Applications/Blender_5.1.1.app/Contents/MacOS/Blender --background \\
        --python utilities/batch_3dm_compare.py -- \\
        --input  Sample_3DM_Files \\
        --output /tmp/3dm_compare \\
        [--tol 1e-6]
"""

import sys
import os
import argparse
import glob
import importlib

_KS_READ3DM    = "bl_ext.user_default.ks_jk_import_3dm.read3dm"
_EXPORT_MODULE = "bl_ext.user_default.export_nurbs_3dm"
_EXPORT_OP     = "export_scene.nurbs_3dm"


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args():
    try:
        idx = sys.argv.index("--")
        argv = sys.argv[idx + 1:]
    except ValueError:
        argv = []
    parser = argparse.ArgumentParser(prog="batch_3dm_compare")
    parser.add_argument("--input",  required=True,
                        help="Directory of .3dm files or a single .3dm file")
    parser.add_argument("--output", required=True,
                        help="Output directory for roundtrip .3dm files")
    parser.add_argument("--tol", type=float, default=1e-6,
                        help="Comparison tolerance in metres (default 1e-6)")
    return parser.parse_args(argv)


def _collect_files(input_path):
    if os.path.isfile(input_path) and input_path.endswith(".3dm"):
        return [input_path]
    if os.path.isdir(input_path):
        files = sorted(glob.glob(os.path.join(input_path, "*.3dm")))
        return [f for f in files if not f.endswith(".3dmbak")]
    print(f"[ERROR] --input not found: {input_path}")
    return []


# ---------------------------------------------------------------------------
# Blender helpers
# ---------------------------------------------------------------------------

def _clear_scene():
    import bpy
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete()
    for block in list(bpy.data.meshes):
        bpy.data.meshes.remove(block)
    for block in list(bpy.data.curves):
        bpy.data.curves.remove(block)


def _ensure_extension(module_name, label):
    import bpy
    if module_name in bpy.context.preferences.addons:
        return True
    try:
        bpy.ops.preferences.addon_enable(module=module_name)
        if module_name in bpy.context.preferences.addons:
            return True
    except Exception as e:
        print(f"[WARN] Could not enable {label}: {e}")
    return False


def _import_with_ks(filepath):
    import bpy
    try:
        mod = importlib.import_module(_KS_READ3DM)
    except ImportError as e:
        print(f"  [ERROR] Cannot import {_KS_READ3DM}: {e}")
        return False
    options = {
        'filepath':                 filepath,
        'import_hidden_objects':    True,
        'import_hidden_layers':     True,
        'import_layers_as_empties': False,
        'import_annotations':       False,
        'import_curves':            True,
        'import_meshes':            False,
        'import_subd':              False,
        'import_extrusions':        True,
        'import_brep':              True,
        'import_nurbs_surfaces':    True,
        'merge_brep_faces':         True,
        'import_pointset':          False,
        'import_views':             False,
        'import_named_views':       False,
        'import_groups':            False,
        'import_nested_groups':     False,
        'import_instances':         False,
        'import_instances_grid_layout': False,
        'import_instances_grid':    10,
        'link_materials_to':        'PREFERENCES',
        'update_materials':         True,
        'merge_by_distance':        False,
        'merge_distance':           0.0001,
        'subD_level_viewport':      2,
        'subD_level_render':        2,
        'subD_boundary_smooth':     'ALL',
    }
    try:
        result = mod.read_3dm(bpy.context, filepath, options)
        return 'FINISHED' in result
    except Exception as e:
        print(f"  [ERROR] read_3dm raised: {e}")
        return False


def _export_3dm(filepath):
    import bpy
    try:
        cat, name = _EXPORT_OP.split(".", 1)
        op = getattr(getattr(bpy.ops, cat), name)
        bpy.ops.object.select_all(action='SELECT')
        result = op(filepath=filepath, use_selection=True)
        return 'FINISHED' in result
    except Exception as e:
        print(f"  [ERROR] Export raised: {e}")
        return False


def _object_summary():
    import bpy
    types = {}
    for obj in bpy.context.scene.objects:
        t = obj.type
        types[t] = types.get(t, 0) + 1
    return types


# ---------------------------------------------------------------------------
# Comparison
# ---------------------------------------------------------------------------

def _load_compare():
    utils_dir = os.path.dirname(os.path.abspath(__file__))
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    try:
        from compare_3dm import compare
        return compare
    except ImportError as e:
        print(f"[WARN] compare_3dm not importable: {e}")
        return None


def _compare(compare_fn, path_original, path_rt, tol):
    if compare_fn is None:
        return "no-compare"
    if not os.path.exists(path_rt):
        return "export-failed"
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            ok = compare_fn(path_original, path_rt, tol)
    except Exception as e:
        return f"error: {e}"
    output = buf.getvalue()
    if "EQUIVALENT" in output:
        return "EQUIVALENT"
    if "GEOMETRY OK" in output:
        return "GEOMETRY OK"
    if "GEOMETRIC DIFFERENCES" in output:
        for line in output.splitlines():
            if any(k in line for k in ("GEOMETRIC", "CP[", "differs", "count", "Order")):
                print(f"    {line.strip()}")
        return "FAIL"
    return "FAIL" if not ok else "OK"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    import bpy

    args = _parse_args()
    input_files = _collect_files(args.input)
    if not input_files:
        print("[ERROR] No .3dm files found.")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    if not _ensure_extension(_EXPORT_MODULE, "export_nurbs_3dm"):
        print("[ERROR] export_nurbs_3dm not available — aborting.")
        sys.exit(1)

    compare_fn = _load_compare()

    results = []

    for src in input_files:
        stem = os.path.splitext(os.path.basename(src))[0]
        rt_path = os.path.join(args.output, f"{stem}_rt.3dm")

        print(f"\n{'='*60}")
        print(f"Processing: {stem}")

        _clear_scene()

        print(f"  Importing with ks_jk_import_3dm ...")
        ok = _import_with_ks(src)
        if not ok:
            print(f"  Import failed")
            results.append((stem, "import-failed", "—", "import-failed"))
            continue

        objs = _object_summary()
        obj_label = ", ".join(f"{v}×{k}" for k, v in objs.items()) if objs else "none"
        print(f"  Objects: {obj_label}")

        if not objs:
            results.append((stem, obj_label, "—", "no-objects"))
            continue

        print(f"  Exporting roundtrip → {os.path.basename(rt_path)}")
        if not _export_3dm(rt_path):
            results.append((stem, obj_label, "export-failed", "export-failed"))
            continue

        result = _compare(compare_fn, src, rt_path, args.tol)
        print(f"  Result: {result}")
        results.append((stem, obj_label, os.path.basename(rt_path), result))

    # ── Summary table ─────────────────────────────────────────────────────
    col0 = max((len(r[0]) for r in results), default=20)
    col0 = max(col0, 20)
    col1 = max((len(r[1]) for r in results), default=22)
    col1 = max(col1, 22)
    print(f"\n\n{'═'*80}")
    print(f"ROUNDTRIP SUMMARY  (tol={args.tol})")
    print(f"{'═'*80}")
    print(f"{'File':<{col0}}  {'Objects':<{col1}}  Result")
    print(f"{'─'*80}")
    for stem, objs, _, result in results:
        print(f"{stem:<{col0}}  {objs:<{col1}}  {result}")
    print(f"{'═'*80}")

    passed = sum(1 for r in results if r[3] in ("EQUIVALENT", "GEOMETRY OK"))
    print(f"\n{passed}/{len(results)} passed")


main()
