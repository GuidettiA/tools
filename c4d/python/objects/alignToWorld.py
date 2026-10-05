"""
Aligne l'axe des objets sélectionnés sur le repère monde.

Seul l'axe change d'orientation : la géométrie (points, tangentes) et les
enfants conservent leur position monde d'origine.

Utilisation :
  1. Sélectionner un ou plusieurs objets
  2. Lancer le script
"""

import c4d


# ─── Utilitaires ─────────────────────────────────────────────────────────────

def collect_children(op: c4d.BaseObject, out: list) -> None:
    """Collecte récursivement tous les descendants d'un objet."""
    child = op.GetDown()
    while child:
        out.append(child)
        collect_children(child, out)
        child = child.GetNext()


def align_axis_to_world(op: c4d.BaseObject, doc: c4d.documents.BaseDocument) -> None:
    """
    Aligne l'axe local de `op` sur le repère monde :
      • Rotation  → identité (axes X/Y/Z parallèles au monde)
      • Position  → conservée (même position monde qu'avant)
      • Points    → recalculés pour rester au même endroit dans l'espace monde
      • Tangentes → transformées en vecteurs directionnels (rotation seule)
      • Enfants   → leur matrice monde est restaurée (ils ne bougent pas)
    """

    # 1. Sauvegarder la matrice monde actuelle de l'objet
    mg_old = op.GetMg()

    # 2. Sauvegarder les matrices monde de tous les enfants
    children: list = []
    collect_children(op, children)
    children_mg = {child: child.GetMg() for child in children}

    # 3. Calculer les positions monde de tous les points (si objet géométrique)
    points_world = []
    if op.IsInstanceOf(c4d.Opoint):
        for i in range(op.GetPointCount()):
            points_world.append(mg_old * op.GetPoint(i))

    # 4. Construire la nouvelle matrice monde :
    #    • Translation = ancienne position monde
    #    • Rotation    = identité (axes alignés sur le monde)
    mg_new = c4d.Matrix()       # identité : v1=(1,0,0) v2=(0,1,0) v3=(0,0,1)
    mg_new.off = mg_old.off     # on conserve la position monde
    op.SetMg(mg_new)

    # 5. Remettre les points à leur position monde d'origine
    if points_world:
        # ~mg_new est calculé directement : pas besoin de repasser par op.GetMg()
        mg_new_inv = ~mg_new
        for i, p_world in enumerate(points_world):
            op.SetPoint(i, mg_new_inv * p_world)

        # 5b. Recalculer les tangentes Bézier (splines uniquement)
        #
        #     Les tangentes sont des vecteurs directionnels (pas des positions) :
        #     elles ne subissent PAS de translation, uniquement rotation + scale.
        #     Formule générale : t_new = R_new_inv * R_old * t_old
        #     Comme R_new est l'identité, R_new_inv = I, donc : t_new = R_old * t_old
        if op.IsInstanceOf(c4d.Ospline):
            # Matrice rotation/scale de l'ancienne orientation (off=0 → pas de translation)
            R_old = c4d.Matrix(c4d.Vector(0), mg_old.v1, mg_old.v2, mg_old.v3)
            for i in range(op.GetPointCount()):
                tangent = op.GetTangent(i)
                op.SetTangent(i, R_old * tangent["vl"], R_old * tangent["vr"])

        op.Message(c4d.MSG_UPDATE)

    # 6. Restaurer les matrices monde des enfants (ils ne doivent pas bouger)
    for child in children:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, child)
        child.SetMg(children_mg[child])


# ─── Point d'entrée ──────────────────────────────────────────────────────────

def main() -> None:
    doc = c4d.documents.GetActiveDocument()
    objects = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN)

    if not objects:
        c4d.gui.MessageDialog(
            "Aucun objet sélectionné.\n"
            "Sélectionnez au moins un objet et relancez le script."
        )
        return

    c4d.StopAllThreads()
    doc.StartUndo()

    for op in objects:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, op)
        align_axis_to_world(op, doc)

    doc.EndUndo()
    c4d.EventAdd()

    print(f"[align_axis_to_world] {len(objects)} objet(s) traité(s).")


# ─── Lancement ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    main()