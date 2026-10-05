"""
Crée une instance de l'objet sélectionné, avec un contrôle d'échelle simplifié.

Un Python Tag et deux User Data sont ajoutés sur l'instance :
  - Scale : Vector (pas 0.001, défaut 1,1,1)
  - Fac   : Float (pas 0.01, défaut 100)
L'échelle appliquée à l'instance est Scale * Fac.

Utilisation :
  1. Sélectionner un objet
  2. Lancer le script
"""

import c4d
from c4d import gui

TAG_CODE = '''import c4d

def main():
    obj = op.GetObject()
    if obj is None:
        return

    scale = obj[c4d.ID_USERDATA, 1]
    fac   = obj[c4d.ID_USERDATA, 2]

    obj[c4d.ID_BASEOBJECT_REL_SCALE] = c4d.Vector(
        scale.x * fac,
        scale.y * fac,
        scale.z * fac,
    )
'''


def add_ud_vector(tag, name, default=c4d.Vector(1, 1, 1), step=0.01):
    bc = c4d.GetCustomDatatypeDefault(c4d.DTYPE_VECTOR)
    bc[c4d.DESC_NAME]       = name
    bc[c4d.DESC_SHORT_NAME] = name
    bc[c4d.DESC_ANIMATE]    = c4d.DESC_ANIMATE_ON
    bc[c4d.DESC_UNIT]       = c4d.DESC_UNIT_REAL
    bc[c4d.DESC_STEP]       = c4d.Vector(step, step, step)
    bc[c4d.DESC_DEFAULT]    = default
    element = tag.AddUserData(bc)
    tag[element] = default
    return element


def add_ud_float_percent(tag, name, default_pct=1.0, step=0.001):
    bc = c4d.GetCustomDatatypeDefault(c4d.DTYPE_REAL)
    bc[c4d.DESC_NAME]       = name
    bc[c4d.DESC_SHORT_NAME] = name
    bc[c4d.DESC_ANIMATE]    = c4d.DESC_ANIMATE_ON
    bc[c4d.DESC_UNIT]       = c4d.DESC_UNIT_PERCENT
    bc[c4d.DESC_STEP]       = step
    bc[c4d.DESC_MIN]        = 0.0
    bc[c4d.DESC_DEFAULT]    = default_pct
    element = tag.AddUserData(bc)
    tag[element] = default_pct
    return element


def main():
    doc = c4d.documents.GetActiveDocument()
    sel = doc.GetActiveObject()

    if sel is None:
        gui.MessageDialog("Sélectionnez un objet avant de lancer le script.")
        return

    doc.StartUndo()

    # ── 1. Créer l'Instance ──────────────────
    instance = c4d.BaseObject(c4d.Oinstance)
    instance.SetName("Instance_" + sel.GetName())
    instance[c4d.INSTANCEOBJECT_LINK] = sel
    instance.SetMg(sel.GetMg())
    doc.InsertObject(instance)
    doc.AddUndo(c4d.UNDOTYPE_NEW, instance)

    # ── 2. Créer le Python Tag sur l'instance ─
    tag = instance.MakeTag(c4d.Tpython)
    doc.AddUndo(c4d.UNDOTYPE_NEW, tag)
    tag.SetName("Scale x Fac")

    # ── 3. User Data SUR L'INSTANCE ─────────
    add_ud_vector(instance, "Scale", default=c4d.Vector(1, 1, 1), step=0.001)
    add_ud_float_percent(instance, "Fac", default_pct=1.0, step=0.0001)
    instance.Message(c4d.MSG_CHANGE)

    # ── 4. Code Python dans le tag ───────────
    tag[c4d.TPYTHON_CODE] = TAG_CODE

    # ── 5. Finaliser ─────────────────────────
    c4d.EventAdd()
    doc.EndUndo()
    doc.SetActiveObject(instance)

    gui.MessageDialog(
        "Instance créée !"
    )


if __name__ == "__main__":
    main()
