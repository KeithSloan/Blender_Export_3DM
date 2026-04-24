# Export NURBS 3DM — Blender Extension

Exports Blender NURBS surfaces and curves to Rhino **3DM** format using the
open-source `rhino3dm` library. Unlike mesh-based exporters, this addon
preserves the exact NURBS representation — control points, weights, degree,
and knot vectors — so the geometry arrives in Rhino or FreeCAD as true
B-spline surfaces, not tessellated approximations.

## Supported geometry

### Native Blender objects

| Blender type | Exported as |
|---|---|
| Surface (NURBS) | `NurbsSurface` |
| Curve (NURBS) | `NurbsCurve` |
| Curve (Bezier) | `NurbsCurve` degree 3 with piecewise-Bezier knots |
| Mesh (optional) | `Mesh` |

### Surface Psycho objects

[Surface Psycho](https://github.com/Poulpator/Bezier-quest) is a Blender
geometry-nodes addon that stores NURBS/Bezier surface data as **mesh
attributes** rather than using Blender's native SURFACE type.  The exporter
detects SP objects by their geometry-node modifier name and reads the surface
data directly from those attributes — no intermediate mesh conversion.

| SP type | Detected by modifier | Exported as |
|---|---|---|
| NURBS Patch (`SP - NURBS Patch Meshing`) | `CP_NURBS_surf`, `Degrees`, `Knot U/V`, `Multiplicity U/V` | `NurbsSurface` |
| Bezier Patch (`SP - Bezier Patch Meshing`) | `CP_any_order_surf`, `CP_count` | `NurbsSurface` (degree = count − 1) |

SP object types that are not yet supported (FlatPatch, Curve, Cylinder, Sphere,
Cone, Torus, Surface of Revolution/Extrusion) are skipped with an informational
message.

## Conventions used in this document

After installing Blender, rename the application bundle to include the version
number so multiple versions can coexist:

```bash
mv /Applications/Blender.app /Applications/Blender_5.1.1.app
```

All shell commands below use this `Blender_x.y.z.app` naming convention.

## Requirements

### rhino3dm Python library

`rhino3dm` must be installed into **Blender's own Python interpreter** —
the system Python is not used.

Find the correct Python binary for your Blender version:

```bash
# Blender 4.4
/Applications/Blender_4.4.app/Contents/Resources/4.4/python/bin/python3.11 -m pip install rhino3dm

# Blender 5.0
/Applications/Blender.app/Contents/Resources/5.0/python/bin/python3.11 -m pip install rhino3dm
```

On Linux/Windows, find the equivalent path inside the Blender application
folder and run the same `pip install rhino3dm` command.

## Installation

### From zip (Blender 4.2+)

1. Download `export_nurbs_3dm.zip`
2. `Edit → Preferences → Extensions → Install from Disk`
3. Select the zip file
4. Enable **Export NURBS 3DM** in the Extensions list

> **macOS note:** Blender's file browser may not display `.zip` files.
> Use the symlink method below instead.

### Symlink (development / macOS workaround)

```bash
ln -s /path/to/Blender_Export_3DM \
  "$HOME/Library/Application Support/Blender/4.4/extensions/user_default/export_nurbs_3dm"
```

Then enable in `Edit → Preferences → Extensions`.

## Usage

`File → Export → NURBS Rhino 3DM (.3dm)`

Options:
- **Selection Only** — export only selected objects (default: on)
- **Export Meshes** — include mesh objects as rhino3dm Mesh (default: off)

## Pipeline

This exporter supports two Blender → 3DM → FreeCAD NURBS pipelines:

```
Blender NURBS surface  (native SURFACE type)
    ↓ Export NURBS 3DM (.3dm)
Rhino 3DM file  (NurbsSurface entities, clamped knots)
    ↓ FreeCAD ImportExport_3DM workbench
OCCT BSplineSurface  (exact, no tessellation)
```

```
Surface Psycho NURBS/Bezier patch  (MESH type with GN attributes)
    ↓ Export NURBS 3DM (.3dm)
Rhino 3DM file  (NurbsSurface entities, knots from SP attributes)
    ↓ FreeCAD ImportExport_3DM workbench
OCCT BSplineSurface  (exact, no tessellation)
```

Surface Psycho also has its own direct STEP/IGES exporter
(`File → Export → Export STEP / Export IGES`) which uses Open CASCADE (OCP)
and produces the same geometry.  The 3DM route is useful when the target
application reads `.3dm` but not STEP/IGES.

It also pairs with [KS_JK_import_3dm](https://github.com/KeithSloan/KS_JK_import_3dm)
for round-trip testing: import a `.3dm` as Blender NURBS surfaces, then export
back to verify geometric equivalence.

**KS_JK_import_3dm** is a fork of
[JesterKing's import_3dm](https://github.com/jesterKing/import_3dm).  The fork
adds:

- NURBS Surface import (`ObjectType.Surface` dispatch, in addition to Brep)
- Custom properties (`rhino_order_u`, `rhino_order_v`, `rhino_cyclic_u`,
  `rhino_cyclic_v`) stored on each imported Curve data block to preserve NURBS
  properties that Blender's Python API cannot store natively in multi-spline
  format (see *Blender NURBS surface — Python API limitation* in `CLAUDE.md`)
- A distinct `bl_idname` (`ks_jk_import_3dm.some_data`) so both importers can
  be enabled simultaneously for side-by-side comparison testing

## Utilities

The `utilities/` directory contains command-line tools for batch testing.
All scripts run headlessly via Blender's `--background` mode.

### batch_3dm_compare.py

**`.3dm` → import → export → compare**

For each `.3dm` file in `Sample_3DM_Files/`: import with KS_JK_import_3dm,
re-export, and compare original vs roundtrip.

```bash
/Applications/Blender_5.1.1.app/Contents/MacOS/Blender --background \
    --python utilities/batch_3dm_compare.py -- \
    --input  Sample_3DM_Files \
    --output /tmp/3dm_compare
```

### batch_blend_compare.py

**`.blend` → export → import → re-export → compare**

For each `.blend` file: export to `.3dm`, import back with KS_JK_import_3dm,
re-export, and compare the two `.3dm` files.

```bash
/Applications/Blender_5.1.1.app/Contents/MacOS/Blender --background \
    --python utilities/batch_blend_compare.py -- \
    --input  SampleBlendFiles/V5.1.1 \
    --output /tmp/blend_compare
```

### batch_compare_importers.py

**`.blend` → export → import (JK & KS side-by-side) → re-export → compare**

As above but runs both JesterKing's importer and KS_JK_import_3dm in the same
session and prints a side-by-side comparison table.  Useful for tracking which
geometry types each importer supports.

```bash
/Applications/Blender_5.1.1.app/Contents/MacOS/Blender --background \
    --python utilities/batch_compare_importers.py -- \
    --input  SampleBlendFiles/V5.1.1 \
    --output /tmp/compare_out
```

### compare_3dm.py

Geometrically compare two `.3dm` files — used internally by the batch scripts
above and also callable directly:

```bash
python3 utilities/compare_3dm.py original.3dm roundtrip.3dm [--tol 1e-6]
```

Normalises coordinates to metres, compares control points, weights, and
normalised knot vectors.  Control-point differences cause exit code 1;
knot-vector differences are informational only (Blender uses uniform knots
so parameterisation shifts are expected on closed/rational surfaces).

### batch_roundtrip.py

Earlier import-and-re-export script (no comparison).  Superseded by
`batch_3dm_compare.py` for most uses.

## Sample files

```
SampleBlendFiles/
  V5.1.1_Shapes.blend     ← all V5.1.1 shapes combined
  V4.4/                   ← Blender 4.4 test files
  V5.1.1/                 ← individual Blender 5.1.1 test files
```

### Blender 5.1.1 — `SampleBlendFiles/V5.1.1/`

Test scenes covering the main NURBS geometry types, created in Blender 5.1.1:

| File | Contents |
|------|----------|
| `V5.1.1_SurfPatch.blend` | Flat NURBS surface patch |
| `V5.1.1_SurfCylinder.blend` | NURBS cylinder surface |
| `V5.1.1_SurfSphere.blend` | NURBS sphere surface |
| `V5.1.1_SurfCircle_.blend` | NURBS circle surface |
| `V5.1.1_SurfTorus.blend` | NURBS torus surface |
| `V5.1.1_SurfTor_us.blend` | NURBS torus surface (variant) |
| `V5.1.1_NurbsCurve.blend` | NURBS curve |
| `V5.1.1_BezierCurve.blend` | Bezier curve |

Open any file, select the object, and use `File → Export → NURBS Rhino 3DM (.3dm)`
to export.  Import the resulting `.3dm` into FreeCAD via the
[ImportExport_3DM](https://github.com/KeithSloan/ImportExport_3DM) workbench,
or import back into Blender via
[KS_JK_import_3dm](https://github.com/KeithSloan/KS_JK_import_3dm) for
round-trip verification.

### Blender 4.4 — `SampleBlendFiles/V4.4/`

| File | Description |
|------|-------------|
| `V4.4_Curves.blend` | Blender 4.4 NURBS curves |
| `V4.4_Surfaces.blend` | Blender 4.4 NURBS surfaces |
| `SimpleSurface.blend` | 4×4 cubic NURBS surface patch |
| `SimpleSurface.3dm` | Exported 3DM — ready to import into Rhino or FreeCAD |

### Rhino sample files — `Sample_3DM_Files/`

`.3dm` files copied from the
[ImportExport_3DM](https://github.com/KeithSloan/ImportExport_3DM) FreeCAD
workbench `testCases/` directory.  These are Rhino-originated files useful for
testing the KS_JK_import_3dm importer independently of the Blender exporter.

| File | Geometry |
|------|----------|
| `ArcCurve.3dm` | Arc curve |
| `BezierCurve.3dm` | Bezier curve |
| `Circle.3dm` | Circle curve |
| `Cone.3dm` | Cone surface |
| `Curve.3dm` | NURBS curve |
| `Cylinder.3dm` | Cylinder surface |
| `Ellipse.3dm` | Ellipse curve |
| `LineCurve.3dm` | Line curve |
| `PointCloud.3dm` | Point cloud |
| `PolyCurve_Joined_Line_NURBS-curve.3dm` | Joined polycurve |
| `PolyCurve_PolyLine.3dm` | Polyline |
| `PolysurfCylinder.3dm` | Polysurface cylinder |
| `Surface.3dm` | NURBS surface |

### Round-trip test results — Blender 5.1.1 (KS_JK_import_3dm)

Run with `utilities/batch_compare_importers.py` against `SampleBlendFiles/V5.1.1/`:

| File | JK importer | KS importer |
|------|-------------|-------------|
| BezierCurve | EQUIVALENT | EQUIVALENT |
| NurbsCurve | GEOMETRY OK | GEOMETRY OK |
| SurfCircle_ | GEOMETRY OK | GEOMETRY OK |
| SurfCylinder | — | GEOMETRY OK |
| SurfPatch | — | GEOMETRY OK |
| SurfSphere | — | EQUIVALENT |
| SurfTor_us | — | GEOMETRY OK |
| SurfTorus | — | GEOMETRY OK |

`—` = JK importer does not support NURBS Surface import (falls back to render mesh, no roundtrip possible).

Bezier curves are exported as degree-3 NurbsCurves with piecewise-Bezier knots
and round-trip correctly through both importers.

## Notes

- Output files are written in **metres** (Blender's internal unit system).
  Rhino and FreeCAD will display values correctly when the unit system is read
  from the file.
- NURBS curves and surfaces use **clamped** knot vectors (endpoint-interpolating)
  for compatibility with OpenCASCADE / FreeCAD.
- Bezier curves use piecewise-Bezier knots (multiplicity = degree at each segment
  junction) which preserves exact Bezier segment geometry.
- World transform is baked into the control points on export for native Blender
  SURFACE/CURVE objects.
- Cyclic (closed) surfaces are exported correctly — the sphere and torus round-trip cleanly.
- **Surface Psycho objects:** SP stores control points in world space inside the
  geometry-node attributes, so no additional world-transform is applied.  SP
  objects with non-identity object transforms should be applied before export
  (same requirement as SP's own STEP/IGES exporter).

## Known limitation — Blender NURBS surface Python API

Round-trip testing with rhino3dm revealed that Blender's Python API cannot
create NURBS surfaces in the native Blender 5.x format.  Blender stores surfaces
as a single spline with `pntsu × pntsv` control points, but `point_count_u`
(`pntsu`) is **read-only** from Python (`PROP_NOT_EDITABLE`), and `pntsv` has no
Python exposure at all.

The only surface constructable from Python is a single-row surface (`pntsv = 1`),
causing Blender to clamp `order_v` to 2 regardless of the value set by the
script.  Cyclic flags in V are similarly unreliable.

**Current workaround:** KS_JK_import_3dm stores the original Rhino values as
custom properties (`rhino_order_u`, `rhino_order_v`, `rhino_cyclic_u`,
`rhino_cyclic_v`) on the Curve data block.  The exporter reads these back on
roundtrip.  This is a side-channel hack made necessary by the API gap.

**To resolve this properly, Blender's Python API needs one of:**

- `point_count_u` made writable, plus `point_count_v` exposed and writable, so
  a script can lay out a full `U × V` point grid in a single spline and declare
  both dimensions.
- A new surface constructor such as `splines.new('NURBS', count_u=N, count_v=M)`
  that creates a spline with the correct `pntsu`/`pntsv` from the outset.

Full technical details are in `CLAUDE.md` under
*Known limitation — Blender NURBS surface Python API*.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
