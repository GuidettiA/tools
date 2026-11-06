"""
Crée un nuage de points couvrant la surface d'un objet ou reprenant ses sommets.

Sert à obtenir une répartition de points sur une forme, par exemple comme
support de clonage ou de particules.

Modes :
  - Surface : tire N points au hasard sur la surface, répartis uniformément
    (pondéré par l'aire des polygones, donc même densité partout). Le tirage
    change à chaque exécution.
  - Sommets : reprend un point par sommet du maillage. Le nombre de points
    saisi est alors ignoré.

Accepte aussi les générateurs et les objets déformés : c'est la géométrie
affichée qui est utilisée.

Résultat : un objet "PointCloud" placé à l'origine, en coordonnées monde.
L'objet source reste visible. Non annulable avec Ctrl+Z (supprimer le
nuage à la main si besoin).

Utilisation :
  1. Sélectionner un objet
  2. Lancer le script, choisir le mode et le nombre de points, puis Créer
"""

import c4d
import random
import bisect
 
# --- Paramètres par défaut (repris par la boîte de dialogue au lancement) ---
DEFAULT_POINT_COUNT = 5000
OUTPUT_NAME = "PointCloud"
 
# IDs des éléments de la boîte de dialogue
ID_GROUP = 1000
ID_POINT_COUNT = 1001
ID_MODE_VERTICES = 1002
ID_MODE_SURFACE = 1003
ID_OK = 1004
ID_CANCEL = 1005
 
 
class PointCloudDialog(c4d.gui.GeDialog):
    """Boîte de dialogue demandant le nombre de points et le mode d'échantillonnage."""
 
    point_count = DEFAULT_POINT_COUNT
    mode = "SURFACE"
    confirmed = False
 
    def CreateLayout(self):
        self.SetTitle("Créer un nuage de points")
 
        self.GroupBegin(ID_GROUP, c4d.BFH_SCALEFIT, 2, 0)
        self.GroupBorderSpace(10, 10, 10, 10)
 
        self.AddStaticText(0, c4d.BFH_LEFT, name="Nombre de points :")
        self.AddEditNumberArrows(ID_POINT_COUNT, c4d.BFH_SCALEFIT)
 
        self.AddStaticText(0, c4d.BFH_LEFT, name="Mode :")
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 1, 0)
        self.AddRadioGroup(ID_MODE_SURFACE, c4d.BFH_SCALEFIT, 1, 2)
        self.AddChild(ID_MODE_SURFACE, 0, "Échantillonnage surface (uniforme)")
        self.AddChild(ID_MODE_SURFACE, 1, "Points existants du maillage")
        self.GroupEnd()
 
        self.GroupEnd()
 
        self.GroupBegin(0, c4d.BFH_RIGHT, 2, 0)
        self.AddButton(ID_CANCEL, c4d.BFH_RIGHT, name="Annuler")
        self.AddButton(ID_OK, c4d.BFH_RIGHT, name="Créer")
        self.GroupEnd()
 
        return True
 
    def InitValues(self):
        self.SetLong(ID_POINT_COUNT, DEFAULT_POINT_COUNT, 1, 10000000)
        self.SetLong(ID_MODE_SURFACE, 0)
        return True
 
    def Command(self, id, msg):
        if id == ID_OK:
            self.point_count = self.GetLong(ID_POINT_COUNT)
            self.mode = "SURFACE" if self.GetLong(ID_MODE_SURFACE) == 0 else "VERTICES"
            self.confirmed = True
            self.Close()
        elif id == ID_CANCEL:
            self.confirmed = False
            self.Close()
        return True
 
 
def get_deformed_object(op):
    """Récupère le cache déformé/généré si besoin (générateurs, deformers)."""
    cache = op.GetDeformCache()
    if cache is None:
        cache = op.GetCache()
    if cache is None:
        cache = op
    return cache
 
 
def collect_triangles(obj):
    """Retourne une liste de triangles (p1, p2, p3) en coordonnées globales."""
    points = obj.GetAllPoints()
    polys = obj.GetAllPolygons()
    mg = obj.GetMg()
    triangles = []
    for poly in polys:
        a, b, c, d = poly.a, poly.b, poly.c, poly.d
        p_a = mg * points[a]
        p_b = mg * points[b]
        p_c = mg * points[c]
        triangles.append((p_a, p_b, p_c))
        if c != d:
            p_d = mg * points[d]
            triangles.append((p_a, p_c, p_d))
    return triangles
 
 
def triangle_area(p1, p2, p3):
    return (p2 - p1).Cross(p3 - p1).GetLength() * 0.5
 
 
def sample_point_on_triangle(p1, p2, p3):
    r1 = random.random()
    r2 = random.random()
    sqrt_r1 = r1 ** 0.5
    u = 1 - sqrt_r1
    v = r2 * sqrt_r1
    w = 1 - u - v
    return p1 * u + p2 * v + p3 * w
 
 
def build_vertex_cloud(obj):
    mg = obj.GetMg()
    points = obj.GetAllPoints()
    return [mg * p for p in points]
 
 
def build_surface_cloud(obj, count):
    triangles = collect_triangles(obj)
    if not triangles:
        return []
 
    areas = [triangle_area(*t) for t in triangles]
    total_area = sum(areas)
    if total_area == 0:
        return []
 
    # distribution cumulative pour tirage pondéré par aire
    cumulative = []
    running = 0.0
    for a in areas:
        running += a
        cumulative.append(running)
 
    result = []
    for _ in range(count):
        r = random.random() * total_area
        idx = bisect.bisect_left(cumulative, r)
        idx = min(idx, len(triangles) - 1)
        p1, p2, p3 = triangles[idx]
        result.append(sample_point_on_triangle(p1, p2, p3))
    return result
 
 
def main():
    doc = c4d.documents.GetActiveDocument()
    op = doc.GetActiveObject()
 
    if op is None:
        c4d.gui.MessageDialog("Sélectionne un objet avant de lancer le script.")
        return
 
    source = get_deformed_object(op)
 
    if not source.CheckType(c4d.Opolygon):
        c4d.gui.MessageDialog("L'objet (ou son cache) doit être un objet Polygon.")
        return
 
    dlg = PointCloudDialog()
    dlg.Open(c4d.DLG_TYPE_MODAL, defaultw=300, defaulth=100)
 
    if not dlg.confirmed:
        return
 
    point_count = max(1, dlg.point_count)
    mode = dlg.mode
 
    if mode == "VERTICES":
        cloud_points = build_vertex_cloud(source)
    else:
        cloud_points = build_surface_cloud(source, point_count)
 
    if not cloud_points:
        c4d.gui.MessageDialog("Aucun point généré.")
        return
 
    cloud_obj = c4d.PolygonObject(len(cloud_points), 0)
    cloud_obj.SetName(OUTPUT_NAME)
    for i, p in enumerate(cloud_points):
        cloud_obj.SetPoint(i, p)
    cloud_obj.Message(c4d.MSG_UPDATE)
 
    doc.InsertObject(cloud_obj)
    doc.SetActiveObject(cloud_obj)
    c4d.EventAdd()
 
 
if __name__ == "__main__":
    main()
