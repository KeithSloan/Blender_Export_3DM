# Claude Code Instructions — Blender_Export_3DM

## Blender installation convention

After installing Blender, the user renames `/Applications/Blender.app` to
`/Applications/Blender_x.y.z.app` (e.g. `/Applications/Blender_5.1.1.app`).
Always use the versioned path in shell commands — never `/Applications/Blender.app`.

## Extension zip

The file `export_nurbs_3dm.zip` is the installable Blender extension archive
(Install from Disk in Blender's Extension preferences).  It must be kept in sync
with the source files at all times.

**Whenever any of the following files change, regenerate the zip immediately:**

```
__init__.py
blender_manifest.toml
export_nurbs_3dm.py
```

Command to regenerate (run from repo root):

```bash
rm -f export_nurbs_3dm.zip
zip export_nurbs_3dm.zip __init__.py blender_manifest.toml export_nurbs_3dm.py
```

macOS automatically expands zip files downloaded from the web, so users install
from the zip on disk — keeping it current is essential.

## Version bumping

Before regenerating the zip for any functional change, bump the version in
`blender_manifest.toml`:

```toml
version = "0.1.0"   # → increment patch, minor, or major as appropriate
```

Use semantic versioning: patch for bug fixes, minor for new features, major for
breaking changes.  Commit the version bump together with the code change.

## SampleBlendFiles layout

```
SampleBlendFiles/
  V5.1.1_Shapes.blend       ← combined file with all V5.1.1 shapes
  V4.4/                     ← Blender 4.4 test files (blend, 3dm, etc.)
    V4.4_Curves.blend
    V4.4_Surfaces.blend
    SimpleSurface.blend
    SimpleSurface.3dm
    V4.4_*.3dm  …
  V5.1.1/                   ← individual Blender 5.1.1 test files
    V5.1.1_BezierCurve.blend
    V5.1.1_NurbsCurve.blend
    V5.1.1_SurfCircle_.blend
    V5.1.1_SurfCylinder.blend
    V5.1.1_SurfPatch.blend
    V5.1.1_SurfSphere.blend
    V5.1.1_SurfTor_us.blend
    V5.1.1_SurfTorus.blend
```

Do not commit `.blend1` files (Blender backup files).

## Sample_3DM_Files

Copied from `/Users/ksloan/Workbenches/ImportExport_3DM/testCases/` (the
[ImportExport_3DM](https://github.com/KeithSloan/ImportExport_3DM) FreeCAD
workbench).  Only `.3dm` files are copied — screenshots are excluded.
If new test cases are added upstream, copy the `.3dm` files again from that
location.

## Bezier curve export

Blender Bezier splines are exported as degree-3 `NurbsCurve` objects using a
**piecewise-Bezier knot vector**: each segment junction has knot multiplicity 3
(= degree), giving knots `[0,0,0, 1,1,1, 2,2,2, ..., n,n,n]`.

Control point layout per segment (anchor[i] → anchor[i+1]):
```
anchor[i],  handle_right[i],  handle_left[i+1]
```
followed by the final `anchor[n]` for non-cyclic curves.

Both JK and KS_JK importers read this back as a NURBS curve and round-trip
EQUIVALENT.  The importer produces a NURBS spline (not a Bezier spline), which
is geometrically identical but uses Blender's uniform-clamped parameterisation
on re-export — knot differences are informational only in compare_3dm.

## KS_JK_import_3dm

KS_JK_import_3dm is a fork of [JesterKing's import_3dm](https://github.com/jesterKing/import_3dm).
Key additions over the upstream fork:

- NURBS Surface import (`ObjectType.Surface` dispatch)
- Custom properties on imported Curve data blocks for roundtrip correctness
  (see section below)
- Distinct `bl_idname = "ks_jk_import_3dm.some_data"` so both importers can
  coexist in the same Blender session

## Blender NURBS surface — Python API limitation

Blender 5.x stores NURBS surfaces natively as a **single spline** with all
`count_u × count_v` control points, with the U dimension in the internal field
`pntsu` (exposed as the read-only `point_count_u` property).  This allows
`order_v` and cyclic flags to be stored correctly.

The Python API **cannot** create this format: `point_count_u` / `pntsu` is
`PROP_NOT_EDITABLE`.  The only path from Python is **multi-spline** format (one
spline per V-row), in which Blender clamps `order_v` to 2 on each individual
spline (since each row has `pntsv = 1`).

**Workaround used by KS_JK_import_3dm:** the true rhino values are stored as
custom properties on the Curve data block:

| Property | Meaning |
|---|---|
| `rhino_order_u` | NURBS order in U |
| `rhino_order_v` | NURBS order in V (cannot be stored in Blender spline) |
| `rhino_cyclic_u` | 1 if surface is closed in U, else 0 |
| `rhino_cyclic_v` | 1 if surface is closed in V, else 0 |

The exporter (`export_nurbs_3dm.py`) reads these custom properties when it
detects multi-spline format, ensuring a correct roundtrip even though Blender's
spline properties cannot hold the values natively.
