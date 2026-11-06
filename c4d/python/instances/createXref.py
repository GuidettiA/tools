"""
Convertit l'objet sélectionné en XRef et rebranche ses références.

L'objet (avec ses enfants et ses matériaux) est sauvegardé dans
proxy/<nom>_xref.c4d à côté du document, puis remplacé par un XRef au même
emplacement. Les Instances et Cloners (mode Objet) qui pointaient vers
l'objet sont rebranchés sur le XRef.

Utilisation :
  1. Sauvegarder le document principal
  2. Sélectionner l'objet à convertir
  3. Lancer le script
"""

import c4d
import os

INSTANCE_ID  = c4d.Oinstance
CLONER_ID    = 1018544
MG_MODE      = 1018598
MG_OBJ_LINK  = 1018597
MG_MODE_OBJ  = 0
OXREF_ID     = c4d.Oxref
FILE_DESC_ID = c4d.DescID(
    c4d.DescLevel(c4d.ID_CA_XREF_FILE, c4d.DTYPE_FILENAME, 0)
)

# ─── Matériaux ────────────────────────────────────────────────

def collect_mat_map(op, mat_map, root=True):
    if op is None:
        return
    for tag in op.GetTags():
        if tag.GetType() == c4d.Ttexture:
            mat = tag[c4d.TEXTURETAG_MATERIAL]
            if mat is not None:
                mat_map[mat.GetName()] = mat
    collect_mat_map(op.GetDown(), mat_map, root=False)
    if not root:
        collect_mat_map(op.GetNext(), mat_map, root=False)

def insert_materials(mat_map, xref_doc):
    name_to_clone = {}
    for name, mat in mat_map.items():
        mat_clone = mat.GetClone(c4d.COPYFLAGS_NONE)
        if mat_clone is not None:
            xref_doc.InsertMaterial(mat_clone)
            name_to_clone[name] = mat_clone
    return name_to_clone

def relink_tags_by_index(original_op, clone_op, name_to_clone, root=True):
    if original_op is None or clone_op is None:
        return
    orig_tags  = original_op.GetTags()
    clone_tags = clone_op.GetTags()
    for ot, ct in zip(orig_tags, clone_tags):
        if ot.GetType() == c4d.Ttexture:
            mat = ot[c4d.TEXTURETAG_MATERIAL]
            if mat is not None:
                name = mat.GetName()
                if name in name_to_clone:
                    ct[c4d.TEXTURETAG_MATERIAL] = name_to_clone[name]
    relink_tags_by_index(original_op.GetDown(), clone_op.GetDown(), name_to_clone, root=False)
    if not root:
        relink_tags_by_index(original_op.GetNext(), clone_op.GetNext(), name_to_clone, root=False)

# ─── Références ───────────────────────────────────────────────

def find_references(root, target_op, results):
    op = root
    while op:
        try:
            t = op.GetType()
            ref = None
            if t == INSTANCE_ID:
                ref = op[c4d.INSTANCEOBJECT_LINK]
            elif t == CLONER_ID:
                if op[MG_MODE] == MG_MODE_OBJ:
                    ref = op[MG_OBJ_LINK]
            if ref is not None and ref == target_op:
                results.append(op)
        except Exception:
            pass
        find_references(op.GetDown(), target_op, results)
        op = op.GetNext()

# ─── XRef ─────────────────────────────────────────────────────

def create_xref(doc, source_obj, xref_path):
    xref = c4d.BaseObject(OXREF_ID)
    if xref is None:
        return None
    xref.SetMg(source_obj.GetMg())
    xref.SetName(source_obj.GetName())
    parent = source_obj.GetUp()
    pred   = source_obj.GetPred()
    doc.InsertObject(xref, parent, pred)
    ok = xref.SetParameter(
        FILE_DESC_ID,
        xref_path,
        c4d.DESCFLAGS_SET_USERINTERACTION
    )
    if not ok:
        xref.Remove()
        return None
    return xref

def relink_reference(op, new_target):
    try:
        t = op.GetType()
        if t == INSTANCE_ID:
            op[c4d.INSTANCEOBJECT_LINK] = new_target
            return True
        elif t == CLONER_ID:
            op[MG_OBJ_LINK] = new_target
            return True
    except Exception:
        pass
    return False

# ─── Main ─────────────────────────────────────────────────────

def main():
    doc = c4d.documents.GetActiveDocument()
    if doc is None:
        c4d.gui.MessageDialog("Aucun document actif.")
        return

    target = doc.GetActiveObject()
    if target is None:
        c4d.gui.MessageDialog("Sélectionnez un objet.")
        return

    if target.GetType() == OXREF_ID:
        c4d.gui.MessageDialog("L'objet sélectionné est déjà un XRef.")
        return

    doc_path = doc.GetDocumentPath()
    if not doc_path:
        c4d.gui.MessageDialog("Sauvegardez d'abord le document principal.")
        return

    proxy_dir = os.path.join(doc_path, "proxy")
    if not os.path.exists(proxy_dir):
        os.makedirs(proxy_dir)

    safe_name     = target.GetName().replace(" ", "_")
    xref_filename = safe_name + "_xref.c4d"
    xref_path     = os.path.join(proxy_dir, xref_filename)

    # 1. Collecte des matériaux sur target + enfants uniquement
    mat_map = {}
    collect_mat_map(target, mat_map)

    # 2. Clone de l'objet
    obj_clone = target.GetClone(c4d.COPYFLAGS_NONE)
    scale = obj_clone.GetRelScale()
    obj_clone.SetMl(c4d.Matrix())
    obj_clone.SetRelScale(scale)

    # 3. Préparation xref_doc + insertion des matériaux
    xref_doc = c4d.documents.BaseDocument()
    name_to_clone = insert_materials(mat_map, xref_doc)

    # 4. Rebranchement tags avant InsertObject
    relink_tags_by_index(target, obj_clone, name_to_clone)

    # 5. Insertion du clone dans xref_doc
    xref_doc.InsertObject(obj_clone)

    # 6. Sauvegarde
    if not c4d.documents.SaveDocument(
        xref_doc, xref_path,
        c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST,
        c4d.FORMAT_C4DEXPORT
    ):
        c4d.gui.MessageDialog("Impossible de sauvegarder :\n" + xref_path)
        c4d.documents.KillDocument(xref_doc)
        return
    c4d.documents.KillDocument(xref_doc)

    # 7. Collecte des références dans le doc principal
    refs = []
    find_references(doc.GetFirstObject(), target, refs)

    # 8. Remplacement par le XRef
    doc.StartUndo()

    source_xref = create_xref(doc, target, xref_path)
    if source_xref is None:
        doc.EndUndo()
        c4d.gui.MessageDialog("Échec de la création du XRef.")
        return

    doc.AddUndo(c4d.UNDOTYPE_NEW, source_xref)
    doc.AddUndo(c4d.UNDOTYPE_DELETE, target)
    target.Remove()

    relinked = 0
    for ref_obj in refs:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, ref_obj)
        if relink_reference(ref_obj, source_xref):
            relinked += 1

    doc.EndUndo()
    c4d.EventAdd()

    c4d.gui.MessageDialog(
        "XRef créé : proxy/{}\n{} matériau(x) transféré(s)\n{} référence(s) rebranchée(s).".format(
            xref_filename, len(name_to_clone), relinked
        )
    )

if __name__ == '__main__':
    main()