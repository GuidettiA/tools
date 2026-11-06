"""
Bake l'animation de la caméra sélectionnée sur une copie de l'objet.

Pour chaque frame de la plage du document, la position, la rotation et
l'échelle (ainsi que la distance de focus pour une RS Camera avec objet de
focus) sont enregistrées puis posées en clés sur une copie "<nom>_baked".
Les tags de contrainte et Align to Spline sont retirés de la copie ;
l'original reste intact.

Utilisation :
  1. Sélectionner la caméra à baker
  2. Lancer le script
"""

import c4d

def get_or_create_track(obj, desc_id):
    track = obj.FindCTrack(desc_id)
    if track is None:
        track = c4d.CTrack(obj, desc_id)
        obj.InsertTrackSorted(track)
    return track

def set_key(curve, time, value):
    key_dict = curve.AddKey(time)
    if key_dict:
        key_dict["key"].SetValue(curve, value)

def main():
    doc = c4d.documents.GetActiveDocument()
    obj = doc.GetActiveObject()

    if obj is None:
        c4d.gui.MessageDialog("Aucun objet sélectionné.")
        return

    fps = doc.GetFps()
    start_frame = doc.GetMinTime().GetFrame(fps)
    end_frame   = doc.GetMaxTime().GetFrame(fps)

    # ── Se place à la première frame avant de commencer ─────────────────
    start_time = doc.GetMinTime()
    doc.SetTime(start_time)
    doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    c4d.EventAdd()

    doc.StartUndo()

    # ── Duplication de l'objet (avec tous ses tags) ─────────────────────
    bake_obj = obj.GetClone()
    bake_obj.SetName(obj.GetName() + "_baked")
    doc.InsertObject(bake_obj, obj.GetUp(), obj)
    doc.AddUndo(c4d.UNDOTYPE_NEW, bake_obj)

    # ── Collecte des valeurs réelles depuis l'objet original ────────────

    RS_CAMERA_TYPE       = 1057516
    RS_FOCUS_OBJECT_ID   = 1130
    RS_FOCUS_DISTANCE_ID = 1010
    dof_target = obj[RS_FOCUS_OBJECT_ID] if obj.GetType() == RS_CAMERA_TYPE else None

    baked = []
    for frame in range(start_frame, end_frame + 1):
        time = c4d.BaseTime(frame, fps)
        doc.SetTime(time)
        doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)

        entry = {
            "time":  time,
            "pos":   obj.GetRelPos(),
            "rot":   obj.GetRelRot(),
            "scale": obj.GetRelScale(),
        }

        # Calcule la focus distance = distance entre caméra et objet cible
        if dof_target is not None:
            cam_pos    = obj.GetMg().off
            target_pos = dof_target.GetMg().off
            entry["focus"] = (target_pos - cam_pos).GetLength()

        baked.append(entry)

    # ── Création des tracks et pose des clefs sur la copie ──────────────
    pos_ids = [
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION, c4d.DTYPE_VECTOR, 0),
                   c4d.DescLevel(c4d.VECTOR_X, c4d.DTYPE_REAL, 0)),
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION, c4d.DTYPE_VECTOR, 0),
                   c4d.DescLevel(c4d.VECTOR_Y, c4d.DTYPE_REAL, 0)),
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_POSITION, c4d.DTYPE_VECTOR, 0),
                   c4d.DescLevel(c4d.VECTOR_Z, c4d.DTYPE_REAL, 0)),
    ]
    rot_ids = [
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_ROTATION, c4d.DTYPE_VECTOR, 0),
                   c4d.DescLevel(c4d.VECTOR_X, c4d.DTYPE_REAL, 0)),
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_ROTATION, c4d.DTYPE_VECTOR, 0),
                   c4d.DescLevel(c4d.VECTOR_Y, c4d.DTYPE_REAL, 0)),
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_ROTATION, c4d.DTYPE_VECTOR, 0),
                   c4d.DescLevel(c4d.VECTOR_Z, c4d.DTYPE_REAL, 0)),
    ]
    scale_ids = [
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_SCALE, c4d.DTYPE_VECTOR, 0),
                   c4d.DescLevel(c4d.VECTOR_X, c4d.DTYPE_REAL, 0)),
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_SCALE, c4d.DTYPE_VECTOR, 0),
                   c4d.DescLevel(c4d.VECTOR_Y, c4d.DTYPE_REAL, 0)),
        c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_SCALE, c4d.DTYPE_VECTOR, 0),
                   c4d.DescLevel(c4d.VECTOR_Z, c4d.DTYPE_REAL, 0)),
    ]

    doc.AddUndo(c4d.UNDOTYPE_CHANGE, bake_obj)

    pos_curves   = [get_or_create_track(bake_obj, d).GetCurve() for d in pos_ids]
    rot_curves   = [get_or_create_track(bake_obj, d).GetCurve() for d in rot_ids]
    scale_curves = [get_or_create_track(bake_obj, d).GetCurve() for d in scale_ids]

    # Track Focus Distance
    focus_curve = None
    if dof_target is not None:
        focus_id = c4d.DescID(c4d.DescLevel(RS_FOCUS_DISTANCE_ID, c4d.DTYPE_REAL, 0))
        focus_curve = get_or_create_track(bake_obj, focus_id).GetCurve()

    for data in baked:
        t     = data["time"]
        pos   = data["pos"]
        rot   = data["rot"]
        scale = data["scale"]

        set_key(pos_curves[0], t, pos.x)
        set_key(pos_curves[1], t, pos.y)
        set_key(pos_curves[2], t, pos.z)

        set_key(rot_curves[0], t, rot.x)
        set_key(rot_curves[1], t, rot.y)
        set_key(rot_curves[2], t, rot.z)

        set_key(scale_curves[0], t, scale.x)
        set_key(scale_curves[1], t, scale.y)
        set_key(scale_curves[2], t, scale.z)

        if focus_curve is not None and "focus" in data:
            set_key(focus_curve, t, data["focus"])

    # ── Suppression des tags de contrainte sur la copie ─────────────────
    CONSTRAINT_TAG_ID = 1019364
    tag = bake_obj.GetFirstTag()
    while tag:
        next_tag = tag.GetNext()
        tag_type = tag.GetType()
        tag_type_name = tag.GetTypeName().lower()
        ALIGN_TO_SPLINE_TAG_ID = 5699
        if tag_type == CONSTRAINT_TAG_ID or tag_type == ALIGN_TO_SPLINE_TAG_ID or "constraint" in tag_type_name:
            doc.AddUndo(c4d.UNDOTYPE_DELETE, tag)
            tag.Remove()
        tag = next_tag

    # ── Suppression de l'objet Focus sur la copie ──────────────────────
    if dof_target is not None:
        bake_obj[RS_FOCUS_OBJECT_ID] = None

    doc.EndUndo()
    c4d.EventAdd()

    total = end_frame - start_frame + 1
    c4d.gui.MessageDialog(
        f"Bake terminé !\n{total} frames bakées.\n"
        f"Original intact : '{obj.GetName()}'\n"
        f"Copie bakée : '{bake_obj.GetName()}'"
    )

if __name__ == '__main__':
    main()