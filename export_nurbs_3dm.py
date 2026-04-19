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
    mat = obj.matrix_world
    for spline in obj.data.splines:
        if spline.type != 'NURBS':
            print(f'  Skipping non-NURBS spline type: {spline.type}')
            continue

        cu = spline.point_count_u
        cv = spline.point_count_v
        order_u = spline.order_u
        order_v = spline.order_v
        is_rational = any(p.co.w != 1.0 for p in spline.points)

        print(f'  NURBS surface: {cu}x{cv} CVs  order {order_u}x{order_v}  rational={is_rational}')
        print(f'  cyclic u={spline.use_cyclic_u} v={spline.use_cyclic_v}')
        print(f'  endpoint u={spline.use_endpoint_u} v={spline.use_endpoint_v}')

        srf = rhino3dm.NurbsSurface.Create(3, is_rational, order_u, order_v, cu, cv)

        # Control points - Blender stores row-major with U varying fastest
        for vi in range(cv):
            for ui in range(cu):
                p = spline.points[vi * cu + ui]
                w = p.co.w
                world = mat @ Vector((p.co.x, p.co.y, p.co.z))
                # rhino3dm Point4d uses homogeneous form (x*w, y*w, z*w, w)
                srf.Points[ui, vi] = rhino3dm.Point4d(
                    world.x * w, world.y * w, world.z * w, w)

        # Knots - force clamped (endpoint=True) for OCCT compatibility
        # Blender's non-endpoint NURBS uses uniform knots which OCCT can't
        # represent as a non-periodic surface
        ku = make_knots(cu, order_u, use_endpoint=True, use_cyclic=spline.use_cyclic_u)
        kv = make_knots(cv, order_v, use_endpoint=True, use_cyclic=spline.use_cyclic_v)
        print(f'  knots U({len(ku)}): {ku}')
        print(f'  knots V({len(kv)}): {kv}')

        expected_u = cu + order_u - 2
        expected_v = cv + order_v - 2
        if len(ku) != expected_u:
            print(f'  WARNING: knot U length {len(ku)} expected {expected_u}')
        if len(kv) != expected_v:
            print(f'  WARNING: knot V length {len(kv)} expected {expected_v}')

        for i, k in enumerate(ku):
            srf.KnotsU[i] = k
        for i, k in enumerate(kv):
            srf.KnotsV[i] = k

        attr = rhino3dm.ObjectAttributes()
        attr.Name = obj.name
        model.Objects.AddSurface(srf, attr)
        print(f'  Added NurbsSurface: {obj.name}')


def export_nurbs_curve(model, obj):
    mat = obj.matrix_world
    for spline in obj.data.splines:
        if spline.type != 'NURBS':
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
