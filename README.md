# Export NURBS 3DM — Blender Extension

Exports Blender NURBS surfaces and curves to Rhino **3DM** format using the
open-source `rhino3dm` library. Unlike mesh-based exporters, this addon
preserves the exact NURBS representation — control points, weights, degree,
and knot vectors — so the geometry arrives in Rhino or FreeCAD as true
B-spline surfaces, not tessellated approximations.

## Supported geometry

| Blender type | Exported as |
|---|---|
| Surface (NURBS) | `NurbsSurface` |
| Curve (NURBS) | `NurbsCurve` |
| Mesh (optional) | `Mesh` |

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

This exporter is the Blender end of a Blender → 3DM → FreeCAD NURBS pipeline:

```
Blender NURBS surface
    ↓ Export NURBS 3DM (.3dm)
Rhino 3DM file  (NurbsSurface entities, clamped cubic knots)
    ↓ FreeCAD ImportExport_3DM workbench
OCCT BSplineSurface  (exact, no tessellation)
```

It also pairs with [KS_JK_import_3dm](https://github.com/KeithSloan/KS_JK_import_3dm)
for round-trip testing: import a `.3dm` as Blender NURBS surfaces, then export
back to verify geometric equivalence.

## Utilities

The `utilities/` directory contains command-line tools for batch testing:

### batch_roundtrip.py

Import one or more `.3dm` files via the KS_JK_import_3dm addon and re-export
using this exporter. Run headlessly via Blender's `--background` mode.

```bash
/Applications/Blender_4.4.app/Contents/MacOS/Blender --background \
    --python utilities/batch_roundtrip.py -- \
    --input  /path/to/testCases \
    --output /tmp/roundtrip \
    --nurbs
```

Options:
- `--input`  — path to a single `.3dm` file or a directory of files
- `--output` — output directory for exported files
- `--nurbs` — import Breps as NURBS Surface objects and curves as NURBS Curve objects (recommended)
- `--all-objects` — export all scene objects (default: selection only)

### compare_3dm.py

Geometrically compare two `.3dm` files — useful for verifying round-trips.
Normalises coordinates to metres using each file's declared unit system, and
compares control points, order, and normalised knot vectors.

```bash
python3 utilities/compare_3dm.py original.3dm roundtrip.3dm [--tol 1e-6]
```

Exits 0 if equivalent, 1 if differences found.

## Sample files

The `SampleFiles/` directory contains a simple test case:

| File | Description |
|------|-------------|
| `SampleFiles/SimpleSurface.blend` | Blender file with a 4×4 cubic NURBS surface patch |
| `SampleFiles/SimpleSurface.3dm` | Exported 3DM — ready to import into Rhino or FreeCAD |

Open `SimpleSurface.blend`, export with this addon, then import the resulting
`.3dm` into FreeCAD using the
[ImportExport_3DM](https://github.com/KeithSloan/ImportExport_3DM) workbench
to verify the full pipeline end-to-end.

## Notes

- Output files are written in **metres** (Blender's internal unit system).
  Rhino and FreeCAD will display values correctly when the unit system is read
  from the file.
- Knot vectors are always exported as **clamped** (endpoint-interpolating)
  for compatibility with OpenCASCADE / FreeCAD.
- World transform is baked into the control points on export.
- Blender NURBS surfaces must have `use_cyclic` off for best results.

## License

GNU General Public License v3.0 — see [LICENSE](LICENSE).
