# Blender NURBS Surface — Python API Limitation

## Summary

Blender's Python API cannot create NURBS surfaces in the native Blender 5.x
format.  The internal U-dimension field (`pntsu`) is read-only from Python,
forcing importers to use a degraded multi-spline layout that cannot represent
`order_v > 2` or reliable cyclic flags.  A workaround using custom properties
is in place; the correct fix requires a Blender API change.

---

## Background

### How Blender stores NURBS surfaces internally

Blender stores a NURBS surface as a `Nurb` C struct containing:

| C field  | Meaning                          | Python property    |
|----------|----------------------------------|--------------------|
| `pntsu`  | Control point count in U         | `point_count_u` (read-only) |
| `pntsv`  | Control point count in V         | *(not exposed)*    |
| `orderu` | NURBS order in U                 | `order_u` (read/write) |
| `orderv` | NURBS order in V                 | `order_v` (read/write, but clamped — see below) |
| `flagsu` | Cyclic / endpoint flags for U    | `use_cyclic_u`, `use_endpoint_u` |
| `flagsv` | Cyclic / endpoint flags for V    | `use_cyclic_v`, `use_endpoint_v` |

In Blender 5.x, a NURBS surface object uses a **single spline** containing all
`pntsu × pntsv` control points stored in row-major order (V outer, U inner).
With both dimensions declared, `order_v` can be set up to `pntsv` and cyclic
flags apply correctly to the whole surface.

### What Python can create

`bpy.data.curves.new(name, 'SURFACE')` creates a Curve data block.
`surf_data.splines.new('NURBS')` creates one spline with `pntsu = 1, pntsv = 1`.
`spline.points.add(n)` extends the spline to `pntsu = n + 1`, leaving `pntsv = 1`.

There is **no API to set `pntsu` or `pntsv` directly**:

```python
spline.point_count_u = 4   # AttributeError: read-only
```

`pntsu` is declared `PROP_NOT_EDITABLE` in Blender's RNA.
`pntsv` has no RNA property at all.

---

## The Problem

### order_v is always clamped to 2

Because every Python-created spline has `pntsv = 1`, Blender enforces:

```
order_v = max(2, min(order_v, pntsv)) = max(2, min(N, 1)) = 2
```

regardless of what value the script assigns.  This was confirmed by diagnostic
script `/tmp/test_order_v.py`:

```
Row 0: set order_v=3, read back=2   ← clamped immediately on a 1-row spline
Row 1: set order_v=3, read back=2
...
After post-loop set on splines[0]: s0.order_v=2   ← cannot be overridden
```

### Multi-spline workaround is insufficient

Creating multiple splines (one per V-row) gives the correct point layout, but
each individual spline still has `pntsv = 1`, so `order_v` is clamped to 2 on
every row.  The `use_cyclic_u` / `use_cyclic_v` flags may also be lost or
unreliable in this multi-spline layout under Blender 5.x.

### Impact on round-trip export

Round-trip test `utilities/batch_compare_importers.py` reported:

```
[surface 0] OrderV: 3 vs 2     ← GEOMETRIC DIFFERENCES for sphere, torus, patch
```

Any surface imported from Rhino with `order_v > 2` (cubic or higher in V) will
be silently degraded to `order_v = 2` (linear between rows) when re-exported,
producing a geometrically different surface.

---

## Current Workaround

KS_JK_import_3dm stores the original Rhino values as **custom properties** on
the Curve data block immediately after import:

```python
surf_data["rhino_order_u"] = order_u   # int
surf_data["rhino_order_v"] = order_v   # int  ← the value Blender cannot hold
surf_data["rhino_cyclic_u"] = 1 if closed_u else 0
surf_data["rhino_cyclic_v"] = 1 if closed_v else 0
```

The exporter (`export_nurbs_3dm.py`) detects multi-spline format and reads
these properties instead of the (incorrect) spline properties:

```python
if not single_spline_5x:
    order_v    = int(obj.data.get("rhino_order_v", first.order_v))
    use_cyclic_u = bool(obj.data.get("rhino_cyclic_u", int(first.use_cyclic_u)))
    use_cyclic_v = bool(obj.data.get("rhino_cyclic_v", int(first.use_cyclic_v)))
```

This restores geometric correctness for the roundtrip, but relies on a
side-channel that is invisible to any other Blender tool or exporter that does
not know about these properties.

---

## API Requirement

The correct fix requires **one of the following changes to Blender's Python API**.

### Option A — Make `point_count_u` and `point_count_v` writable

```python
spline = surf_data.splines.new('NURBS')
spline.points.add(count_u * count_v - 1)   # lay out all U×V points
spline.point_count_u = count_u             # declare U dimension  ← NEW
# point_count_v is then inferred as total / point_count_u
spline.order_u = order_u
spline.order_v = order_v                   # now valid: pntsv = count_v
spline.use_cyclic_u = closed_u
spline.use_cyclic_v = closed_v
```

Minimum change: remove `PROP_NOT_EDITABLE` from the `pntsu` RNA property and
add a corresponding RNA property for `pntsv`.

### Option B — Surface-aware spline constructor

```python
spline = surf_data.splines.new('NURBS', count_u=count_u, count_v=count_v)
# spline is created with correct pntsu and pntsv from the outset
spline.order_v = order_v   # valid immediately
```

Or equivalently a method on the Curve data block:

```python
surf_data.new_surface_spline(count_u, count_v)
```

---

## Impact if Fixed

- Any Python importer (not just KS_JK) could create surfaces with correct
  `order_v`, cyclic flags, and V-row count without side-channel workarounds.
- Native Blender 5.x single-spline format would be reproducible from Python,
  making imported surfaces indistinguishable from natively created ones.
- The custom properties `rhino_order_v`, `rhino_cyclic_u`, `rhino_cyclic_v`
  in KS_JK_import_3dm could be removed.

---

## Related files

| File | Role |
|------|------|
| `KS_JK_import_3dm/import_3dm/converters/nurbs_surface.py` | Writes custom properties on import |
| `Blender_Export_3DM/export_nurbs_3dm.py` | Reads custom properties on export |
| `Blender_Export_3DM/utilities/batch_compare_importers.py` | Test that revealed the problem |
