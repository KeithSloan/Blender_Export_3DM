# Session state — 2026-04-25

Snapshot of where the Blender_Export_3DM project stands at the end of the
v0.8.0 session.  Use this as the resume point in a new conversation.

## Current version

**v0.8.0** — shipped, deployed, committed, pushed.  Last two commits:

- `3c76058` — implementation of handling mirrors, still issue with two planes
  subject to further investigation
- `1e564c0` — docs: README — Mirror modifier (v0.8.0), HHH known issue,
  inspect_3dm.py

Working tree clean; `main` matches `origin/main`.

## What changed in v0.8.0

**Bug fixed:** SP objects with a Mirror modifier were exporting only the
original half — the mirrored half was silently dropped because SP's
geometry-node mesher writes a single patch's worth of CPs to mesh attributes,
and a Mirror modifier in the stack duplicates verts/faces but not the SP
attribute payload.  Effect: ship hulls (138 of 165 SP objects in the Pinnace
have an X-mirror) appeared as half-boats in the export.

**Implementation:** new helpers in `export_nurbs_3dm.py`:

- `_mirror_transforms(obj)` — enumerates `(Matrix, suffix)` pairs for every
  geometric copy the Mirror modifier stack would produce.  Honours
  `mirror_object` field, multiple stacked Mirror modifiers (Cartesian
  product), 1/2/3-axis combinations, and the disabled-modifier eyeball.
- `_orientation_flipped(mat)` — true when det < 0; signals that CP order
  must be reversed to keep surface normal / curve winding consistent.
- `_transform_pts3` / `_reverse_knots` / `_build_nurbs_surface` /
  `_emit_mirrored_surface` / `_emit_mirrored_curve` — per-type emit helpers.

The four affected SP export functions were refactored to use these helpers:
`export_sp_bspline_surface`, `export_sp_bezier_surface`,
`export_sp_bezier_curve_any_order`, `export_sp_flatpatch`.

SP `CURVE` and `COMPOUND` were intentionally left alone: their evaluated
edge mesh already contains the mirrored geometry produced by the modifier.

Naming convention for mirrored copies: original keeps its name; each
mirrored copy gets a suffix like `_mirrorX`, `_mirrorY`, `_mirrorZ`,
`_mirrorXY`, etc.

Docs are in `CLAUDE.md` under *Mirror modifier support (v0.8.0+)* and in
`README.md` under the Surface Psycho support section (blockquote note).

## Reference files for this session

- **Test artefact:** `Surface_Psycho_Files/SP - 50ft Pinnace Nurbs modelHHH.3dm`
  is the v0.8.0 export with Mirror handling enabled.
- **FreeCAD project:** `Surface_Psycho_Files/SP - 50ft Pinnace Nurbs modelHHH.FCStd`
  captures the import state for visual inspection.
- **Diagnostic script:** `inspect_3dm.py` lists all objects in a `.3dm` by
  bounding-box diagonal and flags closed degree-1 NurbsCurves (which
  FreeCAD fills as faces).  Run as
  `python3 inspect_3dm.py path/to/file.3dm`.

## Known issue — two oversized NURBS surfaces in Pinnace export

After v0.8.0, the Pinnace export still has two large flat-ish NURBS
surfaces dominating the FreeCAD view:

- `Plane.043` — ~23 × 30 units, 6×6 CPs, degree 5×5, X-mirror enabled
- `Plane.009` — ~22.6 long, 5×8 CPs, degree 4×7, X-mirror enabled

Investigation so far (see README "Known issue" section):

- They are real `BEZIER_SURFACE` SP objects in the source `.blend`, **not**
  FlatPatch boundaries that FreeCAD is filling.  `inspect_3dm.py` confirms
  zero closed degree-1 NurbsCurves in the export.
- Both are visible (`hidden_viewport=False`, `hidden_get=False`) in the
  source `.blend` — so the exporter is faithfully exporting them.
- Both have an X-mirror, so each appears as a pair in the v0.8.0 export
  (~46 × 30 effective span for `Plane.043`).
- The 138-mirror diagnostic confirmed these are part of the same set of
  surfaces affected by the v0.8.0 fix — they're now correctly mirrored,
  just inherently large.

Open question: what do `Plane.043` and `Plane.009` actually represent in
the source model?  Likely candidates: water plane, stage / scenery prop,
hangar floor, or modelling reference plane the original artist forgot to
hide.  Resolution requires opening the source `.blend` and inspecting the
two named objects.

## Linked-data duplicate question (not yet investigated)

The Blender diagnostic also reported **54 mesh datablocks shared by
multiple objects** — linked duplicates.  Concrete examples include
`Plane.131` shared by 8 objects, `Cube` shared by 4, and many port/
starboard pairs.

If SP's geometry-nodes mesher correctly bakes per-instance `matrix_world`
into world-space CPs, all 8 copies of `Plane.131` will export to their
distinct world positions.  If it bakes the master object's transform
instead, all 8 copies will stack on top of each other.

The v0.8.0 fix did **not** address this.  After resolving the Plane.043 /
Plane.009 question, run `inspect_3dm.py` and look for groups of surfaces
with identical bounding boxes — those would indicate the linked-data bug.

## New direction — KS_SurfacePsycho fork

The user reports SP's own STEP and IGES exporters also fail ("barf") on
the Pinnace file.  Plan: fork SurfacePsycho as **KS_SurfacePsycho** to
fix the STEP/IGES export path in addition to the 3DM route.

This is a new piece of work that warrants its own project / conversation.
Likely starting points for KS_SurfacePsycho:

- Source location: `/Users/ksloan/github/Blender_Addons/SurfacePsycho/`
  (per `CLAUDE.md` reference).
- Key files: `common/utils.py` (`sp_type_of_object`,
  `read_attribute_by_name`, enums) and
  `exporter/export_process_cad.py` (`NURBS_face_to_topods`,
  `bezier_face_to_topods`).
- Bezier-quest demo files: `/Users/ksloan/github/Bezier-quest/`.

Not in scope for the current Blender_Export_3DM repo — open a separate
project for it.

## Resume checklist for next session in this repo

When you're ready to come back to Blender_Export_3DM, the remaining
threads are:

1. **Plane.043 / Plane.009 mystery** — open source `.blend`, look at what
   those objects represent.  If they're scenery, decide on workflow
   (delete in source, or add a viewport-visibility-respecting export
   option, or an "exclude oversized" heuristic).
2. **Linked-data duplicates** — verify with `inspect_3dm.py` whether the
   54 sets actually stack at the master's position, and if so, add
   per-instance `matrix_world` handling in the surface exporters.
3. **Native Blender SURFACE / CURVE Mirror handling** — the v0.8.0 fix
   only covers SP types.  Native `obj.type == 'SURFACE'` and
   `obj.type == 'CURVE'` objects with Mirror modifiers are still
   single-half exports (low priority — uncommon in practice, easy to
   fix with the same helper pattern).
4. **Round-trip test for v0.8.0** — re-run
   `utilities/batch_blend_compare.py` and friends to confirm the new
   Mirror code path doesn't regress the existing test suite.
