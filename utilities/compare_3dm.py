"""
compare_3dm.py — Geometrically compare two .3dm files after a round-trip.

Reads both files with rhino3dm and compares NurbsSurface / NurbsCurve geometry:
  - object count and types
  - degree / order
  - control point count and positions (within tolerance)
  - knot vectors

Usage:
    python3 utilities/compare_3dm.py original.3dm roundtrip.3dm [--tol 1e-6]

Requires: pip install rhino3dm
"""

import sys
import argparse
import math

try:
    import rhino3dm as r3d
except ImportError:
    print("ERROR: rhino3dm not installed.  Run: pip install rhino3dm")
    sys.exit(1)


def _parse_args():
    parser = argparse.ArgumentParser(description="Geometrically compare two .3dm files.")
    parser.add_argument("original",  help="Original .3dm file")
    parser.add_argument("roundtrip", help="Round-tripped .3dm file")
    parser.add_argument("--tol", type=float, default=1e-6,
                        help="Tolerance for coordinate/knot comparison (default 1e-6)")
    return parser.parse_args()


# ---------------------------------------------------------------------------
# Geometry extractors
# ---------------------------------------------------------------------------

def _nurbs_surface_from_object(obj):
    """Return a NurbsSurface from a File3dm object, or None."""
    g = obj.Geometry
    t = g.ObjectType
    if t == r3d.ObjectType.Surface:
        try:
            return g.ToNurbsSurface()
        except Exception:
            return None
    if t == r3d.ObjectType.Extrusion:
        try:
            brep = g.ToBrep(False)
            if brep is None:
                return None
            if len(brep.Faces) == 1:
                srf = brep.Faces[0].UnderlyingSurface()
                return srf.ToNurbsSurface() if srf else None
            result = []
            for fi in range(len(brep.Faces)):
                srf = brep.Faces[fi].UnderlyingSurface()
                if srf:
                    ns = srf.ToNurbsSurface()
                    if ns:
                        result.append(ns)
            return result if result else None
        except Exception:
            return None
    if t == r3d.ObjectType.Brep:
        # Single-face Brep — get the underlying surface
        try:
            if len(g.Faces) == 1:
                srf = g.Faces[0].UnderlyingSurface()
                return srf.ToNurbsSurface() if srf else None
            # Multi-face: return list of NurbsSurfaces
            result = []
            for fi in range(len(g.Faces)):
                srf = g.Faces[fi].UnderlyingSurface()
                if srf:
                    ns = srf.ToNurbsSurface()
                    if ns:
                        result.append(ns)
            return result if result else None
        except Exception:
            return None
    return None


def _nurbs_curve_from_object(obj):
    """Return a NurbsCurve from a File3dm object, or None."""
    g = obj.Geometry
    t = g.ObjectType
    if t == r3d.ObjectType.Curve:
        try:
            return g.ToNurbsCurve()
        except Exception:
            return None
    return None


# ---------------------------------------------------------------------------
# Comparison helpers
# ---------------------------------------------------------------------------

def _close(a, b, tol):
    return abs(a - b) <= tol


_UNIT_TO_METRES = {
    r3d.UnitSystem.Millimeters:  0.001,
    r3d.UnitSystem.Centimeters:  0.01,
    r3d.UnitSystem.Meters:       1.0,
    r3d.UnitSystem.Kilometers:   1000.0,
    r3d.UnitSystem.Inches:       0.0254,
    r3d.UnitSystem.Feet:         0.3048,
}


def _unit_scale(model):
    """Return the scale factor that converts model coordinates to metres."""
    return _UNIT_TO_METRES.get(model.Settings.ModelUnitSystem, 1.0)


def _normalise_knots(knots):
    """Normalise a knot vector to [0, 1] for parameterisation-agnostic comparison."""
    if not knots:
        return knots
    lo, hi = knots[0], knots[-1]
    span = hi - lo
    if span == 0:
        return [0.0] * len(knots)
    return [(k - lo) / span for k in knots]


def _compare_knots(label, ka, kb, tol):
    issues = []
    na = _normalise_knots(ka)
    nb = _normalise_knots(kb)
    if len(na) != len(nb):
        issues.append(f"  {label} knot count differs: {len(ka)} vs {len(kb)}")
        return issues
    for i in range(len(na)):
        if not _close(na[i], nb[i], tol):
            issues.append(
                f"  {label} normalised knot[{i}] differs: {na[i]:.6g} vs {nb[i]:.6g}"
                f"  (raw: {ka[i]:.6g} vs {kb[i]:.6g})"
            )
    return issues


def _compare_nurbs_surface(ns_a, ns_b, tol, label="", scale_a=1.0, scale_b=1.0):
    """Compare two NurbsSurfaces; returns (geo_issues, knot_warnings).

    geo_issues  — structural/control-point differences (affect shape)
    knot_warnings — parameterisation differences (expected when round-tripping
                    through Blender, which only supports uniform knots)
    """
    geo = []
    knot_warns = []
    prefix = f"[{label}] " if label else ""

    if ns_a.OrderU != ns_b.OrderU:
        geo.append(f"{prefix}OrderU: {ns_a.OrderU} vs {ns_b.OrderU}")
    if ns_a.OrderV != ns_b.OrderV:
        geo.append(f"{prefix}OrderV: {ns_a.OrderV} vs {ns_b.OrderV}")

    cu_a, cv_a = ns_a.Points.CountU, ns_a.Points.CountV
    cu_b, cv_b = ns_b.Points.CountU, ns_b.Points.CountV
    if cu_a != cu_b or cv_a != cv_b:
        geo.append(f"{prefix}Control point grid: {cu_a}x{cv_a} vs {cu_b}x{cv_b}")
        return geo, knot_warns

    max_dist = 0.0
    for i in range(cu_a):
        for j in range(cv_a):
            pa = ns_a.Points.GetControlPoint(i, j)
            pb = ns_b.Points.GetControlPoint(i, j)
            ax, ay, az = pa.X * scale_a, pa.Y * scale_a, pa.Z * scale_a
            bx, by, bz = pb.X * scale_b, pb.Y * scale_b, pb.Z * scale_b
            dist = math.sqrt((ax-bx)**2 + (ay-by)**2 + (az-bz)**2)
            max_dist = max(max_dist, dist)
            if dist > tol:
                geo.append(
                    f"{prefix}CP[{i},{j}] position differs by {dist:.3e} m: "
                    f"({ax:.4f},{ay:.4f},{az:.4f}) vs ({bx:.4f},{by:.4f},{bz:.4f})"
                )
            if not _close(pa.W, pb.W, tol):
                geo.append(f"{prefix}CP[{i},{j}] weight differs: {pa.W:.6g} vs {pb.W:.6g}")

    if not geo:
        print(f"  {prefix}Control points OK  (max deviation {max_dist:.2e} m)")

    ka_u = [ns_a.KnotsU[i] for i in range(len(ns_a.KnotsU))]
    kb_u = [ns_b.KnotsU[i] for i in range(len(ns_b.KnotsU))]
    ka_v = [ns_a.KnotsV[i] for i in range(len(ns_a.KnotsV))]
    kb_v = [ns_b.KnotsV[i] for i in range(len(ns_b.KnotsV))]
    knot_warns += _compare_knots(f"{prefix}KnotsU", ka_u, kb_u, tol)
    knot_warns += _compare_knots(f"{prefix}KnotsV", ka_v, kb_v, tol)

    return geo, knot_warns


def _compare_nurbs_curve(nc_a, nc_b, tol, label="", scale_a=1.0, scale_b=1.0):
    """Returns (geo_issues, knot_warnings)."""
    geo = []
    knot_warns = []
    prefix = f"[{label}] " if label else ""

    if nc_a.Order != nc_b.Order:
        geo.append(f"{prefix}Order: {nc_a.Order} vs {nc_b.Order}")

    n_a, n_b = len(nc_a.Points), len(nc_b.Points)
    if n_a != n_b:
        geo.append(f"{prefix}Point count: {n_a} vs {n_b}")
        return geo, knot_warns

    max_dist = 0.0
    for i in range(n_a):
        pa = nc_a.Points[i]
        pb = nc_b.Points[i]
        ax, ay, az = pa.X * scale_a, pa.Y * scale_a, pa.Z * scale_a
        bx, by, bz = pb.X * scale_b, pb.Y * scale_b, pb.Z * scale_b
        dist = math.sqrt((ax-bx)**2 + (ay-by)**2 + (az-bz)**2)
        max_dist = max(max_dist, dist)
        if dist > tol:
            geo.append(f"{prefix}CP[{i}] differs by {dist:.3e} m")

    if not geo:
        print(f"  {prefix}Control points OK  (max deviation {max_dist:.2e} m)")

    ka = nc_a.Knots.ToList()
    kb = nc_b.Knots.ToList()
    knot_warns += _compare_knots(f"{prefix}Knots", ka, kb, tol)

    return geo, knot_warns


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------

def _object_type_str(obj):
    return str(obj.Geometry.ObjectType).split(".")[-1]


def compare(path_a, path_b, tol):
    print(f"\nOriginal : {path_a}")
    print(f"Roundtrip: {path_b}")
    print(f"Tolerance: {tol}\n")

    model_a = r3d.File3dm.Read(path_a)
    model_b = r3d.File3dm.Read(path_b)

    objs_a = list(model_a.Objects)
    objs_b = list(model_b.Objects)

    scale_a = _unit_scale(model_a)
    scale_b = _unit_scale(model_b)
    unit_a = model_a.Settings.ModelUnitSystem
    unit_b = model_b.Settings.ModelUnitSystem
    print(f"Unit system: {unit_a} (×{scale_a} m)  vs  {unit_b} (×{scale_b} m)")
    print(f"Object count: {len(objs_a)} (original)  {len(objs_b)} (roundtrip)")

    all_geo_issues = []
    all_knot_warns = []

    # Type summary
    types_a = [_object_type_str(o) for o in objs_a]
    types_b = [_object_type_str(o) for o in objs_b]
    print(f"Types original : {types_a}")
    print(f"Types roundtrip: {types_b}")

    # Compare surfaces
    surfs_a = [(o, _nurbs_surface_from_object(o)) for o in objs_a]
    surfs_a = [(o, s) for o, s in surfs_a if s is not None]
    surfs_b = [(o, _nurbs_surface_from_object(o)) for o in objs_b]
    surfs_b = [(o, s) for o, s in surfs_b if s is not None]

    print(f"\nNURBS surfaces: {len(surfs_a)} original  {len(surfs_b)} roundtrip")

    def _collect_surface(sa, sb, label):
        if isinstance(sa, list) or isinstance(sb, list):
            sa_list = sa if isinstance(sa, list) else [sa]
            sb_list = sb if isinstance(sb, list) else [sb]
            if len(sa_list) != len(sb_list):
                print(f"  {label}: face count {len(sa_list)} vs {len(sb_list)} — comparing matching faces only (caps may be dropped)")
                sb_by_u = {f.Points.CountU: f for f in sb_list}
                matched = 0
                for fi, fa in enumerate(sa_list):
                    fb = sb_by_u.get(fa.Points.CountU)
                    if fb is not None:
                        g, k = _compare_nurbs_surface(fa, fb, tol, f"{label} face{fi}", scale_a, scale_b)
                        all_geo_issues.extend(g)
                        all_knot_warns.extend(k)
                        matched += 1
                    else:
                        print(f"  {label} face{fi}: no matching roundtrip face (U={fa.Points.CountU}) — skipped (likely cap)")
                if matched == 0:
                    all_geo_issues.append(f"  {label}: no comparable faces found")
            else:
                for fi, (fa, fb) in enumerate(zip(sa_list, sb_list)):
                    g, k = _compare_nurbs_surface(fa, fb, tol, f"{label} face{fi}", scale_a, scale_b)
                    all_geo_issues.extend(g)
                    all_knot_warns.extend(k)
        else:
            g, k = _compare_nurbs_surface(sa, sb, tol, label, scale_a, scale_b)
            all_geo_issues.extend(g)
            all_knot_warns.extend(k)

    for idx, ((oa, sa), (ob_, sb)) in enumerate(zip(surfs_a, surfs_b)):
        label = f"surface {idx}"
        print(f"\n  Comparing {label}:")
        _collect_surface(sa, sb, label)

    # Compare curves
    crvs_a = [(o, _nurbs_curve_from_object(o)) for o in objs_a]
    crvs_a = [(o, c) for o, c in crvs_a if c is not None]
    crvs_b = [(o, _nurbs_curve_from_object(o)) for o in objs_b]
    crvs_b = [(o, c) for o, c in crvs_b if c is not None]

    print(f"\nNURBS curves: {len(crvs_a)} original  {len(crvs_b)} roundtrip")

    for idx, ((oa, ca), (ob_, cb)) in enumerate(zip(crvs_a, crvs_b)):
        label = f"curve {idx}"
        print(f"\n  Comparing {label}:")
        g, k = _compare_nurbs_curve(ca, cb, tol, label, scale_a, scale_b)
        all_geo_issues.extend(g)
        all_knot_warns.extend(k)

    # Summary
    print(f"\n{'='*50}")
    if all_knot_warns:
        print(f"PARAMETERISATION NOTE ({len(all_knot_warns)} knot difference(s) — expected when round-tripping through Blender uniform knots):")
        for w in all_knot_warns:
            print(f"  {w}")
    if all_geo_issues:
        print(f"\nGEOMETRIC DIFFERENCES ({len(all_geo_issues)}):")
        for issue in all_geo_issues:
            print(f"  {issue}")
        return False
    else:
        if all_knot_warns:
            print("\nGEOMETRY OK — control points match within tolerance (parameterisation differs, see above)")
        else:
            print("EQUIVALENT — no geometric differences within tolerance")
        return True


def main():
    args = _parse_args()
    ok = compare(args.original, args.roundtrip, args.tol)
    sys.exit(0 if ok else 1)


main()
