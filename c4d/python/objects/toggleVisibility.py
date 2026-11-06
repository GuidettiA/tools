"""
Fait cycler la visibilité éditeur et rendu des objets sélectionnés.

Les trois états (Défaut, On, Off) s'enchaînent à chaque exécution, et la
même valeur est appliquée à la visibilité éditeur et rendu.

Utilisation :
  1. Sélectionner un ou plusieurs objets
  2. Lancer le script
"""

import c4d

def main():
    # Récupération de la sélection
    selection = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_0)
    if not selection:
        return

    doc.StartUndo()
    
    for obj in selection:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, obj)
        
        # On récupère l'état actuel de la visibilité éditeur
        current = obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR]
        
        # LOGIQUE DE BOUCLE : 0 -> 1 -> 2 -> 0
        if current == 0:   # Gris (Default)
            new_state = 1  # Vers Vert (On)
        elif current == 1: # Vert (On)
            new_state = 2  # Vers Rouge (Off)
        else:              # Rouge (Off) ou autre
            new_state = 0  # Retour au Gris (Default)
            
        # Application aux deux points (Vue et Rendu)
        obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = new_state
        obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = new_state
        
        obj.Message(c4d.MSG_UPDATE)

    doc.EndUndo()
    c4d.EventAdd()

if __name__=='__main__':
    main()