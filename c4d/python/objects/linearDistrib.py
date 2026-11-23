"""
Aligne une sélection d'objets de manière linéaire du premier au dernier.

Seul l'axe sélectionné change "AXIS"
Le premier et le dernier objet sélectionnés garde leur position d'origine.

Utilisation :
  1. Sélectionner plusieurs objets
  2. Lancer le script
"""

import c4d

AXIS = 0  # 0 = P.X, 1 = P.Y, 2 = P.Z (coordonnées locales)

def main():
    doc = c4d.documents.GetActiveDocument()
    objs = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_NONE)
    if len(objs) < 3:
        c4d.gui.MessageDialog("Sélectionne au moins 3 objets.")
        return

    objs.sort(key=lambda o: o.GetRelPos()[AXIS])
    start = objs[0].GetRelPos()[AXIS]
    end = objs[-1].GetRelPos()[AXIS]
    step = (end - start) / (len(objs) - 1)
    print("Début :", start, "Fin :", end, "Pas :", step)

    doc.StartUndo()
    for i, o in enumerate(objs):
        pos = o.GetRelPos()
        val = start + i * step
        if AXIS == 0: pos.x = val
        elif AXIS == 1: pos.y = val
        else: pos.z = val
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, o)
        o.SetRelPos(pos)
    doc.EndUndo()
    c4d.EventAdd()

main()
