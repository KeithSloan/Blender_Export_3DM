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

## Surface Psycho (SP) support

Surface Psycho is a Blender geometry-nodes addon (repo: `Bezier-quest`) that
stores NURBS/Bezier surface data as mesh attributes on MESH objects rather than
using Blender's native SURFACE type.  Its own STEP/IGES exporter reads those
attributes via Open CASCADE (OCP); the 3DM exporter replicates the same
attribute-reading logic using only numpy and rhino3dm.

### Detection

SP object type is identified by the name of the **last NODES modifier** whose
node group matches a known mesher name.  Node groups may be numbered
(`SP - NURBS Patch Meshing.001`) — the exporter strips the last 4 characters
before comparing, mirroring SP's own `sp_type_of_object` logic.

Mesher → type mapping:

| SP type | Modifier node group | Exported as |
|---|---|---|
| `BSPLINE_SURFACE` | `SP - NURBS Patch Meshing` | `NurbsSurface` |
| `BEZIER_SURFACE` | `SP - Bezier Patch Meshing` | `NurbsSurface` |
| `PLANE` | `SP - FlatPatch Meshing` | `NurbsCurve` boundary polyline |
| `CURVE` | `SP - Curve Meshing` | `NurbsCurve` polyline(s) |
| `COMPOUND` | `SP - Compound Meshing` | `NurbsCurve` polyline(s), one per chain |
| `BEZIER_CURVE_ANY_ORDER` | `SP -  Bezier Curve Any Order` | `NurbsCurve` single Bezier segment |
| `CYLINDER` | `SP - Cylindrical Meshing` | skipped |
| `CONE` | `SP - Conical Meshing` | skipped |
| `SPHERE` | `SP - Spherical Meshing` | skipped |
| `TORUS` | `SP - Toroidal Meshing` | skipped |
| `SURFACE_OF_REVOLUTION` | `SP - Surface of Revolution Meshing` | skipped |
| `SURFACE_OF_EXTRUSION` | `SP - Surface of Extrusion Meshing` | skipped |

### NURBS patch attributes (`BSPLINE_SURFACE`)

Read from the evaluated mesh (after geometry-nodes execution):

| Attribute | Type | Description |
|---|---|---|
| `CP_count` | INT[2] | `[u_count, v_count]` |
| `CP_NURBS_surf` | FLOAT_VECTOR[u×v] | Control points, V-major order |
| `Degrees` | INT[2] | `[degree_u, degree_v]` |
| `IsPeriodic` | BOOL[2] | `[periodic_u, periodic_v]` (optional) |
| `Weights` | FLOAT[u×v] | Rational weights (optional; defaults to 1) |
| `Multiplicity U` | INT[] | Knot multiplicities in U (trailing zeros) |
| `Knot U` | FLOAT[] | Distinct knot values in U |
| `Multiplicity V` | INT[] | Knot multiplicities in V (trailing zeros) |
| `Knot V` | FLOAT[] | Distinct knot values in V |

Control points are stored V-major (vi outer, ui inner) and are transposed
to `pts[ui, vi]` before being written to rhino3dm's `srf.Points[ui, vi]`.

Periodic surfaces: SP stores N distinct CVs; the exporter appends the first
row/column to close the loop (matching SP's `NURBS_face_to_topods`).

### Knot conversion

SP stores knots as distinct values + multiplicities (standard B-spline form).
rhino3dm uses a full expanded vector **minus the outermost entries**:

```
full = expand(knots, mults)          # e.g. [0,0,0,0, 0.5, 1,1,1,1]
rhino_knots = full[1:-1]             # e.g. [0,0,0, 0.5, 1,1,1]
```

Expected length: `count + order - 2`.  A mismatch triggers a skip with a
warning — this usually indicates a degenerate or unsupported SP configuration.

### Bezier patch attributes (`BEZIER_SURFACE`)

| Attribute | Type | Description |
|---|---|---|
| `CP_count` | INT[2] | `[u_count, v_count]` |
| `CP_any_order_surf` | FLOAT_VECTOR[u×v] | Control points, V-major order |

Represented in rhino3dm as a clamped NURBS with `order = count` (degree =
count − 1) and knot vector `[0]*degree + [1]*degree`.

### FlatPatch attributes (`PLANE`)

FlatPatch stores its boundary as degree-1 segments in `CP_planar` (world
space), but only the explicit segments — the implicit connecting segments
are not stored.  The exporter uses the **evaluated mesh polygon** instead:

- `polygon[0].vertices` — ordered boundary vertex indices
- `me.vertices[i].co` — local-space positions (need `matrix_world` applied)

Each FlatPatch evaluated mesh has typically 2 polygons (front and back faces
from the GN mesher); only `polygon[0]` is exported to avoid duplication.
The result is a closed degree-1 `NurbsCurve` polyline.

### Curve attributes (`CURVE`)

SP Curve objects do **not** have `CP_curve`, `Degree`, `Knot` etc. in their
evaluated mesh — the GN mesher outputs a pure edge mesh (vertices + edges,
no polygons).  The exporter traces connected edge chains and exports each as
a degree-1 `NurbsCurve` polyline.  Vertices are in local space; `matrix_world`
is applied.

This means the exported curve is a polyline through the evaluated mesh
vertices, not the true NURBS representation.  SP's own STEP/IGES exporter
reads source attributes directly via OCP and does not have this limitation.

### Compound attributes (`COMPOUND`)

Same structure as `CURVE` — a pure edge mesh.  May contain multiple
disconnected chains.  Additionally has an `Endpoints` boolean attribute
marking junction vertices, but this is not currently used (each connected
component is exported as a separate chain regardless).

### Bezier Curve Any Order attributes (`BEZIER_CURVE_ANY_ORDER`)

| Attribute | Type | Description |
|---|---|---|
| `CP_count` | INT[n_verts] | Control point count stored at index 0; remaining values are 0 |
| `CP_any_order_curve` | FLOAT_VECTOR[n_verts] | Control points in world space; first `CP_count[0]` entries are valid |

Exported as a single clamped Bezier `NurbsCurve` of degree = `cp_count − 1`.
Knot vector (rhino form): `[0.0] * degree + [1.0] * degree`.

Control points are in **world space** (GN outputs them pre-transformed);
`matrix_world` is **not** applied — same convention as `BEZIER_SURFACE`.

Test file: `Surface_Psycho_Files/SP - any order curve iterative vs unlooped.blend`

### World transform

SP geometry-node trees output control points in **world space** for
BSPLINE_SURFACE and BEZIER_SURFACE (they internally apply `matrix_world`).
Therefore `matrix_world` is **not** applied for those types — matching SP's
own STEP/IGES exporter.

For **FlatPatch, Curve and Compound**, the evaluated mesh vertices are in
**local (object) space**, so `matrix_world` IS applied during export.

`BEZIER_CURVE_ANY_ORDER` uses the `CP_any_order_curve` GN attribute which is
in world space, so `matrix_world` is **not** applied (same as surface types).

### SP file locations

```
/Users/ksloan/github/Blender_Addons/SurfacePsycho/   ← SP add-on source
/Users/ksloan/github/Bezier-quest/                    ← SP demo/test blend files
```

Reference files for understanding SP internals:
- `SurfacePsycho/common/utils.py` — `sp_type_of_object`, `read_attribute_by_name`, enums
- `SurfacePsycho/exporter/export_process_cad.py` — `NURBS_face_to_topods`, `bezier_face_to_topods`

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

## Known limitation — Blender NURBS surface Python API

### Discovery

This limitation was discovered during rhino3dm round-trip testing
(`utilities/batch_compare_importers.py`).  Surfaces with `order_v > 2`
(sphere, torus, patch) failed with `GEOMETRIC DIFFERENCES: OrderV: 3 vs 2`
on re-export after a KS_JK import.  Investigation showed the problem was not
in the rhino3dm library (which reads and writes `.3dm` files correctly) but
in Blender's Python API for NURBS surfaces.

### The problem

Blender 5.x stores NURBS surfaces internally using **two fields** in the `Nurb`
C struct:

| C field | Python property | Meaning |
|---|---|---|
| `pntsu` | `point_count_u` | Number of control points in U |
| `pntsv` | *(not exposed)* | Number of control points in V |

Native Blender surfaces use a **single spline** containing all `pntsu × pntsv`
control points.  With both dimensions known, Blender can correctly store and
display `order_v`, `use_cyclic_u`, and `use_cyclic_v`.

The Python API exposes `point_count_u` as **read-only** (`PROP_NOT_EDITABLE`
in Blender's RNA).  `pntsv` has no Python exposure at all.

Consequence: the only surface a Python script can create via `splines.new('NURBS')`
+ `points.add(n)` is a **single-row surface** (`pntsv = 1`).  Blender then
clamps `order_v` to `max(2, pntsv) = 2` regardless of what the script sets,
and cyclic flags in V behave unreliably.  Creating multiple splines (one per
V-row) works around point count, but each individual spline still has `pntsv = 1`
so `order_v` is still clamped to 2 on every row.

Confirmed by diagnostic (`/tmp/test_order_v.py`):
```
Row 0: set order_v=3, read back=2   ← clamped immediately
Row 1: set order_v=3, read back=2
...
After post-loop set: s0.order_v=2   ← still clamped, cannot be overridden
```

### Workaround (current implementation)

KS_JK_import_3dm stores the true rhino values as **custom properties** on the
Curve data block:

| Property | Meaning |
|---|---|
| `rhino_order_u` | NURBS order in U |
| `rhino_order_v` | NURBS order in V (Blender always clamps this to 2) |
| `rhino_cyclic_u` | 1 if surface is closed in U, else 0 |
| `rhino_cyclic_v` | 1 if surface is closed in V, else 0 |

The exporter (`export_nurbs_3dm.py`) reads these properties when it detects
multi-spline format, restoring the correct values for `.3dm` output.

### API requirement to resolve properly

The correct fix requires **one of the following changes to Blender's Python API**:

1. **Make `point_count_u` writable** — allow Python to set `pntsu` on an
   existing spline after points have been added.  Combined with exposing
   `point_count_v` (writable), this would let a script lay out all
   `count_u × count_v` points in a single spline and declare the U dimension,
   exactly matching the native 5.x single-spline format.

2. **Add a surface constructor** — a new API call such as
   `curves.new_surface(name, count_u, count_v)` or
   `splines.new('NURBS', count_u=N, count_v=M)` that creates a spline with the
   correct `pntsu`/`pntsv` from the outset, allowing `order_v` to be set to any
   valid value immediately.

Either change would let importers create surfaces in native Blender 5.x format
without requiring side-channel custom properties, and would make `order_v` and
cyclic flags directly readable by any exporter without special knowledge of the
import source.
