#!/usr/bin/env python3
"""
Inspect a .3dm file to find geometry that FreeCAD's importer might fill
as a face (closed planar NurbsCurves of any degree).

Usage:
    python3 inspect_3dm.py path/to/file.3dm
"""
import sys
import rhino3dm as r


def bbox_diag(g):
    bb = g.GetBoundingBox()
    return ((bb.Max.X - bb.Min.X) ** 2 +
            (bb.Max.Y - bb.Min.Y) ** 2 +
            (bb.Max.Z - bb.Min.Z) ** 2) ** 0.5


def bbox_size(g):
    bb = g.GetBoundingBox()
    return (bb.Max.X - bb.Min.X,
            bb.Max.Y - bb.Min.Y,
            bb.Max.Z - bb.Min.Z)


def main(path):
    m = r.File3dm.Read(path)
    if m is None:
        print(f"Could not read: {path}")
        sys.exit(1)

    objs = list(m.Objects)
    print(f"File: {path}")
    print(f"Total objects: {len(objs)}\n")

    # Tally by geometry type
    by_type = {}
    for o in objs:
        k = type(o.Geometry).__name__
        by_type[k] = by_type.get(k, 0) + 1
    print("By geometry type:")
    for k, v in sorted(by_type.items()):
        print(f"  {k:20s} {v}")
    print()

    # Closed NurbsCurves of any degree (FreeCAD fills closed planar curves as faces)
    closed_curves = []
    for o in objs:
        g = o.Geometry
        if isinstance(g, r.NurbsCurve) and g.IsClosed:
            closed_curves.append(o)

    print(f"Closed NurbsCurves (FreeCAD will fill closed planar ones as faces): "
          f"{len(closed_curves)}")
    closed_curves.sort(key=lambda o: bbox_diag(o.Geometry), reverse=True)
    for o in closed_curves[:30]:
        g = o.Geometry
        sx, sy, sz = bbox_size(g)
        deg = g.Order - 1
        print(f"  diag={bbox_diag(g):8.2f}  size=({sx:6.2f}x{sy:6.2f}x{sz:6.2f})  "
              f"deg={deg} pts={len(g.Points)}  name={o.Attributes.Name!r}")
    print()

    # Top 15 largest objects overall
    print("Top 15 largest objects by bbox diagonal:")
    objs_sorted = sorted(objs, key=lambda o: bbox_diag(o.Geometry), reverse=True)
    for o in objs_sorted[:15]:
        g = o.Geometry
        sx, sy, sz = bbox_size(g)
        info = type(g).__name__
        detail = ""
        if isinstance(g, r.NurbsCurve):
            detail = f"deg={g.Order - 1} pts={len(g.Points)} closed={g.IsClosed}"
        elif isinstance(g, r.NurbsSurface):
            detail = (f"degU={g.OrderU - 1} degV={g.OrderV - 1} "
                      f"pts={g.Points.CountU}x{g.Points.CountV} "
                      f"closedU={g.IsClosed(0)} closedV={g.IsClosed(1)}")
        print(f"  diag={bbox_diag(g):8.2f}  size=({sx:6.2f}x{sy:6.2f}x{sz:6.2f})  "
              f"{info:14s}  {o.Attributes.Name or '':35s}  {detail}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python3 inspect_3dm.py path/to/file.3dm")
        sys.exit(1)
    main(sys.argv[1])
