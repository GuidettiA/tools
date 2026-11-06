"""
Crée un rig caméra Redshift : caméra sur trajectoire circulaire, cible et focus.

Hiérarchie générée sous un null parent portant le nom saisi :
  - <nom>        : RS Camera alignée sur la spline (Align to Spline) et
                   orientée vers la cible (Constraint Aim + Up)
  - Pan_<nom>    : spline cercle (rayon 450, plan XZ) servant de trajectoire
  - Cible_<nom>  : null cible, avec Up_<nom> et Focus_<nom> en enfants

Utilisation :
  1. Lancer le script
  2. Saisir le nom de la caméra (par défaut "Camera")
"""

import c4d

def main():
    # --- NOM DE LA CAMÉRA ---
    default_name = "Camera"
    cam_name = c4d.gui.InputDialog("Nom de la caméra :", default_name)
    if not cam_name:
        cam_name = default_name

    # --- CRÉATION DES OBJETS ---
    cam = c4d.BaseObject(1057516)
    cam.SetName(cam_name)
    cam[500] = 105

    pan_spline = c4d.BaseObject(c4d.Osplinecircle)
    pan_spline.SetName("Pan_" + cam_name)
    pan_spline[c4d.PRIM_CIRCLE_RADIUS] = 450
    pan_spline[c4d.PRIM_PLANE] = c4d.PRIM_PLANE_XZ

    cible_cam = c4d.BaseObject(c4d.Onull)
    cible_cam.SetName("Cible_" + cam_name)

    null_up = c4d.BaseObject(c4d.Onull)
    null_up.SetName("Up_" + cam_name)
    null_up[c4d.ID_BASEOBJECT_REL_POSITION] = c4d.Vector(0, 30, 0)

    null_focus = c4d.BaseObject(c4d.Onull)
    null_focus.SetName("Focus_" + cam_name)
    null_focus.InsertUnder(cible_cam)
    null_up.InsertUnder(cible_cam)

    # --- NULL PARENT ---
    null_parent = c4d.BaseObject(c4d.Onull)
    null_parent.SetName(cam_name)

    # --- INSERTION (parent en premier, enfants ensuite) ---
    doc.InsertObject(null_parent)
    cible_cam.InsertUnder(null_parent)
    pan_spline.InsertUnder(null_parent)
    cam.InsertUnder(null_parent)

    # --- CONFIGURATION FOCUS CAMÉRA ---
    cam[1130] = null_focus
    cam[1101] = null_focus
    cam[1113] = null_focus

    # --- CONFIGURATION DES TAGS ---
    # Align to Spline
    align_tag = cam.MakeTag(5699)
    if align_tag:
        align_tag[1001] = pan_spline
        pd_align = c4d.PriorityData()
        pd_align.SetPriorityValue(c4d.PRIORITYVALUE_MODE, c4d.CYCLE_INITIAL)
        pd_align.SetPriorityValue(c4d.PRIORITYVALUE_PRIORITY, 1)
        align_tag[c4d.EXPRESSION_PRIORITY] = pd_align

    # Constraint Tag
    constraint_tag = cam.MakeTag(1019364)
    if constraint_tag:
        constraint_tag.SetName("Constraint")
        pd_const = c4d.PriorityData()
        pd_const.SetPriorityValue(c4d.PRIORITYVALUE_MODE, c4d.CYCLE_ANIMATION)
        pd_const.SetPriorityValue(c4d.PRIORITYVALUE_PRIORITY, -1)
        constraint_tag[c4d.EXPRESSION_PRIORITY] = pd_const
        constraint_tag[c4d.ID_CA_CONSTRAINT_TAG_AIM] = True
        constraint_tag[c4d.ID_CA_CONSTRAINT_TAG_UP] = True
        constraint_tag[50001] = 0
        constraint_tag.Message(c4d.MSG_UPDATE)
        constraint_tag[20001] = cible_cam
        constraint_tag[50005] = null_up
        constraint_tag[40001] = null_up

    c4d.EventAdd()

if __name__ == '__main__':
    main()