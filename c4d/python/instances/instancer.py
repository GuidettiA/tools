"""
Remplace les objets sélectionnés par des instances du premier objet sélectionné.

Chaque instance reprend la matrice monde et la place dans la hiérarchie de
l'objet qu'elle remplace.

Utilisation :
  1. Sélectionner l'objet source, puis les objets à remplacer
     (l'ordre de sélection compte)
  2. Lancer le script
"""

import c4d
from c4d import gui

def main():
    doc = c4d.documents.GetActiveDocument()

    # Le premier objet sélectionné devient la source de l'instance,
    # les suivants sont remplacés — l'ordre de sélection est préservé.
    selection = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_SELECTIONORDER)
    if len(selection) < 2:
        gui.MessageDialog(
            "Veuillez sélectionner au moins deux objets.\n"
            "Le premier sera la source, les autres seront remplacés."
        )
        return

    target_obj = selection[0]
    to_replace = selection[1:]

    doc.StartUndo()
    try:
        for obj in to_replace:
            instance = c4d.BaseObject(c4d.Oinstance)

            # Modes disponibles :
            # 0 : Instance standard
            # 1 : Render Instance
            # 2 : Multi-Instance
            instance[c4d.INSTANCEOBJECT_RENDERINSTANCE_MODE] = 0
            instance[c4d.INSTANCEOBJECT_LINK] = target_obj
            instance.SetName(f"Instance_{target_obj.GetName()}")

            # Copie de la position, rotation et échelle de l'objet remplacé
            instance.SetMg(obj.GetMg())

            # Insertion au même endroit dans la hiérarchie
            doc.InsertObject(instance, parent=obj.GetUp(), pred=obj)
            doc.AddUndo(c4d.UNDOTYPE_NEW, instance)

            # AddUndo AVANT Remove() pour que C4D capture l'état de l'objet
            doc.AddUndo(c4d.UNDOTYPE_DELETE, obj)
            obj.Remove()

    except Exception as e:
        gui.MessageDialog(f"Erreur : {e}")
    finally:
        doc.EndUndo()

    c4d.EventAdd()

if __name__ == "__main__":
    main()