"""
batch_compare_importers.py

Opens each .blend file, exports to .3dm, then round-trips through both
JesterKing's import_3dm and KS_JK_import_3dm. Compares each roundtrip
against the original and prints a side-by-side summary table.

Both importers share the same bpy.ops bl_idname, so this script calls
their read_3dm() functions directly rather than going through bpy.ops.

Usage:
    /Applications/Blender_5.1.1.app/Contents/MacOS/Blender --background \\
        --python utilities/batch_compare_importers.py -- \\
        --input  /path/to/SampleBlendFiles \\
        --output /tmp/compare_out \\
        [--tol 1e-6]
"""

import sys
import os
import argparse
import glob
import importlib

# Module paths for the two importers' read3dm submodules.
# Each importer now has a distinct bl_idname so both can coexist:
#   JesterKing:  import_3dm.some_data
#   KS_JK:       ks_jk_import_3dm.some_data
_JK_READ3DM    = "bl_ext.user_default.import_3dm.read3dm"
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
    parser = argparse.ArgumentParser(prog="batch_compare_importers")
    parser.add_argument("--input",  required=True,
                        help="Directory of .blend files or a single .blend file")
    parser.add_argument("--output", required=True,
                        help="Output directory for intermediate .3dm files")
    parser.add_argument("--tol", type=float, default=1e-6,
                        help="Comparison tolerance in metres (default 1e-6)")
    return parser.parse_args(argv)


def _collect_blend_files(input_path):
    if os.path.isfile(input_path) and input_path.endswith(".blend"):
        return [input_path]
    if os.path.isdir(input_path):
        files = sorted(glob.glob(os.path.join(input_path, "*.blend")))
        return [f for f in files if not f.endswith(".blend1")]
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


def _export_3dm(filepath):
    import bpy
    try:
        cat, name = _EXPORT_OP.split(".", 1)
        op = getattr(getattr(bpy.ops, cat), name)
        bpy.ops.object.select_all(action='SELECT')
        result = op(filepath=filepath, use_selection=True)
        return 'FINISHED' in result
    except Exception as e:
        print(f"[ERROR] Export: {e}")
        return False


def _base_options(filepath):
    return {
        'filepath':               filepath,
        'import_hidden_objects':  True,
        'import_hidden_layers':   True,
        'import_layers_as_empties': False,
        'import_annotations':     False,
        'import_curves':          True,
        'import_meshes':          False,
        'import_subd':            False,
        'import_extrusions':      True,
        'import_brep':            True,
        'import_pointset':        False,
        'import_views':           False,
        'import_named_views':     False,
        'import_groups':          False,
        'import_nested_groups':   False,
        'import_instances':       False,
        'import_instances_grid_layout': False,
        'import_instances_grid':  10,
        'link_materials_to':      'PREFERENCES',
        'update_materials':       True,
        'merge_by_distance':      False,
        'merge_distance':         0.0001,
        'subD_level_viewport':    2,
        'subD_level_render':      2,
        'subD_boundary_smooth':   'ALL',
    }


def _import_with(read3dm_path, filepath, extra=None):
    """Call read_3dm() directly from a module, bypassing bpy.ops."""
    import bpy
    try:
        mod = importlib.import_module(read3dm_path)
    except ImportError as e:
        print(f"  [ERROR] Cannot import {read3dm_path}: {e}")
        return False
    options = _base_options(filepath)
    if extra:
        options.update(extra)
    try:
        result = mod.read_3dm(bpy.context, filepath, options)
        return 'FINISHED' in result
    except Exception as e:
        print(f"  [ERROR] read_3dm raised: {e}")
        return False


def _object_summary():
    import bpy
    types = {}
    for obj in bpy.context.scene.objects:
        t = obj.type
        types[t] = types.get(t, 0) + 1
    return types


# ---------------------------------------------------------------------------
# Inline comparison (calls compare_3dm.compare())
# ---------------------------------------------------------------------------

def _load_compare():
    """Add utilities/ to sys.path and import the compare function."""
    utils_dir = os.path.dirname(os.path.abspath(__file__))
    if utils_dir not in sys.path:
        sys.path.insert(0, utils_dir)
    try:
        from compare_3dm import compare
        return compare
    except ImportError as e:
        print(f"[WARN] compare_3dm not importable: {e}")
        return None


def _compare_result(compare_fn, path_original, path_rt, tol):
    """Run comparison; capture stdout; return result string."""
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
        # Print details so failures are diagnosable
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
    blend_files = _collect_blend_files(args.input)
    if not blend_files:
        print("[ERROR] No .blend files found.")
        sys.exit(1)

    os.makedirs(args.output, exist_ok=True)

    if not _ensure_extension(_EXPORT_MODULE, "export_nurbs_3dm"):
        print("[ERROR] export_nurbs_3dm not available — aborting.")
        sys.exit(1)

    compare_fn = _load_compare()

    # Results table: list of (stem, jk_objects, ks_objects, jk_result, ks_result)
    results = []

    for blend_path in blend_files:
        stem = os.path.splitext(os.path.basename(blend_path))[0]
        print(f"\n{'='*60}")
        print(f"Processing: {stem}")

        orig_3dm = os.path.join(args.output, f"{stem}_original.3dm")
        jk_3dm   = os.path.join(args.output, f"{stem}_jk.3dm")
        ks_3dm   = os.path.join(args.output, f"{stem}_ks.3dm")

        # ── Step 1: open .blend and export original ──────────────────────
        print(f"  Opening {os.path.basename(blend_path)}")
        try:
            bpy.ops.wm.open_mainfile(filepath=blend_path)
        except Exception as e:
            print(f"  [ERROR] Could not open: {e}")
            results.append((stem, "-", "-", "open-failed", "open-failed"))
            continue

        n_scene = len(bpy.context.scene.objects)
        print(f"  Scene objects: {n_scene}")

        if not _export_3dm(orig_3dm):
            print(f"  [ERROR] Export failed")
            results.append((stem, "-", "-", "export-failed", "export-failed"))
            continue
        print(f"  Exported original → {os.path.basename(orig_3dm)}")

        # ── Step 2: import with JesterKing ───────────────────────────────
        _clear_scene()
        print(f"\n  [JK] Importing with import_3dm ...")
        jk_ok = _import_with(_JK_READ3DM, orig_3dm)
        jk_objs = _object_summary() if jk_ok else {}
        jk_label = ", ".join(f"{v}×{k}" for k, v in jk_objs.items()) if jk_objs else "import-failed"
        print(f"  [JK] Objects: {jk_label}")

        if jk_ok and jk_objs:
            _export_3dm(jk_3dm)
            print(f"  [JK] Exported → {os.path.basename(jk_3dm)}")

        # ── Step 3: import with KS_JK ────────────────────────────────────
        _clear_scene()
        print(f"\n  [KS] Importing with ks_jk_import_3dm ...")
        ks_ok = _import_with(_KS_READ3DM, orig_3dm,
                              extra={'import_nurbs_surfaces': True,
                                     'merge_brep_faces': True})
        ks_objs = _object_summary() if ks_ok else {}
        ks_label = ", ".join(f"{v}×{k}" for k, v in ks_objs.items()) if ks_objs else "import-failed"
        print(f"  [KS] Objects: {ks_label}")

        if ks_ok and ks_objs:
            _export_3dm(ks_3dm)
            print(f"  [KS] Exported → {os.path.basename(ks_3dm)}")

        # ── Step 4: compare ───────────────────────────────────────────────
        jk_result = _compare_result(compare_fn, orig_3dm, jk_3dm, args.tol)
        ks_result = _compare_result(compare_fn, orig_3dm, ks_3dm, args.tol)
        print(f"\n  [JK] vs original: {jk_result}")
        print(f"  [KS] vs original: {ks_result}")

        results.append((stem, jk_label, ks_label, jk_result, ks_result))

    # ── Summary table ─────────────────────────────────────────────────────
    col0 = max(len(r[0]) for r in results) if results else 30
    col0 = max(col0, 20)
    print(f"\n\n{'═'*90}")
    print(f"COMPARISON SUMMARY  (tol={args.tol})")
    print(f"{'═'*90}")
    hdr = f"{'File':<{col0}}  {'JK objects':<22}  {'KS objects':<22}  {'JK result':<14}  {'KS result'}"
    print(hdr)
    print(f"{'─'*90}")
    for stem, jk_objs, ks_objs, jk_res, ks_res in results:
        print(f"{stem:<{col0}}  {jk_objs:<22}  {ks_objs:<22}  {jk_res:<14}  {ks_res}")
    print(f"{'═'*90}")


main()
