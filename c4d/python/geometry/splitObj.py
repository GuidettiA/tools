"""
Explose un objet polygonal en un objet distinct par îlot de polygones connectés.

Les îlots peuvent être regroupés selon leur boîte englobante (option de la
boîte de dialogue).

Tags transférés automatiquement :
  - Phong
  - UVW (tous les canaux)
  - Normales
  - Matériaux (TextureTag), y compris leurs sélections de polygones

Utilisation :
  1. Sélectionner un objet polygonal
  2. Lancer le script et régler les options
"""

import c4d
from c4d import gui
from collections import defaultdict

# Constantes de visibilité C4D (0=défaut, 1=off, 2=on)
VISIBILITY_OFF = 1

# ─────────────────────────────────────────────
#  Interface utilisateur (Dialogue)

class OptionsDialog(gui.GeDialog):
    ID_CHECK_BBOX = 1001
    ID_VALUE_BBOX = 1002
    ID_BTN_OK     = 1003

    def __init__(self):
        self.cancelled = True   # FIX : annulation détectée si la croix est utilisée
        self.use_bbox  = True
        self.bbox_val  = 0.0

    def CreateLayout(self):
        self.SetTitle("Exploser l'objet")

        self.GroupBegin(0, c4d.BFH_SCALEFIT, 2, 0, "Paramètres")
        self.GroupBorderSpace(10, 10, 10, 10)

        self.AddCheckbox(self.ID_CHECK_BBOX, c4d.BFH_LEFT, 0, 0, "Regrouper par BBox")
        self.SetBool(self.ID_CHECK_BBOX, True)

        self.AddEditNumber(self.ID_VALUE_BBOX, c4d.BFH_SCALEFIT, 80, 0)
        self.SetFloat(self.ID_VALUE_BBOX, 0.0)

        self.GroupEnd()

        self.AddButton(self.ID_BTN_OK, c4d.BFH_CENTER, 100, 20, "Exécuter")
        return True

    def Command(self, id, msg):
        if id == self.ID_BTN_OK:
            self.cancelled = False  # FIX : seul le bouton valide lève le flag
            self.use_bbox  = self.GetBool(self.ID_CHECK_BBOX)
            self.bbox_val  = self.GetFloat(self.ID_VALUE_BBOX)
            self.Close()
        return True

# ─────────────────────────────────────────────
#  Union-Find & Logique Géométrique

class UnionFind:
    def __init__(self, n):
        self.parent = list(range(n))
        self.rank   = [0] * n

    def find(self, x):
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra == rb: return
        if self.rank[ra] < self.rank[rb]: ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]: self.rank[ra] += 1

    def groups(self):
        g = defaultdict(list)
        for i in range(len(self.parent)):
            g[self.find(i)].append(i)
        return list(g.values())

def find_polygon_islands(polys, point_count):
    """
    Regroupe les polygones en îles connexes par DFS itératif.
    Note : un triangle en C4D est un CPolygon avec c == d, ce qui est
    préservé tel quel lors de la copie — aucun traitement spécial requis.
    """
    poly_count  = len(polys)
    pt_to_polys = [[] for _ in range(point_count)]
    for idx, p in enumerate(polys):
        for v in {p.a, p.b, p.c, p.d}:
            pt_to_polys[v].append(idx)
    visited = [False] * poly_count
    islands = []
    for start in range(poly_count):
        if visited[start]: continue
        island, stack = [], [start]
        while stack:
            pid = stack.pop()
            if visited[pid]: continue
            visited[pid] = True
            island.append(pid)
            p = polys[pid]
            for v in {p.a, p.b, p.c, p.d}:
                for nbr in pt_to_polys[v]:
                    if not visited[nbr]: stack.append(nbr)
        islands.append(island)
    return islands

def compute_island_bbox(island_poly_ids, polys, points):
    used = set()
    for pid in island_poly_ids:
        p = polys[pid]
        used.update({p.a, p.b, p.c, p.d})
    pts = [points[i] for i in used]
    mn = c4d.Vector(min(pt.x for pt in pts), min(pt.y for pt in pts), min(pt.z for pt in pts))
    mx = c4d.Vector(max(pt.x for pt in pts), max(pt.y for pt in pts), max(pt.z for pt in pts))
    return mn, mx

def bboxes_overlap(mn1, mx1, mn2, mx2, tol):
    return (mn1.x - tol <= mx2.x and mx1.x + tol >= mn2.x and
            mn1.y - tol <= mx2.y and mx1.y + tol >= mn2.y and
            mn1.z - tol <= mx2.z and mx1.z + tol >= mn2.z)

def cluster_islands(islands, polys, points, tol):
    """
    Regroupe les îles dont les bounding boxes se chevauchent (± tol).
    Complexité O(n²) sur le nombre d'îles — acceptable pour un usage interactif
    standard ; à optimiser (sweep line) si le mesh comporte des centaines d'îles.
    """
    bboxes = [compute_island_bbox(isl, polys, points) for isl in islands]
    uf = UnionFind(len(islands))
    for i in range(len(islands)):
        for j in range(i + 1, len(islands)):
            if bboxes_overlap(bboxes[i][0], bboxes[i][1], bboxes[j][0], bboxes[j][1], tol):
                uf.union(i, j)
    clusters = []
    for group in uf.groups():
        merged = []
        for island_idx in group: merged.extend(islands[island_idx])
        clusters.append(merged)
    return clusters

# ─────────────────────────────────────────────
#  Construction et Transfert de Tags

def build_object(poly_ids, polys, points, name, source_matrix):
    # FIX : garantir que poly_ids est une liste (sécurité si générateur passé)
    poly_ids = list(poly_ids)

    used_pts = set()
    for pid in poly_ids:
        p = polys[pid]
        used_pts.update({p.a, p.b, p.c, p.d})

    sorted_pts = sorted(used_pts)
    old_to_new_pt   = {old: new for new, old in enumerate(sorted_pts)}
    old_to_new_poly = {old: new for new, old in enumerate(poly_ids)}

    new_obj = c4d.PolygonObject(len(sorted_pts), len(poly_ids))
    new_obj.SetName(name)
    new_obj.SetMg(source_matrix)

    for new_idx, old_idx in enumerate(sorted_pts):
        new_obj.SetPoint(new_idx, points[old_idx])

    for new_pid, old_pid in enumerate(poly_ids):
        p = polys[old_pid]
        new_obj.SetPolygon(new_pid, c4d.CPolygon(
            old_to_new_pt[p.a], old_to_new_pt[p.b],
            old_to_new_pt[p.c], old_to_new_pt[p.d]))

    new_obj.Message(c4d.MSG_UPDATE)
    return new_obj, old_to_new_poly

def transfer_all_tags(src_obj, dst_obj, poly_ids, old_to_new_poly):
    # FIX : garantir que poly_ids est une liste (itération multiple)
    poly_ids = list(poly_ids)

    # Phong
    phong = src_obj.GetTag(c4d.Tphong)
    if phong:
        dst_obj.InsertTag(phong.GetClone())

    # UVW (tous les canaux)
    tag = src_obj.GetFirstTag()
    while tag:
        if tag.GetType() == c4d.Tuvw:
            new_tag = c4d.UVWTag(len(poly_ids))
            new_tag.SetName(tag.GetName())
            for new_pid, old_pid in enumerate(poly_ids):
                uvw = tag.GetSlow(old_pid)
                new_tag.SetSlow(new_pid, uvw['a'], uvw['b'], uvw['c'], uvw['d'])
            dst_obj.InsertTag(new_tag)
        tag = tag.GetNext()

    # Normales
    norm = src_obj.GetTag(c4d.Tnormal)
    if norm:
        new_norm = c4d.NormalTag(len(poly_ids))
        src_data, dst_data = norm.GetDataAddressR(), new_norm.GetDataAddressW()
        for new_pid, old_pid in enumerate(poly_ids):
            c4d.NormalTag.Set(dst_data, new_pid, c4d.NormalTag.Get(src_data, old_pid))
        dst_obj.InsertTag(new_norm)

    # Matériaux et Sélections de polygones
    # FIX : on insère d'abord les SelectionTags, puis les TextureTags qui
    #       y font référence — C4D requiert cet ordre pour reconnaître la restriction.
    #       De plus, un TextureTag avec restriction est ignoré si la sélection
    #       correspondante est introuvable dans la source.
    transferred_selections = set()

    tag = src_obj.GetFirstTag()
    while tag:
        if tag.GetType() == c4d.Ttexture:
            restr = tag[c4d.TEXTURETAG_RESTRICTION]
            clone = tag.GetClone()

            if restr:
                # Restriction déclarée : chercher et transférer le SelectionTag
                sel_found = False
                if restr not in transferred_selections:
                    sel_tag = src_obj.GetFirstTag()
                    while sel_tag:
                        if (sel_tag.GetType() == c4d.Tpolygonselection
                                and sel_tag.GetName() == restr):
                            new_sel = c4d.SelectionTag(c4d.Tpolygonselection)
                            new_sel.SetName(restr)
                            s_sel = sel_tag.GetBaseSelect()
                            d_sel = new_sel.GetBaseSelect()
                            for old_pid in poly_ids:
                                if s_sel.IsSelected(old_pid):
                                    d_sel.Select(old_to_new_poly[old_pid])
                            dst_obj.InsertTag(new_sel)         # SelectionTag en premier
                            transferred_selections.add(restr)
                            sel_found = True
                            break
                        sel_tag = sel_tag.GetNext()
                else:
                    sel_found = True  # déjà transféré lors d'un tag précédent

                # FIX : n'insérer le TextureTag que si la sélection existe
                if sel_found:
                    dst_obj.InsertTag(clone)
            else:
                # Pas de restriction : on insère le TextureTag directement
                dst_obj.InsertTag(clone)

        tag = tag.GetNext()

# ─────────────────────────────────────────────
#  Main

def main():
    doc = c4d.documents.GetActiveDocument()
    obj = doc.GetActiveObject()

    if obj is None or not obj.IsInstanceOf(c4d.Opolygon):
        gui.MessageDialog("Sélectionnez un objet polygonal.")
        return

    # FIX : guard objet sans polygones
    polys = obj.GetAllPolygons()
    if not polys:
        gui.MessageDialog("L'objet ne contient aucun polygone.")
        return

    # Fenêtre d'options
    dlg = OptionsDialog()
    dlg.Open(c4d.DLG_TYPE_MODAL, defaultw=300, defaulth=100)

    # FIX : abandon si l'utilisateur a fermé la fenêtre sans valider
    if dlg.cancelled:
        return

    use_bbox = dlg.use_bbox
    bbox_val = dlg.bbox_val

    points        = obj.GetAllPoints()
    source_matrix = obj.GetMg()

    # Calcul des îles / clusters
    islands = find_polygon_islands(polys, obj.GetPointCount())
    clusters = cluster_islands(islands, polys, points, bbox_val) if use_bbox else islands

    n = len(clusters)
    if n <= 1 and use_bbox:
        gui.MessageDialog("Un seul groupe détecté. Vérifiez la tolérance.")
        return

    obj_name  = obj.GetName()
    pad_width = len(str(n))

    doc.StartUndo()
    try:
        for i, cluster in enumerate(clusters):
            part_name = f"{obj_name}_part_{str(i + 1).zfill(pad_width)}"
            new_obj, old_poly_map = build_object(cluster, polys, points, part_name, source_matrix)
            transfer_all_tags(obj, new_obj, cluster, old_poly_map)
            doc.InsertObject(new_obj, pred=obj)
            doc.AddUndo(c4d.UNDOTYPE_NEW, new_obj)

        doc.AddUndo(c4d.UNDOTYPE_CHANGE, obj)

        # FIX : VISIBILITY_OFF = 1 en C4D (0=défaut, 1=off, 2=on)
        obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = VISIBILITY_OFF
        obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER] = VISIBILITY_OFF
        obj.SetName(f"{obj_name}_ORIGINAL")

    except Exception as e:
        gui.MessageDialog(f"Erreur : {e}")
    finally:
        doc.EndUndo()

    c4d.EventAdd()

if __name__ == "__main__":
    main()