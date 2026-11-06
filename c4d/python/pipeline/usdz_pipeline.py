r"""
Traite un lot de fichiers .usdz : nettoyage, sauvegarde avec assets, export FBX.

Un seul script dont le comportement change selon la façon dont il est lancé.

Utilisation :
  - GUI (Script Manager, C4D ouvert normalement) :
      - popup au démarrage pour choisir le dossier source
      - fenêtre flottante déplaçable avec bouton de rendu d'aperçu de la vue
        actuelle (cadrage manuel), ou passage au fichier suivant sans rendu
  - Headless (avec c4dpy) : archivage seul, sans popup ni rendu (pas de
    viewport disponible). Aucun fallback implicite, l'argument est obligatoire :
      & c4dpy.exe usdz_pipeline.py "chemin\vers\fichier.usdz"    (1 fichier)
      & c4dpy.exe usdz_pipeline.py "chemin\vers\dossier"         (tout le dossier)
    Sans argument, ou si le chemin donné n'existe pas, le script s'arrête avec
    un message d'erreur clair.
    C'est ce que fait run_batch.ps1 : un process c4dpy frais par fichier, pour
    éviter l'accumulation mémoire/corruption sur de gros lots.

Sortie (dans les deux modes) :
  OUTPUT_ROOT = <dossier source>\usdz_output
  Log         = OUTPUT_ROOT\_logs\usdz_pipeline_<mode>_<timestamp>.log

Étapes pour chaque fichier :
  1. Ouvre le fichier
  2. Copie le .usdz source dans OUTPUT_ROOT\<nom>\
  3. Nettoie la hiérarchie (logique de cleanUSDZ.py)
  4. Save Project with Assets
  5. Sélectionne le Null racine
  6. Exporte en FBX
  7. Supprime les fichiers intermédiaires signalés par C4D
  8. GUI seulement : rendu d'aperçu optionnel de la vue actuelle, enregistré
     en OUTPUT_ROOT\<nom>.png
"""

import c4d
import os
import sys
import re
import glob
import shutil
import datetime
import ctypes
import msvcrt
import tempfile
from urllib.parse import urlparse
from urllib.request import url2pathname

FBX_EXPORT_ID = 1026370

DELETE_INTERMEDIATE_FILES = True
INTERMEDIATE_FILE_PATTERN = re.compile(r"newly file was not removed: '(file:///[^']+)'")

# --- Reglages du rendu d'apercu (GUI uniquement) ---
PREVIEW_XRES = 1920
PREVIEW_YRES = 1080
RENDER_SETTINGS_TEMPLATE = None
PREVIEW_USE_VIEWPORT_RENDERER = True
PREVIEW_VIEW_OVERRIDES = {
    c4d.BASEDRAW_DISPLAYFILTER_GRID: 0,          # Workplane
    c4d.BASEDRAW_DISPLAYFILTER_WORLDAXIS: 0,     # World Axis
    c4d.BASEDRAW_DISPLAYFILTER_HORIZON: 0,       # Horizon
    c4d.BASEDRAW_DISPLAYFILTER_HUD: 0,           # HUD
    c4d.BASEDRAW_DISPLAYFILTER_NULL: 0,          # Null
    c4d.BASEDRAW_DISPLAYFILTER_SPLINE: 0,        # Spline
    c4d.BASEDRAW_DISPLAYFILTER_OBJECTHANDLES: 0, # Axis
    c4d.BASEDRAW_DISPLAYFILTER_HANDLES: 0,       # Handles
}


def is_gui_session():
    """True si lance depuis C4D en interface graphique normale (script manager), False en headless (c4dpy).
    Source : https://developers.maxon.net/forum/post/61212"""

    return c4d.GeGetVersionType() == c4d.VERSIONTYPE_CINEMA4D


class _NullStream:
    """Flux muet, utilise si sys.stdout est indisponible (certains contextes du Script Manager n'ont pas de vraie console)."""

    def write(self, data):
        pass

    def flush(self):
        pass


class Tee:
    """Duplique chaque écriture vers plusieurs flux (ex: console + fichier log).

    _tee_marker sert à se reconnaitre d'un run a l'autre du Script Manager en GUI :
    celui-ci ré-execute tout le texte du script à chaque lancement, donc Tee est une classe différente en memoire à chaque run :
    un isinstance(sys.stdout, Tee) rate systématiquement un Tee crée par un run précédent.
    Un attribut marqueur, lui, est détectable quelle que soit la classe qui l'a posé."""

    _tee_marker = True

    def __init__(self, *streams):
        self._streams = streams

    def write(self, data):
        for s in self._streams:
            s.write(data)
            s.flush()

    def flush(self):
        for s in self._streams:
            s.flush()


class NativeStdoutCapture:
    """
    Capture la sortie standard au niveau OS pendant le bloc `with`, pas seulement au niveau Python.
    Nécessaire car les messages natifs de C4D (ex. "newly file was not removed") ne passent pas forcement par sys.stdout.

    Redirige à la fois le descripteur CRT (os.dup2) et le handle Windows natif (SetStdHandle), selon le chemin que C4D emprunte.
    """

    STD_OUTPUT_HANDLE = -11

    def __enter__(self):
        sys.stdout.flush()
        self._tmp = tempfile.TemporaryFile(mode="w+b")
        self._tmp_fd = self._tmp.fileno()

        self._saved_fd = os.dup(1)
        os.dup2(self._tmp_fd, 1)

        self._kernel32 = ctypes.windll.kernel32
        self._saved_handle = self._kernel32.GetStdHandle(self.STD_OUTPUT_HANDLE)
        tmp_handle = msvcrt.get_osfhandle(self._tmp_fd)
        self._kernel32.SetStdHandle(self.STD_OUTPUT_HANDLE, tmp_handle)

        self.output = ""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        sys.stdout.flush()
        self._kernel32.SetStdHandle(self.STD_OUTPUT_HANDLE, self._saved_handle)
        os.dup2(self._saved_fd, 1)
        os.close(self._saved_fd)

        self._tmp.seek(0)
        self.output = self._tmp.read().decode("utf-8", errors="replace")
        self._tmp.close()

        sys.stdout.write(self.output)
        sys.stdout.flush()
        return False


def cleanup_intermediate_files(captured_output):
    """Parse la sortie capturée et supprime (ou liste) exactement les fichiers que C4D a lui-même signalés comme non supprimés."""

    paths = [
        url2pathname(urlparse(uri).path)
        for uri in INTERMEDIATE_FILE_PATTERN.findall(captured_output)
    ]
    if not paths:
        return

    print(f"[NETTOYAGE] {len(paths)} fichier(s) intermédiaire(s) signalé(s) par C4D")
    for p in paths:
        if not os.path.exists(p):
            print(f"  [DEJA ABSENT] {p}")
            continue
        if DELETE_INTERMEDIATE_FILES:
            try:
                os.remove(p)
                print(f"  [SUPPRIME] {p}")
            except OSError as e:
                print(f"  [ERREUR] {p} : {e}")
        else:
            print(f"  [DRY RUN] a supprimer : {p}")


def find_root_null_by_name(doc, name):
    op = doc.GetFirstObject()
    while op:
        if op.GetName() == name and op.GetType() == c4d.Onull:
            return op
        op = op.GetNext()
    return None


def clean_usdz(doc):
    """Portage direct de cleanUSDZ.py."""

    selected_objects = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_CHILDREN)
    selected_nulls = [o for o in selected_objects if o.GetType() == c4d.Onull]

    doc.StartUndo()
    created_root_null = None

    def cleanup_null(root_null):
        all_geometry = []
        nulls_to_delete = []

        def scan_hierarchy(obj):
            while obj:
                if obj != root_null:
                    if obj.GetType() != c4d.Onull:
                        all_geometry.append({'obj': obj, 'matrix': obj.GetMg()})
                    else:
                        nulls_to_delete.append(obj)
                scan_hierarchy(obj.GetDown())
                obj = obj.GetNext()

        scan_hierarchy(root_null.GetDown())

        for item in all_geometry:
            obj = item['obj']
            mg = item['matrix']
            doc.AddUndo(c4d.UNDOTYPE_CHANGE, obj)
            obj.Remove()
            obj.InsertUnder(root_null)
            obj.SetMg(mg)

        for n in reversed(nulls_to_delete):
            doc.AddUndo(c4d.UNDOTYPE_DELETE, n)
            n.Remove()

    if selected_nulls:
        for null in selected_nulls:
            cleanup_null(null)
    else:
        doc_name = doc.GetDocumentName()
        clean_name = os.path.splitext(doc_name)[0] or "scene_nettoyee"

        root_null = c4d.BaseObject(c4d.Onull)
        root_null.SetName(clean_name)
        doc.InsertObject(root_null)
        doc.AddUndo(c4d.UNDOTYPE_NEWOBJ, root_null)
        created_root_null = root_null

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

    return created_root_null


def process_file(usdz_path, output_root, keep_open=False):
    """
    Traite un fichier : copie, nettoyage, save with assets, export FBX, nettoyage des intermediaires.

    keep_open=False (headless) : ferme le document à la fin, ne retourne rien.

    keep_open=True (GUI) : laisse le document ouvert et visible dans l'UI,
    retourne (doc, null_obj, out_dir, filename) pour que l'appelant (la fenetre flottante) prenne le relai pour le rendu d'apercu.

    Retourne None si le fichier n'a pas pu être ouvert.
    """

    filename = os.path.splitext(os.path.basename(usdz_path))[0]
    out_dir = os.path.join(output_root, filename)
    os.makedirs(out_dir, exist_ok=True)

    shutil.copy2(usdz_path, os.path.join(out_dir, os.path.basename(usdz_path)))

    doc = c4d.documents.LoadDocument(usdz_path, c4d.SCENEFILTER_NONE)
    if doc is None:
        print(f"[ERREUR] impossible d'ouvrir {filename}")
        return None

    if keep_open:
        c4d.documents.InsertBaseDocument(doc)
    c4d.documents.SetActiveDocument(doc)

    root_null = clean_usdz(doc)

    with NativeStdoutCapture() as cap:
        assets = []
        missing_assets = []
        save_flags = (
            c4d.SAVEPROJECT_ASSETS
            | c4d.SAVEPROJECT_SCENEFILE
            | c4d.SAVEPROJECT_USEDOCUMENTNAMEASFILENAME
        )
        ok_save = c4d.documents.SaveProject(doc, save_flags, out_dir + os.sep, assets, missing_assets)

        null_obj = root_null or find_root_null_by_name(doc, filename)
        if null_obj:
            doc.SetActiveObject(null_obj, c4d.SELECTION_NEW)

        fbx_path = os.path.join(out_dir, filename + ".fbx")
        ok_fbx = c4d.documents.SaveDocument(
            doc, fbx_path, c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST, FBX_EXPORT_ID
        )

    if not ok_save:
        print(f"[ATTENTION] Echec sauvegarde projet pour {filename}")
    if missing_assets:
        print(f"[ATTENTION] Assets manquants pour {filename}: {missing_assets}")
    if not null_obj:
        print(f"[ATTENTION] Null '{filename}' introuvable")
    if not ok_fbx:
        print(f"[ATTENTION] Echec export FBX pour {filename}")

    cleanup_intermediate_files(cap.output)

    if keep_open:
        c4d.EventAdd()
        return doc, null_obj, out_dir, filename

    c4d.documents.KillDocument(doc)
    print(f"[OK] {filename} traite")
    return None


# =====================================================================
# Mode GUI : popup de dossier + fenêtre flottante avec rendu d'apercu
# =====================================================================

class BatchDialog(c4d.gui.GeDialog):
    ID_LABEL = 1000
    ID_BTN_RENDER = 1001
    ID_BTN_SKIP = 1002

    def __init__(self, files, output_root):
        self.files = files
        self.output_root = output_root
        self.index = -1
        self.current_doc = None
        self.current_filename = None
        self.current_out_dir = None

    def CreateLayout(self):
        self.SetTitle("Batch USDZ -> FBX")
        self.AddStaticText(self.ID_LABEL, c4d.BFH_SCALEFIT, name="Initialisation...")
        self.AddButton(self.ID_BTN_RENDER, c4d.BFH_SCALEFIT, name="Rendu apercu de la vue actuelle")
        self.AddButton(self.ID_BTN_SKIP, c4d.BFH_SCALEFIT, name="Fichier suivant (sans rendu)")
        return True

    def InitValues(self):
        self.ProcessNext()
        return True

    def ProcessNext(self):
        if self.current_doc:
            c4d.documents.KillDocument(self.current_doc)
            self.current_doc = None

        self.index += 1
        if self.index >= len(self.files):
            self.SetString(self.ID_LABEL, "Terminé -- tu peux fermer cette fenetre.")
            self.Enable(self.ID_BTN_RENDER, False)
            self.Enable(self.ID_BTN_SKIP, False)
            return

        usdz_path = self.files[self.index]
        result = process_file(usdz_path, self.output_root, keep_open=True)

        if result is None:
            self.SetString(self.ID_LABEL, f"[ERREUR] fichier ignoré -- passage au suivant")
            self.ProcessNext()
            return

        doc, null_obj, out_dir, filename = result
        self.current_doc = doc
        self.current_filename = filename
        self.current_out_dir = out_dir

        self.SetString(
            self.ID_LABEL,
            f"[{self.index + 1}/{len(self.files)}] {filename} -- cadre la vue, "
            f"puis choisis une action"
        )

    def RenderPreview(self):
        doc = self.current_doc
        if doc is None:
            return

        bd = doc.GetActiveBaseDraw()
        if bd is None:
            print("[ATTENTION] Pas de BaseDraw actif, rendu d'apercu annulé")
            return

        previous_scene_cam = bd.GetSceneCamera(doc)
        editor_cam = bd.GetEditorCamera()
        temp_cam = editor_cam.GetClone()
        temp_cam.SetName("__preview_cam__")
        doc.InsertObject(temp_cam)
        temp_cam.SetMg(bd.GetMg())
        bd.SetSceneCamera(temp_cam)

        previous_view_values = {pid: bd[pid] for pid in PREVIEW_VIEW_OVERRIDES}
        for pid, value in PREVIEW_VIEW_OVERRIDES.items():
            bd[pid] = value
        c4d.EventAdd()

        template_rd = None
        temp_rd = None
        previous_rd = doc.GetActiveRenderData()

        try:
            if RENDER_SETTINGS_TEMPLATE and os.path.exists(RENDER_SETTINGS_TEMPLATE):
                tpl_doc = c4d.documents.LoadDocument(RENDER_SETTINGS_TEMPLATE, c4d.SCENEFILTER_NONE)
                if tpl_doc and tpl_doc.GetActiveRenderData():
                    template_rd = tpl_doc.GetActiveRenderData().GetClone()
                if tpl_doc:
                    c4d.documents.KillDocument(tpl_doc)

            if template_rd:
                doc.InsertRenderData(template_rd)
                doc.SetActiveRenderData(template_rd)
                rd = template_rd
                temp_rd = template_rd
            elif PREVIEW_USE_VIEWPORT_RENDERER:
                rd = c4d.documents.RenderData()
                rd[c4d.RDATA_RENDERENGINE] = c4d.RDATA_RENDERENGINE_PREVIEWHARDWARE
                rd[c4d.RDATA_XRES] = PREVIEW_XRES
                rd[c4d.RDATA_YRES] = PREVIEW_YRES
                vp = c4d.BaseList2D(c4d.RDATA_RENDERENGINE_PREVIEWHARDWARE)
                vp[c4d.VP_PREVIEWHARDWARE_DISPLAYFILTER_HUD] = 0
                rd.InsertVideoPostLast(vp)
                doc.InsertRenderData(rd)
                doc.SetActiveRenderData(rd)
                temp_rd = rd
            else:
                rd = previous_rd.GetClone()
                rd[c4d.RDATA_XRES] = PREVIEW_XRES
                rd[c4d.RDATA_YRES] = PREVIEW_YRES

            xres = int(rd[c4d.RDATA_XRES])
            yres = int(rd[c4d.RDATA_YRES])
            bmp = c4d.bitmaps.MultipassBitmap(xres, yres, c4d.COLORMODE_RGB)
            bmp.AddChannel(True, True)

            result = c4d.documents.RenderDocument(
                doc, rd.GetDataInstance(), bmp,
                c4d.RENDERFLAGS_EXTERNAL | c4d.RENDERFLAGS_SHOWERRORS
            )

            if result != c4d.RENDERRESULT_OK:
                print(f"[ATTENTION] Rendu d'apercu echoue pour {self.current_filename} (code {result})")
                return

            preview_path = os.path.join(self.output_root, self.current_filename + ".png")
            bmp.Save(preview_path, c4d.FILTER_PNG)
            print(f"[APERCU] enregistre : {preview_path}")
        finally:
            for pid, value in previous_view_values.items():
                bd[pid] = value
            if temp_rd:
                doc.SetActiveRenderData(previous_rd)
                temp_rd.Remove()
            bd.SetSceneCamera(previous_scene_cam)
            temp_cam.Remove()
            c4d.EventAdd()

    def Command(self, id, msg):
        if id == self.ID_BTN_RENDER:
            self.RenderPreview()
            self.ProcessNext()
        elif id == self.ID_BTN_SKIP:
            self.ProcessNext()
        return True


dlg = None  # référence globale : évite que la fenetre async soit ramassée par le garbage collector et se ferme toute seule


def run_gui():
    global dlg

    source_folder = c4d.storage.LoadDialog(
        title="Choisir le dossier contenant les .usdz",
        flags=c4d.FILESELECT_DIRECTORY
    )
    if not source_folder:
        return  # popup annulé

    output_root = os.path.join(source_folder, "usdz_output")

    # Même emplacement de log qu'en headless, quel que soit le mode de lancement : OUTPUT_ROOT\_logs\
    log_folder = os.path.join(output_root, "_logs")
    setup_logging(log_folder, "gui")

    files = glob.glob(os.path.join(source_folder, "*.usdz"))
    if not files:
        c4d.gui.MessageDialog(f"Aucun .usdz trouvé dans {source_folder}")
        return

    dlg = BatchDialog(files, output_root)
    dlg.Open(c4d.DLG_TYPE_ASYNC, defaultw=420, defaulth=100)


# =====================================================================
# Mode headless (c4dpy) : archivage seul, pas de rendu
# =====================================================================

def run_headless():
    if len(sys.argv) <= 1:
        print(
            "[ERREUR] Aucun argument fourni. Lance via run_batch.ps1, ou "
            "passe en argument soit un fichier .usdz, soit un dossier qui "
            "en contient."
        )
        sys.exit(1)

    arg = sys.argv[1]

    if os.path.isfile(arg):
        if not arg.lower().endswith(".usdz"):
            print(f"[ERREUR] Le fichier fourni n'est pas un .usdz : {arg}")
            sys.exit(1)
        source_folder = os.path.dirname(arg)
        usdz_files = [arg]
    elif os.path.isdir(arg):
        source_folder = arg
        usdz_files = glob.glob(os.path.join(source_folder, "*.usdz"))
        if not usdz_files:
            print(f"[ERREUR] Aucun fichier .usdz trouvé dans {source_folder}")
            sys.exit(1)
    else:
        print(f"[ERREUR] Chemin introuvable (ni fichier ni dossier) : {arg}")
        sys.exit(1)

    output_root = os.path.join(source_folder, "usdz_output")

    # Headless : potentiellement plusieurs .log (un par process lancé par run_batch.ps1)
    # -> dans un sous-dossier, pour ne pas polluer le dossier source avec un fichier par asset.
    log_folder = os.path.join(output_root, "_logs")
    log_path = setup_logging(log_folder, "headless")

    try:
        print(f"{len(usdz_files)} fichier(s) .usdz trouve(s)")
        for f in usdz_files:
            process_file(f, output_root, keep_open=False)
    finally:
        print(f"[LOG] ecrit dans {log_path}")


# =====================================================================
# Logging commun
# =====================================================================

def setup_logging(log_dir, mode_tag):
    os.makedirs(log_dir, exist_ok=True)
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = os.path.join(log_dir, f"usdz_pipeline_{mode_tag}_{timestamp}.log")
    log_file = open(log_path, "w", encoding="utf-8")

    # Le Script Manager garde l'état Python d'un run à l'autre dans la même session GUI :
    # repartir d'une base saine si sys.stdout est déjà enveloppé par un run précédent
    # (détection par attribut, pas par isinstance -- voir docstring de Tee).

    if getattr(sys.stdout, "_tee_marker", False) or sys.stdout is None:
        console_stream = _NullStream()
    else:
        console_stream = sys.stdout
    sys.stdout = Tee(console_stream, log_file)
    print(f"[LOG] écrit dans {log_path}")
    return log_path


def main():
    if is_gui_session():
        run_gui()
    else:
        run_headless()


if __name__ == "__main__":
    main()
