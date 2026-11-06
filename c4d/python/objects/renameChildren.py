"""
Renomme les enfants de l'objet sélectionné en <parent>.1, <parent>.2, etc.

Seul le premier niveau est renommé ; le renommage récursif des sous-enfants
peut être activé dans rename_children().

Utilisation :
  1. Sélectionner l'objet parent
  2. Lancer le script
"""

import c4d

def rename_children(parent, base_name, current_index=1):
    """Fonction récursive pour parcourir et renommer les enfants.
    """
    # Récupère le premier enfant de l'objet
    child = parent.GetDown()

    while child:
        # 1. Enregistre l'état de l'enfant pour le Ctrl+Z (Undo) avant de changer le nom
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, child)

        # 2. Crée le nouveau nom (ex: Parent.1)
        new_name = f"{base_name}.{current_index}"
        child.SetName(new_name)

        # 3. Incrémente le compteur pour le prochain objet
        current_index += 1

        # --- OPTIONNEL ---
        # Si tu veux AUSSI renommer les enfants des enfants (les sous-enfants),
        # décommente les deux lignes ci-dessous :
        # if child.GetDown():
        #     current_index = rename_children(child, base_name, current_index)
        # -----------------

        # Passe à l'objet suivant au même niveau (le frère/la sœur)
        child = child.GetNext()

    return current_index

def main():
    # 'op' est l'objet actuellement sélectionné (le Parent)
    if not op:
        print("Veuillez sélectionner l'objet parent.")
        return

    # Vérifie si l'objet a au moins un enfant
    if not op.GetDown():
        print(f"L'objet '{op.GetName()}' n'a pas d'enfants à renommer.")
        return

    # Début de la session d'annulation (Undo)
    doc.StartUndo()

    # On récupère le nom du parent pour s'en servir de base
    parent_name = op.GetName()

    # Lance le renommage à partir du premier enfant
    rename_children(op, parent_name)

    # Fin de la session d'annulation
    doc.EndUndo()

    # Rafraîchit l'interface de Cinema 4D (notamment le gestionnaire d'objets)
    c4d.EventAdd()

if __name__=='__main__':
    main()