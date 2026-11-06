# -*- coding: utf-8 -*-
"""
Homepage — panneau Cinema 4D listant les projets en cours
petit-studio.fr

Installation :
  Copier le dossier « homepage_c4d » dans le dossier plugins de Cinema 4D
  (Édition > Préférences > Ouvrir le dossier des préférences > plugins),
  ou l'ajouter via Préférences > Plugins > Ajouter un dossier.
  Relancer C4D, puis Extensions > Homepage. La fenêtre est dockable :
  une fois dockée et le layout enregistré, elle réapparaît à chaque lancement.

Configuration partagée avec le panneau After Effects :
  %APPDATA%\\petit-studio\\homepage.json
    root        : dossier scanné (commun à AE et C4D)
    stages      : étapes After Effects
    c4d_stages  : étapes Cinema 4D, dans l'ordre, avec le dossier du .c4d relatif au projet
    skip        : noms de dossiers à ignorer pendant le scan (commun à AE et C4D),
                  en plus des dossiers de rendu/cache ignorés d'office
"""

import os
import re
import sys
import json
import time
import shutil

import c4d
from c4d import gui, documents, storage

# ID de test réservé par Maxon (1000001 à 1000010) : à remplacer par un ID unique
# obtenu sur developers.maxon.net avant toute diffusion.
PLUGIN_ID = 1000010

# ---------- Réglages ----------
LIST_H = 150      # hauteur des tableaux (px)
MAX_DEPTH = 4     # profondeur max de recherche des .c4d dans un projet

# Dossiers toujours ignorés pendant le scan ; les autres se règlent dans la clé « skip » du JSON
SKIP_BUILTIN = re.compile(r"^(renders?|caches?|proxy|tex|illum|backup)$", re.I)
# .c4d ignorés : copies de sauvegarde automatiques
IGNORE_FILE = re.compile(r"(_backup(_\d+)?|autosave)", re.I)

DEFAULT_C4D_STAGES = [
    {"name": "maquette",  "folder": "maquette/c4d"},
    {"name": "layout",    "folder": "layout/c4d"},
    {"name": "animation", "folder": "animation/c4d"},
]

NAME_RULE = re.compile(r"^[a-z0-9]+([_-][a-z0-9]+)*$")
# Copie de conflit Synology Drive : nom_<client>_<Mon-JJ-HHMM-AAAA>_Conflict
CONFLICT = re.compile(r"_[^_]+_[^_]+_conflict$", re.I)


# ---------- Configuration ----------
def config_path():
    if sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("APPDATA", os.path.expanduser("~"))
    return os.path.join(base, "petit-studio", "homepage.json")


def save_config(cfg):
    path = config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)


def load_config():
    path = config_path()
    cfg = {}
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except (ValueError, OSError) as e:
            gui.MessageDialog("Fichier de configuration illisible :\n%s\n\n%s" % (path, e))
            return {"c4d_stages": DEFAULT_C4D_STAGES, "skip": []}
    if not isinstance(cfg, dict):
        cfg = {}
    changed = False
    if not cfg.get("c4d_stages"):
        cfg["c4d_stages"] = DEFAULT_C4D_STAGES
        changed = True
    if not isinstance(cfg.get("skip"), list):
        cfg["skip"] = []
        changed = True
    if changed:
        save_config(cfg)  # les autres clés (root, stages AE) sont conservées
    return cfg


def stage_index(cfg, name):
    name = name.lower()
    for i, s in enumerate(cfg["c4d_stages"]):
        if str(s.get("name", "")).lower() == name:
            return i
    return -1


# ---------- Analyse des noms ----------
def is_conflict(path):
    return bool(CONFLICT.search(os.path.splitext(os.path.basename(path))[0]))


def parse_name(path):
    """date_client_projet_etape_version (suffixe de conflit ignoré) ; None hors schéma."""
    base = CONFLICT.sub("", os.path.splitext(os.path.basename(path))[0])
    parts = base.split("_")
    if len(parts) < 3:
        return None
    m = re.match(r"^(v?)(\d+)$", parts[-1], re.I)
    if not m:
        return None
    return {
        "prefix":  "_".join(parts[:-2]),
        "stage":   parts[-2],
        "version": int(m.group(2)),
        "label":   m.group(2),
        "vchar":   m.group(1),
        "width":   max(2, len(m.group(2))),
    }


def build_name(info, stage, version):
    v = str(version).zfill(info["width"])
    return ("%s_%s_%s%s" % (info["prefix"], stage, info["vchar"], v)).lower() + ".c4d"


def free_file(folder, info, stage, start_v):
    """Premier numéro libre à partir de start_v : rien n'est jamais écrasé."""
    v = start_v
    while os.path.exists(os.path.join(folder, build_name(info, stage, v))):
        v += 1
    return os.path.join(folder, build_name(info, stage, v))


# ---------- Scan ----------
def sub_folders(folder):
    try:
        names = sorted(os.listdir(folder))
    except OSError:
        return []
    return [os.path.join(folder, n) for n in names
            if not n.startswith((".", "#")) and os.path.isdir(os.path.join(folder, n))]


def find_c4d(folder, depth, out, skip):
    if depth > MAX_DEPTH:
        return
    try:
        names = os.listdir(folder)
    except OSError:
        return
    for n in names:
        if n.startswith("."):
            continue
        p = os.path.join(folder, n)
        if os.path.isdir(p):
            if not SKIP_BUILTIN.match(n) and n.lower() not in skip:
                find_c4d(p, depth + 1, out, skip)
        elif n.lower().endswith(".c4d") and not IGNORE_FILE.search(n):
            out.append(p)


def folder_stage(path, project):
    rel = os.path.relpath(os.path.dirname(path), project).replace("\\", "/")
    return "(racine)" if rel == "." else rel


def scan(root, skip):
    """skip : ensemble de noms de dossiers à ignorer, en minuscules."""
    projects = []
    for client in sub_folders(root):
        for proj in sub_folders(client):
            files = []
            find_c4d(proj, 1, files, skip)
            files.sort(key=os.path.getmtime, reverse=True)
            items, latest, conflicts = [], None, 0
            for f in files:
                info = parse_name(f)
                it = {
                    "path":     f,
                    "info":     info,
                    "stage":    info["stage"] if info else folder_stage(f, proj),
                    "version":  info["label"] if info else "—",
                    "mtime":    os.path.getmtime(f),
                    "conflict": is_conflict(f),
                }
                if it["conflict"]:
                    conflicts += 1
                elif latest is None:
                    latest = it  # .c4d le plus récent hors conflit
                items.append(it)
            if latest is None and items:
                latest = items[0]
            projects.append({
                "client":    os.path.basename(client),
                "name":      os.path.basename(proj),
                "folder":    proj,
                "items":     items,
                "latest":    latest,
                "conflicts": conflicts,
                "stage":     latest["stage"] if latest else "—",
                "last":      latest["mtime"] if latest else None,
            })
    # Plus récent en haut, projets sans .c4d à la fin
    projects.sort(key=lambda p: p["last"] or 0, reverse=True)
    return projects


def latest_by_stage(cfg, items):
    """Une ligne par étape : version la plus haute, puis la plus récente.
    Ordre des étapes selon la config ; copies de conflit à la fin."""
    best, conflicts = {}, []
    for it in items:
        if it["conflict"]:
            conflicts.append(it)
            continue
        k = it["stage"].lower()
        key = (it["info"]["version"] if it["info"] else -1, it["mtime"])
        if k not in best or key > best[k][0]:
            best[k] = (key, it)

    def order(k):
        i = stage_index(cfg, k)
        return i if i >= 0 else 999

    return [best[k][1] for k in sorted(best, key=order)] + conflicts


def fmt(t):
    return time.strftime("%d/%m/%y %H:%M", time.localtime(t)) if t else "—"


# ---------- Documents ouverts ----------
def norm(p):
    return os.path.normcase(os.path.normpath(p))


def find_open_doc(path):
    doc = documents.GetFirstDocument()
    while doc:
        name = doc.GetDocumentName()
        if name and norm(os.path.join(doc.GetDocumentPath(), name)) == norm(path):
            return doc
        doc = doc.GetNext()
    return None


def collect_tex(path, doc=None):
    """Textures réellement utilisées par la scène, référencées en relatif et situées
    dans <dossier de la scène>/tex/. Les textures ailleurs (chemins absolus,
    bibliothèques communes…) sont ignorées : elles restent où elles sont.
    Renvoie une liste de chemins absolus."""
    src_dir = os.path.dirname(path)
    tex_dir = norm(os.path.join(src_dir, "tex"))
    tmp = None
    if doc is None:
        tmp = documents.LoadDocument(path, c4d.SCENEFILTER_OBJECTS | c4d.SCENEFILTER_MATERIALS, None)
        if tmp is None:
            raise OSError("Impossible de lire la scène : " + path)
        doc = tmp
    try:
        assets = []
        flags = getattr(c4d, "ASSETDATA_FLAG_TEXTURESONLY", 0)
        documents.GetAllAssetsNew(doc, False, "", flags, assets)
    finally:
        if tmp is not None:
            documents.KillDocument(tmp)

    found = []
    for a in assets:
        name = a.get("assetname") or ""
        if not name or "://" in name or os.path.isabs(name):
            continue  # chemin absolu ou URL : la texture ne bouge pas
        candidates = [a.get("filename") or "",
                      os.path.join(src_dir, name),
                      os.path.join(src_dir, "tex", name)]
        for c in candidates:
            if c and os.path.isabs(c) and os.path.isfile(c) and norm(c).startswith(tex_dir + os.sep):
                if norm(c) not in [norm(f) for f in found]:
                    found.append(c)
                break
    return found


def copy_tex(files, src_dir, dest_dir):
    """Copie en conservant la sous-arborescence de tex/. N'écrase jamais.
    Renvoie (copiés, ignorés car déjà présents)."""
    copied, skipped = 0, 0
    for f in files:
        target = os.path.join(dest_dir, os.path.relpath(f, src_dir))
        if os.path.exists(target):
            skipped += 1
            continue
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(f, target)
        copied += 1
    return copied, skipped


def open_c4d(path):
    if not os.path.exists(path):
        gui.MessageDialog("Fichier introuvable :\n" + path)
        return
    doc = find_open_doc(path)
    if doc:
        documents.SetActiveDocument(doc)  # déjà ouvert : on bascule dessus
    else:
        documents.LoadFile(path)
    c4d.EventAdd()


def open_folder(path):
    if sys.platform == "win32":
        os.startfile(path)
    else:
        storage.ShowInFinder(path, True)


# ---------- Tableaux (TreeView à colonnes) ----------
class Row(object):
    def __init__(self, i, cells, data):
        self.i = i
        self.cells = cells
        self.data = data


# Couleur de la ligne sélectionnée (première constante disponible selon la version)
def _sel_color():
    for name in ("COLOR_BG_HIGHLIGHT", "COLOR_BGFOCUS", "COLOR_TEXTFOCUS"):
        if hasattr(c4d, name):
            return getattr(c4d, name)
    return c4d.Vector(0.25, 0.4, 0.6)


class Table(gui.TreeViewFunctions):
    def __init__(self, headers, on_select, on_double):
        self.headers = headers
        self.rows = []
        self.sel = None
        self.tree = None  # TreeView associé, renseigné à la construction
        self.on_select = on_select
        self.on_double = on_double

    def set_rows(self, rows):
        self.sel = rows[0] if rows else None  # première ligne présélectionnée
        # Un TreeView vide affiche « ??? » : on garde une ligne vide, non sélectionnable
        self.rows = rows or [Row(0, [""] * len(self.headers), None)]

    def GetFirst(self, root, ud):
        return self.rows[0] if self.rows else None  # vide seulement avant le premier scan

    def GetDown(self, root, ud, obj):
        return None

    def GetNext(self, root, ud, obj):
        return self.rows[obj.i + 1] if obj.i + 1 < len(self.rows) else None

    def GetPred(self, root, ud, obj):
        return self.rows[obj.i - 1] if obj.i > 0 else None

    def GetId(self, root, ud, obj):
        return obj.i

    def IsOpened(self, root, ud, obj):
        return False

    def IsSelected(self, root, ud, obj):
        return obj is self.sel

    def _set_sel(self, obj):
        if obj is self.sel:
            return
        self.sel = obj
        if self.tree:
            self.tree.Refresh()  # redessine la surbrillance
        self.on_select()

    def Select(self, root, ud, obj, mode):
        if obj is not None and obj.data is None:
            return  # ligne vide
        if mode in (c4d.SELECTION_NEW, c4d.SELECTION_ADD):
            self._set_sel(obj)
        elif mode == c4d.SELECTION_SUB and obj is self.sel:
            self._set_sel(None)

    def DeselectAll(self, root, ud):
        self._set_sel(None)

    def MouseDown(self, root, ud, obj, col, mouseinfo, rightButton):
        # Clic dans la zone vide sous les lignes : désélection, comme dans AE
        if (obj is None or obj.data is None) and not rightButton:
            self._set_sel(None)
            return True
        return False

    def GetName(self, root, ud, obj):
        return obj.cells[0]

    def GetColumnWidth(self, root, ud, obj, col, area):
        return max(area.DrawGetTextWidth(obj.cells[col]),
                   area.DrawGetTextWidth(self.headers[col])) + 16

    def GetLineHeight(self, root, ud, obj, col, area):
        return area.DrawGetFontHeight() + 6

    def DrawCell(self, root, ud, obj, col, drawinfo, bgColor):
        area = drawinfo["frame"]
        x, y = drawinfo["xpos"], drawinfo["ypos"]
        w, h = drawinfo["width"], drawinfo["height"]
        if obj is self.sel:
            # Bande continue : chaque cellule déborde sur l'espace entre colonnes,
            # la dernière va jusqu'au bord droit du tableau
            right = area.GetWidth() if col == len(self.headers) - 1 else x + w + 4
            area.DrawSetPen(_sel_color())
            area.DrawRectangle(max(0, x - 4), y, right, y + h)
        else:
            area.DrawSetPen(bgColor)
            area.DrawRectangle(x, y, x + w, y + h)
        area.DrawSetTextCol(c4d.COLOR_TEXT, c4d.COLOR_TRANS)
        area.DrawText(obj.cells[col], x + 4, y + (h - area.DrawGetFontHeight()) // 2)

    def DoubleClick(self, root, ud, obj, col, mouseinfo):
        if obj is not None and obj.data is not None:
            self.on_double(obj)
        return True


# ---------- Fenêtre ----------
ID_REFRESH, ID_PATH = 1000, 1001
ID_TREE_PROJ, ID_TREE_FILES = 1010, 1011
ID_OPEN_FOLDER, ID_OPEN_FILE = 1020, 1021
ID_VERSION, ID_STAGE, ID_DUP = 1030, 1031, 1032
ID_STATUS = 1040


class HomepageDialog(gui.GeDialog):
    def __init__(self):
        super(HomepageDialog, self).__init__()
        self.cfg = {}
        self.t_proj = Table(["Client", "Projet", "Étape", "Modifié"],
                            self.on_project_change, self.on_project_double)
        self.t_files = Table(["Fichier", "Étape", "Version", "Modifié"],
                             lambda: None, lambda row: open_c4d(row.data["path"]))
        self.tree_proj = self.tree_files = None

    # --- Construction ---
    def _add_tree(self, gid, table):
        bc = c4d.BaseContainer()
        bc.SetInt32(c4d.TREEVIEW_BORDER, c4d.BORDER_THIN_IN)
        for key in ("TREEVIEW_HAS_HEADER", "TREEVIEW_HIDE_LINES", "TREEVIEW_ALTERNATE_BG",
                    "TREEVIEW_NOENTERRENAME", "TREEVIEW_RESIZE_HEADER", "TREEVIEW_NO_MULTISELECT"):
            if hasattr(c4d, key):
                bc.SetBool(getattr(c4d, key), True)
        tree = self.AddCustomGui(gid, c4d.CUSTOMGUI_TREEVIEW, "",
                                 c4d.BFH_SCALEFIT | c4d.BFV_TOP, 300, LIST_H, bc)
        layout = c4d.BaseContainer()
        for i in range(len(table.headers)):
            layout.SetInt32(i, c4d.LV_USER)
        tree.SetLayout(len(table.headers), layout)
        for i, title in enumerate(table.headers):
            tree.SetHeaderText(i, title)
        table.tree = tree
        tree.SetRoot(None, table, None)
        return tree

    def CreateLayout(self):
        self.SetTitle("Homepage")

        # Tout le contenu dans un groupe collé en haut : la place en trop reste dessous
        self.GroupBegin(0, c4d.BFH_SCALEFIT | c4d.BFV_TOP, cols=1)
        self.GroupBorderSpace(8, 8, 8, 8)
        self.GroupSpace(0, 6)

        self.GroupBegin(0, c4d.BFH_SCALEFIT, cols=2)
        self.GroupSpace(4, 0)
        self.AddButton(ID_REFRESH, c4d.BFH_LEFT, initw=26, name="↻")
        self.AddButton(ID_PATH, c4d.BFH_SCALEFIT, name="")
        self.GroupEnd()

        self.tree_proj = self._add_tree(ID_TREE_PROJ, self.t_proj)
        self.tree_files = self._add_tree(ID_TREE_FILES, self.t_files)

        self.GroupBegin(0, c4d.BFH_LEFT, cols=2)
        self.AddButton(ID_OPEN_FOLDER, c4d.BFH_LEFT, name="Ouvrir le dossier")
        self.AddButton(ID_OPEN_FILE, c4d.BFH_LEFT, name="Ouvrir le fichier")
        self.GroupEnd()

        self.GroupBegin(0, c4d.BFH_LEFT, cols=3)
        self.AddButton(ID_VERSION, c4d.BFH_LEFT, name="Nouvelle version")
        self.AddButton(ID_STAGE, c4d.BFH_LEFT, name="Étape suivante")
        self.AddButton(ID_DUP, c4d.BFH_LEFT, name="Dupliquer…")
        self.GroupEnd()

        self.AddStaticText(ID_STATUS, c4d.BFH_SCALEFIT, name="")
        self.GroupEnd()
        return True

    def InitValues(self):
        self.refresh()
        return True

    # --- Données ---
    def refresh(self):
        self.cfg = load_config()  # relit le JSON à chaque scan
        root = self.cfg.get("root")
        ok = bool(root) and os.path.isdir(root)
        self.SetString(ID_PATH, root if ok else "Cliquer pour choisir le dossier à scanner")
        projects = []
        if not ok:
            self.SetString(ID_STATUS, "Aucun dossier sélectionné")
        else:
            t0 = time.time()
            projects = scan(root, {str(s).lower() for s in self.cfg.get("skip", [])})
            nc = sum(p["conflicts"] for p in projects)
            self.SetString(ID_STATUS, "%d projet(s) scanné(s) en %.1f s%s" % (
                len(projects), time.time() - t0, " — %d conflit(s)" % nc if nc else ""))
        rows = [Row(i, [p["client"], p["name"],
                        p["stage"] + ("  (!) conflit" if p["conflicts"] else ""),
                        fmt(p["last"])], p)
                for i, p in enumerate(projects)]
        self.t_proj.set_rows(rows)
        self.tree_proj.Refresh()
        self.on_project_change()

    def choose_root(self):
        path = storage.LoadDialog(type=c4d.FILESELECTTYPE_ANYTHING,
                                  title="Dossier des projets en cours",
                                  flags=c4d.FILESELECT_DIRECTORY,
                                  def_path=self.cfg.get("root", ""))
        if path:
            cfg = load_config()
            cfg["root"] = path
            save_config(cfg)
            self.refresh()

    def selected_project(self):
        return self.t_proj.sel.data if self.t_proj.sel else None

    def selected_file(self):
        return self.t_files.sel.data if self.t_files.sel else None

    def on_project_change(self):
        p = self.selected_project()
        items = latest_by_stage(self.cfg, p["items"]) if p else []
        rows = [Row(i, [("[conflit] " if it["conflict"] else "") + os.path.basename(it["path"]),
                        it["stage"], it["version"], fmt(it["mtime"])], it)
                for i, it in enumerate(items)]
        self.t_files.set_rows(rows)
        self.tree_files.Refresh()

    def on_project_double(self, row):
        if row.data["latest"]:
            open_c4d(row.data["latest"]["path"])

    # --- Actions ---
    def rel(self, path):
        p = self.selected_project()
        r = os.path.relpath(path, p["folder"]) if p else path
        return r.replace("\\", "/")

    def action_source(self, need_parse):
        it = self.selected_file()
        if not it:
            gui.MessageDialog("Sélectionne d'abord un fichier dans la liste du bas.")
            return None
        if it["conflict"]:
            gui.MessageDialog("C'est une copie de conflit Synology : règle d'abord le conflit.")
            return None
        if need_parse and not it["info"]:
            gui.MessageDialog("Le nom ne suit pas le schéma date_client_projet_etape_version :\n"
                              + os.path.basename(it["path"]))
            return None
        return it

    def create_from(self, it, dest, title, note="", before=None):
        if os.path.exists(dest):
            gui.MessageDialog("Ce fichier existe déjà :\n" + self.rel(dest))
            return
        doc = find_open_doc(it["path"])
        msg = "%s\n\nDe :     %s\nVers :  %s" % (title, self.rel(it["path"]), self.rel(dest))
        if doc:
            msg += "\n\nFichier ouvert : « Enregistrer sous » (les modifications en cours sont incluses)."
        if note:
            msg += "\n\n" + note
        if not gui.QuestionDialog(msg + "\n\nContinuer ?"):
            return
        try:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            if before:
                before()
            if doc:
                if not documents.SaveDocument(doc, dest, c4d.SAVEDOCUMENTFLAGS_NONE,
                                              c4d.FORMAT_C4DEXPORT):
                    gui.MessageDialog("Enregistrement impossible :\n" + dest)
                    return
                doc.SetDocumentPath(os.path.dirname(dest))
                doc.SetDocumentName(os.path.basename(dest))
                documents.SetActiveDocument(doc)
                c4d.EventAdd()
            else:
                shutil.copy2(it["path"], dest)
                open_c4d(dest)
        except OSError as e:
            gui.MessageDialog("Opération impossible :\n%s" % e)
            return
        self.refresh()

    def new_version(self):
        it = self.action_source(True)
        if not it:
            return
        info = it["info"]
        dest = free_file(os.path.dirname(it["path"]), info, info["stage"], info["version"] + 1)
        self.create_from(it, dest, "Nouvelle version")

    def next_stage(self):
        it = self.action_source(True)
        if not it:
            return
        info = it["info"]
        stages = self.cfg["c4d_stages"]
        idx = stage_index(self.cfg, info["stage"])
        if idx < 0:
            gui.MessageDialog("L'étape « %s » n'est pas dans c4d_stages :\n%s"
                              % (info["stage"], config_path()))
            return
        if idx >= len(stages) - 1:
            gui.MessageDialog("« %s » est déjà la dernière étape." % info["stage"])
            return
        nxt = stages[idx + 1]
        folder = os.path.join(self.selected_project()["folder"], *nxt["folder"].split("/"))
        dest = free_file(folder, info, nxt["name"], 1)

        src_dir = os.path.dirname(it["path"])
        try:
            tex = collect_tex(it["path"], find_open_doc(it["path"]))
        except OSError as e:
            gui.MessageDialog("Analyse des textures impossible :\n%s" % e)
            return
        if tex:
            note = ("%d texture(s) utilisée(s) de tex/ seront copiée(s) vers %s/tex.\n"
                    "Les textures situées ailleurs ne bougent pas."
                    % (len(tex), self.rel(os.path.dirname(dest))))
        else:
            note = "Aucune texture à copier depuis tex/."

        result = {}

        def before():
            result["copied"], result["skipped"] = copy_tex(tex, src_dir, os.path.dirname(dest))

        self.create_from(it, dest, "Passer à l'étape « %s »" % nxt["name"], note, before)
        if result.get("skipped"):
            gui.MessageDialog("%d texture(s) copiée(s), %d déjà présente(s) dans la destination "
                              "et laissée(s) telle(s) quelle(s)." % (result["copied"], result["skipped"]))

    def duplicate(self):
        it = self.action_source(False)
        if not it:
            return
        name = os.path.splitext(os.path.basename(it["path"]))[0].lower()
        while True:
            name = gui.RenameDialog(name)
            if not name:
                return
            name = re.sub(r"\.c4d$", "", name, flags=re.I)
            if NAME_RULE.match(name):
                break
            gui.MessageDialog("Nom invalide : minuscules, chiffres, « _ » et « - » uniquement.")
        self.create_from(it, os.path.join(os.path.dirname(it["path"]), name + ".c4d"), "Dupliquer")

    def Command(self, cid, msg):
        it, p = self.selected_file(), self.selected_project()
        if cid == ID_REFRESH:
            self.refresh()
        elif cid == ID_PATH:
            self.choose_root()
        elif cid == ID_OPEN_FILE and it:
            open_c4d(it["path"])
        elif cid == ID_OPEN_FOLDER and (it or p):
            open_folder(os.path.dirname(it["path"]) if it else p["folder"])
        elif cid == ID_VERSION:
            self.new_version()
        elif cid == ID_STAGE:
            self.next_stage()
        elif cid == ID_DUP:
            self.duplicate()
        return True


# ---------- Enregistrement du plugin ----------
class HomepageCommand(c4d.plugins.CommandData):
    dialog = None

    def Execute(self, doc):
        if self.dialog is None:
            self.dialog = HomepageDialog()
        return self.dialog.Open(c4d.DLG_TYPE_ASYNC, pluginid=PLUGIN_ID, defaultw=520, defaulth=480)

    def RestoreLayout(self, sec_ref):
        # Permet à la fenêtre dockée de revenir avec le layout au démarrage
        if self.dialog is None:
            self.dialog = HomepageDialog()
        return self.dialog.Restore(pluginid=PLUGIN_ID, secret=sec_ref)


if __name__ == "__main__":
    c4d.plugins.RegisterCommandPlugin(id=PLUGIN_ID, str="Homepage", info=0, icon=None,
                                      help="Projets en cours", dat=HomepageCommand())
