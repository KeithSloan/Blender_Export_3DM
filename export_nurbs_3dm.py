import bpy
from mathutils import Vector

try:
    import rhino3dm
    RHINO3DM_AVAILABLE = True
except ImportError:
    RHINO3DM_AVAILABLE = False


def make_knots(point_count, order, use_endpoint, use_cyclic):
    # rhino3dm knot vector length = point_count + order - 2 (no first/last entry)
    if use_cyclic:
        # Periodic: uniform sequential knots
        n = point_count + order - 2
        return [float(i) for i in range(n)]
    if use_endpoint:
        # Clamped: repeated values at start and end
        knots  = [0.0] * (order - 1)
        knots += [float(i) for i in range(1, point_count - order + 1)]
        knots += [float(point_count - order + 1)] * (order - 1)
    else:
        # Uniform: sequential integers
        n = point_count + order - 2
        knots = [float(i) for i in range(n)]
    return knots


def export_nurbs_surface(model, obj):
    """
    Export a Blender SURFACE object to a rhino3dm NurbsSurface.

    Blender NURBS surface storage formats
    --------------------------------------
    Blender 5.x stores surfaces natively as a *single* spline containing all
    count_u × count_v control points.  The read-only ``point_count_u`` property
    records the U dimension, allowing ``order_v`` and cyclic flags to be stored
    correctly.  This is detected here by: len(splines)==1 and
    point_count_u < len(points).

    Surfaces imported by KS_JK_import_3dm (and surfaces created by Blender 4.x)
    use *multi-spline* format: one spline per V-row.  The Python API cannot create
    the native single-spline layout because ``point_count_u`` is read-only.  As a
    consequence, Blender clamps ``order_v`` to 2 on each individual spline (since
    each row has pntsv=1).  Cyclic flags may also be unreliable in this format.

    To work around this, KS_JK_import_3dm stores the original rhino values as
    custom properties on the Curve data block: ``rhino_order_u``, ``rhino_order_v``,
    ``rhino_cyclic_u``, ``rhino_cyclic_v``.  This function reads those properties
    when operating on multi-spline format, so the correct values are used even
    though Blender's spline properties cannot hold them.
    """
    mat = obj.matrix_world
    splines = [s for s in obj.data.splines if s.type == 'NURBS']
    if not splines:
        print('  No NURBS splines — nothing to export')
        return

    first = splines[0]
    single_spline_5x = (len(splines) == 1 and first.point_count_u < len(first.points))

    if single_spline_5x:
        # Blender 5.x native single-spline format: all CVs in one spline,
        # point_count_u holds the U count, V = total / U.
        count_u = first.point_count_u
        count_v = len(first.points) // count_u
        order_u = first.order_u
        order_v = first.order_v
        use_cyclic_u = first.use_cyclic_u
        use_cyclic_v = first.use_cyclic_v
        use_endpoint_u = first.use_endpoint_u
        use_endpoint_v = first.use_endpoint_v
    else:
        # Multi-spline format (one spline per V-row).
        # Blender clamps order_v to 2 and may lose cyclic flags on individual
        # splines, so read stored rhino values from custom properties when available.
        count_u = len(first.points)
        count_v = len(splines)
        order_u = int(obj.data.get("rhino_order_u", first.order_u))
        order_v = int(obj.data.get("rhino_order_v", first.order_v))
        use_cyclic_u = bool(obj.data.get("rhino_cyclic_u", int(first.use_cyclic_u)))
        use_cyclic_v = bool(obj.data.get("rhino_cyclic_v", int(first.use_cyclic_v)))
        use_endpoint_u = not use_cyclic_u
        use_endpoint_v = not use_cyclic_v

    is_rational = any(p.co.w != 1.0 for s in splines for p in s.points)

    print(f'  NURBS surface: {count_u}x{count_v} CVs  order {order_u}x{order_v}  rational={is_rational}')
    print(f'  cyclic u={use_cyclic_u} v={use_cyclic_v}')
    print(f'  endpoint u={use_endpoint_u} v={use_endpoint_v}')

    if count_u < 2 or count_v < 2 or order_u < 2 or order_v < 2:
        print(f'  Skipped: degenerate surface ({count_u}x{count_v} CVs, order {order_u}x{order_v})')
        return

    srf = rhino3dm.NurbsSurface.Create(3, is_rational, order_u, order_v, count_u, count_v)

    if single_spline_5x:
        # Blender 5.x single-spline: CVs stored row-major (V outer, U inner)
        pts = first.points
        for vi in range(count_v):
            for ui in range(count_u):
                p = pts[vi * count_u + ui]
                w = p.co.w
                world = mat @ Vector((p.co.x, p.co.y, p.co.z))
                srf.Points[ui, vi] = rhino3dm.Point4d(
                    world.x * w, world.y * w, world.z * w, w)
    else:
        # Multi-spline: one spline per V-row
        for vi, spline in enumerate(splines):
            for ui, p in enumerate(spline.points):
                w = p.co.w
                world = mat @ Vector((p.co.x, p.co.y, p.co.z))
                srf.Points[ui, vi] = rhino3dm.Point4d(
                    world.x * w, world.y * w, world.z * w, w)

    ku = make_knots(count_u, order_u, use_endpoint=use_endpoint_u, use_cyclic=use_cyclic_u)
    kv = make_knots(count_v, order_v, use_endpoint=use_endpoint_v, use_cyclic=use_cyclic_v)
    print(f'  knots U({len(ku)}): {ku}')
    print(f'  knots V({len(kv)}): {kv}')

    for i, k in enumerate(ku):
        srf.KnotsU[i] = k
    for i, k in enumerate(kv):
        srf.KnotsV[i] = k

    attr = rhino3dm.ObjectAttributes()
    attr.Name = obj.name
    model.Objects.AddSurface(srf, attr)
    print(f'  Added NurbsSurface: {obj.name}')


def _export_bezier_spline(model, obj, spline, mat):
    """
    Export one Blender BEZIER spline as a degree-3 rhino3dm NurbsCurve.

    A Blender Bezier spline stores anchor points with left/right handles.
    Each segment (anchor[i] → anchor[i+1]) maps to four NURBS control points:
        anchor[i],  handle_right[i],  handle_left[i+1],  anchor[i+1]
    Adjacent segments share their anchor, so the total CV count is
    n_segs * 3 + 1 (non-cyclic) or n_segs * 3 (cyclic).

    Knot vector (rhino3dm format, first/last clamping knots omitted):
    - Non-cyclic: multiplicity = degree at each segment junction, giving the
      piecewise-Bezier parameterisation [0,0,0, 1,1,1, 2,2,2, ..., n,n,n].
    - Cyclic: uniform sequential integers (periodic parameterisation).
    """
    pts    = spline.bezier_points
    n_pts  = len(pts)
    if n_pts < 2:
        print(f'  Skipped: degenerate Bezier spline ({n_pts} anchor points)')
        return

    cyclic = spline.use_cyclic_u
    n_segs = n_pts if cyclic else n_pts - 1
    n_cv   = n_segs * 3 if cyclic else n_segs * 3 + 1
    degree = 3
    order  = degree + 1

    print(f'  Bezier curve: {n_pts} anchors  {n_segs} segs  {n_cv} CVs  cyclic={cyclic}')

    nc = rhino3dm.NurbsCurve(3, False, order, n_cv)

    # Control points: for each segment, emit anchor[i], right[i], left[i+1].
    # For non-cyclic, append the final anchor after the loop.
    cv_idx = 0
    for i in range(n_segs):
        curr = pts[i]
        nxt  = pts[(i + 1) % n_pts]
        for co in (curr.co, curr.handle_right, nxt.handle_left):
            world = mat @ Vector(co)
            nc.Points[cv_idx] = rhino3dm.Point4d(world.x, world.y, world.z, 1.0)
            cv_idx += 1
    if not cyclic:
        world = mat @ Vector(pts[-1].co)
        nc.Points[cv_idx] = rhino3dm.Point4d(world.x, world.y, world.z, 1.0)

    # Knot vector
    if cyclic:
        for i in range(n_cv + degree - 1):
            nc.Knots[i] = float(i)
    else:
        k = 0
        for i in range(n_segs + 1):
            for _ in range(degree):
                nc.Knots[k] = float(i)
                k += 1

    attr = rhino3dm.ObjectAttributes()
    attr.Name = obj.name
    model.Objects.AddCurve(nc, attr)
    print(f'  Added BezierCurve (as NurbsCurve degree 3): {obj.name}')


def export_nurbs_curve(model, obj):
    mat = obj.matrix_world
    for spline in obj.data.splines:
        if spline.type == 'BEZIER':
            _export_bezier_spline(model, obj, spline, mat)
            continue

        if spline.type != 'NURBS':
            print(f'  Skipped spline type: {spline.type}')
            continue

        n = len(spline.points)
        order = spline.order_u
        is_rational = any(p.co.w != 1.0 for p in spline.points)

        print(f'  NURBS curve: {n} CVs  order {order}  rational={is_rational}')

        nc = rhino3dm.NurbsCurve(3, is_rational, order, n)
        for i, p in enumerate(spline.points):
            w = p.co.w
            world = mat @ Vector((p.co.x, p.co.y, p.co.z))
            nc.Points[i] = rhino3dm.Point4d(world.x * w, world.y * w, world.z * w, w)

        ku = make_knots(n, order, spline.use_endpoint_u, spline.use_cyclic_u)
        print(f'  knots U({len(ku)}): {ku}')
        for i, k in enumerate(ku):
            nc.Knots[i] = k

        attr = rhino3dm.ObjectAttributes()
        attr.Name = obj.name
        model.Objects.AddCurve(nc, attr)
        print(f'  Added NurbsCurve: {obj.name}')


def export_mesh(model, obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ob_eval = obj.evaluated_get(depsgraph)
    me = ob_eval.to_mesh()
    if me is None:
        return

    mat = obj.matrix_world
    r3mesh = rhino3dm.Mesh()

    for v in me.vertices:
        world = mat @ v.co
        r3mesh.Vertices.Add(world.x, world.y, world.z)

    for face in me.polygons:
        verts = list(face.vertices)
        if len(verts) == 3:
            r3mesh.Faces.AddFace(verts[0], verts[1], verts[2])
        elif len(verts) == 4:
            r3mesh.Faces.AddFace(verts[0], verts[1], verts[2], verts[3])

    r3mesh.Normals.ComputeNormals()
    attr = rhino3dm.ObjectAttributes()
    attr.Name = obj.name
    model.Objects.AddMesh(r3mesh, attr)
    ob_eval.to_mesh_clear()
    print(f'  Added Mesh: {obj.name}  faces={len(me.polygons)}')


def save(context, filepath, use_selection, mesh_fallback):
    if not RHINO3DM_AVAILABLE:
        print('ERROR: rhino3dm not available. Install with: pip install rhino3dm')
        return {'CANCELLED'}

    model = rhino3dm.File3dm()
    # Blender's internal coordinate system is metres; declare this so Rhino
    # interprets the exported values correctly regardless of the original file's
    # unit system.
    model.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters

    objects = context.selected_objects if use_selection else context.scene.objects

    for obj in objects:
        if obj.type in {'CAMERA', 'LIGHT', 'EMPTY', 'ARMATURE'}:
            continue
        print(f'Exporting: {obj.name}  type={obj.type}')

        if obj.type == 'SURFACE':
            export_nurbs_surface(model, obj)
        elif obj.type == 'CURVE':
            export_nurbs_curve(model, obj)
        elif obj.type == 'MESH' and mesh_fallback:
            export_mesh(model, obj)
        else:
            print(f'  Skipped (type={obj.type}  mesh_fallback={mesh_fallback})')

    model.Write(filepath, 7)
    print(f'Written: {filepath}')
    return {'FINISHED'}
