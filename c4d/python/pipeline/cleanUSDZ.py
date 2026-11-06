"""
Aplatit la hiérarchie d'un import USDZ en supprimant les nulls intermédiaires.

Tous les objets non-null sont remontés directement sous le null racine, en
conservant leur position monde.

Utilisation :
  - Avec un ou plusieurs nulls sélectionnés : nettoie chacun d'eux
  - Sans null sélectionné : regroupe toute la scène sous un nouveau null
    portant le nom du document
"""

import c4d
import os

# Aplatit la hiérarchie d'un null : remonte tous les objets non-null
# directement sous root_null et supprime les nulls intermédiaires
def cleanup_null(doc, root_null):
    all_geometry = []
    nulls_to_delete = []

    def scan_hierarchy(obj):
        while obj:
            if obj != root_null:
                if obj.GetType() != c4d.Onull:
                    all_geometry.append({
                        'obj': obj,
                        'matrix': obj.GetMg()
                    })
                else:
                    nulls_to_delete.append(obj)
            scan_hierarchy(obj.GetDown())
            obj = obj.GetNext()

    scan_hierarchy(root_null.GetDown())

    for item in all_geometry:
        obj = item['obj']
        mg  = item['matrix']
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, obj)
        obj.Remove()
        obj.InsertUnder(root_null)
        obj.SetMg(mg)

    for n in reversed(nulls_to_delete):
        doc.AddUndo(c4d.UNDOTYPE_DELETE, n)
        n.Remove()

def main():
    # Récupère tous les objets sélectionnés
    selected_objects = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN)

    # Filtre uniquement les nulls
    selected_nulls = [o for o in selected_objects if o.GetType() == c4d.Onull]

    doc.StartUndo()

    if selected_nulls:
        # On applique le nettoyage sur chaque null sélectionné
        for null in selected_nulls:
            cleanup_null(doc, null)
    else:
        # Pas de null sélectionné : traitement de toute la scène
        doc_name = doc.GetDocumentName()
        clean_name = os.path.splitext(doc_name)[0] or "Scene_Nettoyee"

        root_null = c4d.BaseObject(c4d.Onull)
        root_null.SetName(clean_name)
        doc.InsertObject(root_null)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, root_null)

        # Collecte depuis la racine de la scène (pas depuis le null vide)
        all_geometry = []
        nulls_to_delete = []

        def scan_scene(obj):
            while obj:
                if obj != root_null:
                    if obj.GetType() != c4d.Onull:
                        all_geometry.append({'obj': obj, 'matrix': obj.GetMg()})
                    else:
                        nulls_to_delete.append(obj)
                scan_scene(obj.GetDown())
                obj = obj.GetNext()

        scan_scene(doc.GetFirstObject())

        for item in all_geometry:
            obj = item['obj']
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, obj)
            obj.Remove()
            obj.InsertUnder(root_null)
            obj.SetMg(item['matrix'])

        for n in reversed(nulls_to_delete):
            doc.AddUndo(c4d.UNDOTYPE_DELETE, n)
            n.Remove()

    doc.EndUndo()
    c4d.EventAdd()

if __name__ == '__main__':
    main()