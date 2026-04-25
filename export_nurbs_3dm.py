import bpy
import numpy as np
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


# ---------------------------------------------------------------------------
# Surface Psycho (SP) support
# ---------------------------------------------------------------------------
# SP stores NURBS/Bezier surface data as geometry-node output attributes on
# MESH objects rather than using Blender's native SURFACE type.  The object
# type is identified by the name of the last NODES modifier whose node group
# matches one of the SP mesher node group names below.

_SP_MESHER_NAMES = {
    'BSPLINE_SURFACE':        'SP - NURBS Patch Meshing',
    'BEZIER_SURFACE':         'SP - Bezier Patch Meshing',
    'PLANE':                  'SP - FlatPatch Meshing',
    'CYLINDER':               'SP - Cylindrical Meshing',
    'CONE':                   'SP - Conical Meshing',
    'SPHERE':                 'SP - Spherical Meshing',
    'TORUS':                  'SP - Toroidal Meshing',
    'SURFACE_OF_REVOLUTION':  'SP - Surface of Revolution Meshing',
    'SURFACE_OF_EXTRUSION':   'SP - Surface of Extrusion Meshing',
    'CURVE':                  'SP - Curve Meshing',
    'COMPOUND':               'SP - Compound Meshing',
    'BEZIER_CURVE_ANY_ORDER': 'SP -  Bezier Curve Any Order',
}


def _sp_type_of_object(obj):
    """Return the SP surface-type key string, or None if not an SP object."""
    if obj.type != 'MESH':
        return None
    for m in reversed(obj.modifiers):
        if m.type == 'NODES' and m.node_group:
            ng = m.node_group.name
            # SP node groups are named "SP - Foo Meshing" or "SP - Foo Meshing.001"
            base = ng[:-4] if (len(ng) > 4 and ng[-4] == '.') else ng
            for sp_type, mesher in _SP_MESHER_NAMES.items():
                if base == mesher or ng == mesher:
                    return sp_type
    return None


def _sp_read_attr(ob, name, count=None):
    """Read a mesh geometry-node attribute into a numpy array."""
    att = ob.data.attributes[name]
    n = len(att.data)
    dt = att.data_type
    if dt == 'FLOAT_VECTOR':
        buf = np.empty(3 * n, dtype=float)
        att.data.foreach_get('vector', buf)
        arr = buf.reshape((-1, 3))
    elif dt == 'FLOAT':
        arr = np.empty(n, dtype=float)
        att.data.foreach_get('value', arr)
    elif dt == 'INT':
        buf = np.empty(n, dtype=float)
        att.data.foreach_get('value', buf)
        arr = buf.astype(int)
    elif dt == 'BOOLEAN':
        arr = np.empty(n, dtype=bool)
        att.data.foreach_get('value', arr)
    elif dt == 'FLOAT2':
        buf = np.empty(2 * n, dtype=float)
        att.data.foreach_get('vector', buf)
        arr = buf.reshape((-1, 2))
    else:
        raise ValueError(f'Unknown SP attribute type: {dt}')
    return arr if count is None else arr[:count]


def _sp_knots_to_rhino(knots, mults):
    """Expand distinct knots + multiplicities into rhino3dm knot-vector format.

    rhino3dm omits the outermost (first and last) repeated knot values that
    standard NURBS theory requires, so this expansion drops them.
    """
    full = []
    for k, m in zip(knots, mults):
        full.extend([float(k)] * int(m))
    return full[1:-1]


def export_sp_bspline_surface(model, obj, depsgraph):
    """Export a Surface Psycho NURBS patch (B-spline surface) to rhino3dm."""
    ob = obj.evaluated_get(depsgraph)
    try:
        u_count, v_count = _sp_read_attr(ob, 'CP_count', 2).astype(int)
        total = int(u_count) * int(v_count)
        points = _sp_read_attr(ob, 'CP_NURBS_surf', total)
        degree_u, degree_v = _sp_read_attr(ob, 'Degrees', 2).astype(int)
    except KeyError as e:
        print(f'  Skipped SP B-spline surface {obj.name!r}: missing attribute {e}')
        return

    try:
        ip = _sp_read_attr(ob, 'IsPeriodic', 2)
        isperiodic_u, isperiodic_v = bool(ip[0]), bool(ip[1])
    except KeyError:
        isperiodic_u = isperiodic_v = False

    try:
        weights = _sp_read_attr(ob, 'Weights', total)
        is_rational = bool(np.any(weights != 1.0))
    except KeyError:
        weights = np.ones(total, dtype=float)
        is_rational = False

    u_count = int(u_count)
    v_count = int(v_count)
    degree_u = int(degree_u)
    degree_v = int(degree_v)

    # SP stores CPs as flat array in V-major order (vi outer, ui inner).
    # Reshape to (v_count, u_count, 3) then transpose to (u_count, v_count, 3)
    # so pts[ui, vi] and wts[ui, vi] index correctly for rhino3dm.
    pts = points.reshape(v_count, u_count, 3).transpose(1, 0, 2)
    wts = weights.reshape(v_count, u_count).transpose()

    # Periodic surfaces: duplicate the first row/column to close the loop
    if isperiodic_u:
        pts = np.append(pts, pts[0:1, :, :], axis=0)
        wts = np.append(wts, wts[0:1, :], axis=0)
        u_count += 1
    if isperiodic_v:
        pts = np.append(pts, pts[:, 0:1, :], axis=1)
        wts = np.append(wts, wts[:, 0:1], axis=1)
        v_count += 1

    order_u = degree_u + 1
    order_v = degree_v + 1

    try:
        umult_raw = _sp_read_attr(ob, 'Multiplicity U').astype(int)
        u_len = int(np.sum(umult_raw > 0))
        uknots = _sp_read_attr(ob, 'Knot U', u_len)
        umult = umult_raw[:u_len]

        vmult_raw = _sp_read_attr(ob, 'Multiplicity V').astype(int)
        v_len = int(np.sum(vmult_raw > 0))
        vknots = _sp_read_attr(ob, 'Knot V', v_len)
        vmult = vmult_raw[:v_len]
    except KeyError as e:
        print(f'  Skipped SP B-spline surface {obj.name!r}: missing knot attribute {e}')
        return

    ku = _sp_knots_to_rhino(uknots, umult)
    kv = _sp_knots_to_rhino(vknots, vmult)

    exp_ku = u_count + order_u - 2
    exp_kv = v_count + order_v - 2

    print(f'  SP B-spline surface: {u_count}x{v_count} CVs  degree {degree_u}x{degree_v}  rational={is_rational}')

    if len(ku) != exp_ku or len(kv) != exp_kv:
        print(f'  Knot length mismatch U:{len(ku)}≠{exp_ku}  V:{len(kv)}≠{exp_kv} — skipped')
        return

    srf = rhino3dm.NurbsSurface.Create(3, is_rational, order_u, order_v, u_count, v_count)

    for vi in range(v_count):
        for ui in range(u_count):
            p = pts[ui, vi]
            w = float(wts[ui, vi])
            srf.Points[ui, vi] = rhino3dm.Point4d(
                float(p[0]) * w, float(p[1]) * w, float(p[2]) * w, w)

    for i, k in enumerate(ku):
        srf.KnotsU[i] = k
    for i, k in enumerate(kv):
        srf.KnotsV[i] = k

    attr = rhino3dm.ObjectAttributes()
    attr.Name = obj.name
    model.Objects.AddSurface(srf, attr)
    print(f'  Added SP B-spline surface: {obj.name!r}')


def export_sp_bezier_surface(model, obj, depsgraph):
    """Export a Surface Psycho Bezier patch to rhino3dm as a NURBS surface."""
    ob = obj.evaluated_get(depsgraph)
    try:
        u_count, v_count = _sp_read_attr(ob, 'CP_count', 2).astype(int)
        u_count = int(u_count)
        v_count = int(v_count)
        total = u_count * v_count
        points = _sp_read_attr(ob, 'CP_any_order_surf', total)
    except KeyError as e:
        print(f'  Skipped SP Bezier surface {obj.name!r}: missing attribute {e}')
        return

    # A Bezier patch of degree (n-1) x (m-1) is represented as NURBS with
    # order = count (all knots clamped to 0 or 1, multiplicity = degree).
    degree_u = u_count - 1
    degree_v = v_count - 1
    order_u = u_count
    order_v = v_count

    print(f'  SP Bezier surface: {u_count}x{v_count} CVs  degree {degree_u}x{degree_v}')

    srf = rhino3dm.NurbsSurface.Create(3, False, order_u, order_v, u_count, v_count)

    # SP stores (vi outer, ui inner): index = vi * u_count + ui
    for vi in range(v_count):
        for ui in range(u_count):
            p = points[vi * u_count + ui]
            srf.Points[ui, vi] = rhino3dm.Point4d(float(p[0]), float(p[1]), float(p[2]), 1.0)

    # rhino3dm Bezier knot vector: degree zeros followed by degree ones
    # (full clamped knot [0]*order + [1]*order minus the outermost entries)
    ku = [0.0] * degree_u + [1.0] * degree_u
    kv = [0.0] * degree_v + [1.0] * degree_v

    for i, k in enumerate(ku):
        srf.KnotsU[i] = k
    for i, k in enumerate(kv):
        srf.KnotsV[i] = k

    attr = rhino3dm.ObjectAttributes()
    attr.Name = obj.name
    model.Objects.AddSurface(srf, attr)
    print(f'  Added SP Bezier surface (as NURBS): {obj.name!r}')


def _edge_mesh_to_chains(me, mat):
    """Return a list of ordered world-space point lists from an edge-only mesh.

    Traces connected components of the edge graph.  Each component is returned
    as an ordered list of mathutils.Vector (world space).  Open chains start
    from a degree-1 vertex; closed loops start from vertex 0 of that component.
    """
    n_verts = len(me.vertices)
    n_edges = len(me.edges)
    if n_verts == 0 or n_edges == 0:
        return []

    verts_local = np.empty(n_verts * 3, float)
    me.vertices.foreach_get('co', verts_local)
    verts_local = verts_local.reshape(-1, 3)

    edge_arr = np.empty(n_edges * 2, int)
    me.edges.foreach_get('vertices', edge_arr)
    edge_arr = edge_arr.reshape(-1, 2)

    adj = {i: [] for i in range(n_verts)}
    for a, b in edge_arr:
        adj[a].append(b)
        adj[b].append(a)

    visited = set()
    chains = []

    for seed in range(n_verts):
        if seed in visited:
            continue

        # Collect all vertices in this connected component
        component = set()
        stack = [seed]
        while stack:
            v = stack.pop()
            if v in component:
                continue
            component.add(v)
            stack.extend(adj[v])

        visited |= component

        # Find an endpoint (degree 1) to start; if none, it's a closed loop
        start = next((v for v in component if len(adj[v]) == 1), next(iter(component)))
        is_closed = all(len(adj[v]) == 2 for v in component)

        chain = [start]
        prev = -1
        while True:
            curr = chain[-1]
            nexts = [v for v in adj[curr] if v != prev]
            if not nexts:
                break
            nxt = nexts[0]
            if nxt == start and len(chain) > 1:
                break
            chain.append(nxt)
            prev = curr

        pts = [mat @ Vector(verts_local[vi]) for vi in chain]
        if is_closed:
            pts.append(pts[0])
        chains.append(pts)

    return chains


def _chains_to_nurbs_curves(model, chains, name):
    """Add each chain as a degree-1 closed or open NurbsCurve to *model*."""
    for idx, pts in enumerate(chains):
        n = len(pts)
        if n < 2:
            continue

        is_closed = pts[0] == pts[-1] if n > 1 else False
        knot_count = n - 1  # rhino3dm degree-1: pointCount + order - 2 = n + 2 - 2 = n
        nc = rhino3dm.NurbsCurve(3, False, 2, n)
        for i, pt in enumerate(pts):
            nc.Points[i] = rhino3dm.Point4d(pt.x, pt.y, pt.z, 1.0)
        for i in range(knot_count):
            nc.Knots[i] = float(i)

        attr = rhino3dm.ObjectAttributes()
        attr.Name = name if len(chains) == 1 else f'{name}.{idx:03d}'
        model.Objects.AddCurve(nc, attr)

    return len(chains)


def export_sp_curve(model, obj, depsgraph):
    """Export a Surface Psycho Curve (SP - Curve Meshing) as NurbsCurve polyline(s).

    SP Curve objects store their geometry as an evaluated edge mesh (no face
    polygons).  The mesh vertices are in local object space; matrix_world is
    applied to convert to world space.  Each connected chain of edges becomes
    a separate degree-1 NurbsCurve.

    Note: the true NURBS control data (CP_curve, Degree, Knot attributes) is
    not present in the evaluated mesh for these objects — the exported curve is
    a polyline through the evaluated mesh vertices, not the original NURBS.
    """
    ob = obj.evaluated_get(depsgraph)
    chains = _edge_mesh_to_chains(ob.data, obj.matrix_world)
    if not chains:
        print(f'  SP Curve {obj.name!r}: no edge geometry — skipped')
        return
    n = _chains_to_nurbs_curves(model, chains, obj.name)
    total_pts = sum(len(c) for c in chains)
    print(f'  Added SP Curve: {obj.name!r}  ({n} chain(s), {total_pts} pts total)')


def export_sp_compound(model, obj, depsgraph):
    """Export a Surface Psycho Compound (SP - Compound Meshing) as NurbsCurve polyline(s).

    SP Compound objects are collections of curve segments stored as an edge
    mesh, similar to Curve objects but potentially containing multiple
    disconnected chains.  Each connected chain of edges becomes a separate
    degree-1 NurbsCurve.
    """
    ob = obj.evaluated_get(depsgraph)
    chains = _edge_mesh_to_chains(ob.data, obj.matrix_world)
    if not chains:
        print(f'  SP Compound {obj.name!r}: no edge geometry — skipped')
        return
    n = _chains_to_nurbs_curves(model, chains, obj.name)
    total_pts = sum(len(c) for c in chains)
    print(f'  Added SP Compound: {obj.name!r}  ({n} chain(s), {total_pts} pts total)')


def export_sp_bezier_curve_any_order(model, obj, depsgraph):
    """Export a Surface Psycho Bezier Curve Any Order as a NurbsCurve.

    Reads CP_count (index 0) and CP_any_order_curve from the evaluated mesh.
    Represents the curve as a single clamped Bezier of degree = cp_count - 1
    with knot vector [0]*degree + [1]*degree (rhino form, outermost entries
    omitted).  Control points are in world space (same as SP surface types);
    matrix_world is NOT applied.
    """
    ob = obj.evaluated_get(depsgraph)
    me = ob.data

    if 'CP_any_order_curve' not in me.attributes or 'CP_count' not in me.attributes:
        print(f'  SP BezierCurveAnyOrder {obj.name!r}: missing attributes — skipped')
        return

    cp_count_data = np.empty(len(me.vertices), dtype=float)
    me.attributes['CP_count'].data.foreach_get('value', cp_count_data)
    cp_count = int(cp_count_data[0])

    if cp_count < 2:
        print(f'  SP BezierCurveAnyOrder {obj.name!r}: cp_count={cp_count} < 2 — skipped')
        return

    cp_data = np.empty(len(me.vertices) * 3, float)
    me.attributes['CP_any_order_curve'].data.foreach_get('vector', cp_data)
    cps = cp_data.reshape(-1, 3)[:cp_count]

    degree = cp_count - 1
    nc = rhino3dm.NurbsCurve(3, False, degree + 1, cp_count)

    for i, pt in enumerate(cps):
        nc.Points[i] = rhino3dm.Point4d(float(pt[0]), float(pt[1]), float(pt[2]), 1.0)

    for i in range(degree):
        nc.Knots[i] = 0.0
    for i in range(degree):
        nc.Knots[degree + i] = 1.0

    attr = rhino3dm.ObjectAttributes()
    attr.Name = obj.name
    model.Objects.AddCurve(nc, attr)
    print(f'  Added SP BezierCurveAnyOrder (degree {degree}): {obj.name!r}')


def export_sp_flatpatch(model, obj, depsgraph):
    """Export a Surface Psycho FlatPatch boundary as a closed NurbsCurve polyline.

    SP FlatPatch stores its boundary as degree-1 segments in the CP_planar
    attribute (world space), but only the explicit segments — the connecting
    edges between them are implicit.  The easiest source of the complete,
    connected boundary polygon is the evaluated mesh polygon, which the GN
    mesher builds correctly.  Mesh vertices are in local (object) space so
    matrix_world is applied to convert to world space.

    Each polygon in the mesh is exported as a separate closed NurbsCurve.
    SP FlatPatch meshes typically have two polygons (front and back faces);
    only polygon 0 (index 0) is exported to avoid duplicates.
    """
    ob = obj.evaluated_get(depsgraph)
    me = ob.data

    if not me.polygons:
        print(f'  SP FlatPatch {obj.name!r}: no polygons — skipped')
        return

    mat = obj.matrix_world
    verts_local = np.empty(len(me.vertices) * 3, float)
    me.vertices.foreach_get('co', verts_local)
    verts_local = verts_local.reshape(-1, 3)

    # Export only the first polygon to avoid duplicating the mirrored back face
    poly = me.polygons[0]
    boundary = [mat @ Vector(verts_local[vi]) for vi in poly.vertices]
    n = len(boundary)

    # Closed degree-1 NURBS polyline: n+1 points (last = first), n+1 knots
    nc = rhino3dm.NurbsCurve(3, False, 2, n + 1)
    for i, pt in enumerate(boundary):
        nc.Points[i] = rhino3dm.Point4d(pt.x, pt.y, pt.z, 1.0)
    nc.Points[n] = rhino3dm.Point4d(boundary[0].x, boundary[0].y, boundary[0].z, 1.0)
    for i in range(n + 1):
        nc.Knots[i] = float(i)

    attr = rhino3dm.ObjectAttributes()
    attr.Name = obj.name
    model.Objects.AddCurve(nc, attr)
    print(f'  Added SP FlatPatch boundary: {obj.name!r}  ({n} vertices)')


def save(context, filepath, use_selection, mesh_fallback, export_flatpatch=True):
    if not RHINO3DM_AVAILABLE:
        print('ERROR: rhino3dm not available. Install with: pip install rhino3dm')
        return {'CANCELLED'}

    model = rhino3dm.File3dm()
    # Blender's internal coordinate system is metres; declare this so Rhino
    # interprets the exported values correctly regardless of the original file's
    # unit system.
    model.Settings.ModelUnitSystem = rhino3dm.UnitSystem.Meters

    depsgraph = context.evaluated_depsgraph_get()
    objects = context.selected_objects if use_selection else context.scene.objects

    for obj in objects:
        if obj.type in {'CAMERA', 'LIGHT', 'EMPTY', 'ARMATURE'}:
            continue
        print(f'Exporting: {obj.name}  type={obj.type}')

        if obj.type == 'SURFACE':
            export_nurbs_surface(model, obj)
        elif obj.type == 'CURVE':
            export_nurbs_curve(model, obj)
        elif obj.type == 'MESH':
            sp_type = _sp_type_of_object(obj)
            if sp_type == 'BSPLINE_SURFACE':
                export_sp_bspline_surface(model, obj, depsgraph)
            elif sp_type == 'BEZIER_SURFACE':
                export_sp_bezier_surface(model, obj, depsgraph)
            elif sp_type == 'PLANE':
                if export_flatpatch:
                    export_sp_flatpatch(model, obj, depsgraph)
                else:
                    print(f'  SP FlatPatch {obj.name!r}: skipped (export_flatpatch=False)')
            elif sp_type == 'CURVE':
                export_sp_curve(model, obj, depsgraph)
            elif sp_type == 'COMPOUND':
                export_sp_compound(model, obj, depsgraph)
            elif sp_type == 'BEZIER_CURVE_ANY_ORDER':
                export_sp_bezier_curve_any_order(model, obj, depsgraph)
            elif sp_type is not None:
                print(f'  SP type {sp_type!r} not yet supported for 3DM export — skipped')
            elif mesh_fallback:
                export_mesh(model, obj)
            else:
                print(f'  Skipped (type=MESH  mesh_fallback={mesh_fallback})')
        else:
            print(f'  Skipped (type={obj.type}  mesh_fallback={mesh_fallback})')

    model.Write(filepath, 7)
    print(f'Written: {filepath}')
    return {'FINISHED'}
