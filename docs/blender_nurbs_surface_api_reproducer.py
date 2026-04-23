"""
Blender NURBS Surface Python API — minimal reproducer
======================================================
Demonstrates two gaps in the NURBS surface Python API:

  1. point_count_u (pntsu) is read-only — cannot declare U dimension.
  2. order_v is always clamped to 2 on any Python-created spline because
     pntsv is always 1 (not settable), so Blender enforces
     order_v = max(2, min(order_v, pntsv)) = 2.

Paste this script into Blender's Scripting editor and run it.
Tested on Blender 5.1.1.  Expected output shown in comments below.
"""

import bpy

print("\n=== NURBS Surface API reproducer ===\n")

# --- Test 1: point_count_u is read-only ---------------------------------

curve = bpy.data.curves.new("_repro", 'SURFACE')
curve.dimensions = '3D'
spline = curve.splines.new('NURBS')
spline.points.add(3)          # 4 points; pntsu=4, pntsv=1

try:
    spline.point_count_u = 4
    print("UNEXPECTED: point_count_u is writable")
except AttributeError as e:
    print(f"[FAIL] point_count_u read-only: {e}")
    # Expected: AttributeError: bpy_struct: attribute "point_count_u" from
    #           "SplinePoints" is read-only

# --- Test 2: order_v is always clamped to 2 on a single-row spline ------

spline.order_v = 3
print(f"[FAIL] single spline  set order_v=3  read back={spline.order_v}")
# Expected: read back=2   (clamped because pntsv=1)

# --- Test 3: multi-spline layout — order_v still clamped ----------------
# Creating one spline per V-row is the only way Python can lay out a
# grid of control points, but each spline independently has pntsv=1.

print()
for i in range(4):
    row = curve.splines.new('NURBS')
    row.points.add(3)         # 4 points per row
    row.order_u = 4
    row.order_v = 3
    print(f"[FAIL] row {i}  set order_v=3  read back={row.order_v}")
    # Expected: read back=2 for every row

# --- Test 4: what a native Blender surface looks like -------------------
# If you create a NURBS surface via the UI (Add → Surface → NURBS Surface)
# Blender produces a SINGLE spline with pntsu=4, pntsv=4.
# The Python API cannot replicate this.

print()
print("Native Blender surface (created via UI Add → Surface → NURBS Surface):")
print("  len(splines) == 1")
print("  splines[0].point_count_u == 4   (inner U dimension)")
print("  len(splines[0].points)   == 16  (4×4 control points)")
print("  splines[0].order_v       == 4   (cubic in V — correct)")
print()
print("Python-created surface (this script):")
print(f"  len(splines) == {len(curve.splines)}")
print(f"  splines[0].point_count_u == {curve.splines[0].point_count_u}")
print(f"  splines[0].order_v       == {curve.splines[0].order_v}  (always 2, unusable)")

# Cleanup
bpy.data.curves.remove(curve)
print("\n=== Done ===")
