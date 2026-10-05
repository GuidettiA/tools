"""
Pose un point au centre de chaque élément séparé d'un objet polygonal.

Sert à préparer un support de clonage : un objet composé de nombreux
morceaux (feuilles, cailloux, fenêtres…) devient un nuage avec un point par
morceau, sur lequel un Cloner (mode Objet) peut placer des clones.

Détails :
  - Un "élément" (îlot) est un groupe de polygones connectés entre eux.
  - Regroupement BBox (optionnel) : les éléments dont les boîtes englobantes
    se touchent ou se chevauchent, à la tolérance près, fusionnent en un seul
    point. Utile quand un élément est fait de plusieurs pièces disjointes
    (ex. une feuille et sa tige). Avec une tolérance de 0, seuls les
    éléments dont les boîtes se chevauchent déjà sont fusionnés.
  - Le point est la moyenne des sommets de l'élément (et non le centre de
    sa boîte englobante) : il se décale vers les zones les plus denses.
  - Le nuage ne contient que des positions : pas d'orientation ni d'échelle
    par point, contrairement à un Matrix MoGraph.

Résultat : un objet "Points_<nom>" à la même position que la source, qui est
masquée (éditeur et rendu). Annulable avec Ctrl+Z.

Utilisation :
  1. Sélectionner un objet polygonal (éditable : les générateurs ne sont
     pas acceptés)
  2. Lancer le script, régler le regroupement et la tolérance, puis Générer
"""

import c4d
from c4d import gui
from collections import defaultdict

# Constantes de visibilité C4D (0=défaut, 1=off, 2=on)
VISIBILITY_OFF = 1

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
        for island_idx in group:
            merged.extend(islands[island_idx])
        clusters.append(merged)
    return clusters

def get_cluster_center(cluster_poly_ids, polys, points):
    used_pts = set()
    for pid in cluster_poly_ids:
        p = polys[pid]
        used_pts.update({p.a, p.b, p.c, p.d})
    if not used_pts:
        return c4d.Vector()
    return sum((points[i] for i in used_pts), c4d.Vector()) / len(used_pts)

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
        self.SetTitle("Options Nuage de Points")

        self.GroupBegin(0, c4d.BFH_SCALEFIT, 3, 0, "Paramètres")
        self.GroupBorderSpace(10, 10, 10, 10)

        self.AddCheckbox(self.ID_CHECK_BBOX, c4d.BFH_LEFT, 0, 0, "Activer regroupement BBox")
        self.SetBool(self.ID_CHECK_BBOX, True)

        self.AddStaticText(0, c4d.BFH_LEFT, name="Tolérance :")
        self.AddEditNumber(self.ID_VALUE_BBOX, c4d.BFH_SCALEFIT, 80, 0)
        self.SetFloat(self.ID_VALUE_BBOX, 0.0)

        self.GroupEnd()

        self.AddButton(self.ID_BTN_OK, c4d.BFH_CENTER, 100, 20, "Générer")
        return True

    def Command(self, id, msg):
        if id == self.ID_BTN_OK:
            self.cancelled = False  # FIX : seul le bouton valide lève le flag
            self.use_bbox  = self.GetBool(self.ID_CHECK_BBOX)
            self.bbox_val  = self.GetFloat(self.ID_VALUE_BBOX)
            self.Close()
        return True

# ─────────────────────────────────────────────
#  Main

def main():
    doc = c4d.documents.GetActiveDocument()
    obj = doc.GetActiveObject()

    if obj is None or not obj.IsInstanceOf(c4d.Opolygon):
        gui.MessageDialog("Sélectionnez un objet polygonal.")
        return

    # FIX : guard objet sans polygones (avant l'ouverture du dialogue)
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

    points = obj.GetAllPoints()

    # Calcul des îles / clusters
    islands  = find_polygon_islands(polys, obj.GetPointCount())
    clusters = cluster_islands(islands, polys, points, bbox_val) if use_bbox else islands

    n = len(clusters)
    if n <= 1 and use_bbox:
        gui.MessageDialog("Un seul groupe détecté. Vérifiez la tolérance.")
        return

    # Construction du nuage de points
    all_centers = [get_cluster_center(c, polys, points) for c in clusters]
    point_cloud = c4d.PolygonObject(n, 0)
    point_cloud.SetName(f"Points_{obj.GetName()}")
    point_cloud.SetAllPoints(all_centers)
    point_cloud.SetMg(obj.GetMg())

    doc.StartUndo()
    try:
        doc.InsertObject(point_cloud)
        doc.AddUndo(c4d.UNDOTYPE_NEW, point_cloud)

        doc.AddUndo(c4d.UNDOTYPE_CHANGE, obj)
        # VISIBILITY_OFF = 1 en C4D (0=défaut, 1=off, 2=on)
        obj[c4d.ID_BASEOBJECT_VISIBILITY_EDITOR] = VISIBILITY_OFF
        obj[c4d.ID_BASEOBJECT_VISIBILITY_RENDER]  = VISIBILITY_OFF

    except Exception as e:
        gui.MessageDialog(f"Erreur : {e}")
    finally:
        doc.EndUndo()

    c4d.EventAdd()

if __name__ == "__main__":
    main()