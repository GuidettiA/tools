"""
Génère un fichier .c4d par rig caméra présent dans la scène.

Un rig caméra est un null racine contenant une caméra (C4D, Redshift,
Octane ou Arnold).

Utilisation :
  1. Lancer le script
  2. Renseigner la boîte de dialogue (une seule fois pour tous les rigs) :
     dossier de sortie, renommage de la caméra, pattern de nommage
     - le pattern est pré-rempli avec la logique maquette→layout
     - la variable $camera est remplacée par le nom du rig à la sauvegarde

Étapes pour chaque rig :
  1. Duplique le document
  2. Supprime tous les autres rigs caméra et l'objet Stage
  3. Renomme la caméra en "Camera" si l'option est cochée
  4. Calcule l'offset basé sur la première clé du rig
  5. Décale TOUTES les clés de la scène de cet offset
  6. Ajuste la plage temporelle (0 → durée du rig)
  7. Sauvegarde dans le dossier choisi
"""

import c4d
import os
import re

CAMERA_TYPES = {
    c4d.Ocamera,  # Caméra native C4D (5103)
    1057516,      # Redshift RS Camera
    1040504,      # Octane Camera
    1055451,      # Arnold Camera
}


# ---------------------------------------------------------------------------
# Dialog IDs
# ---------------------------------------------------------------------------
TXT_FOLDER       = 101
BTN_BROWSE       = 102
CHK_RENAME_CAM   = 103
BTN_SETUP_OK     = 104
BTN_SETUP_CANCEL = 105
TXT_PATTERN      = 106


# ---------------------------------------------------------------------------
# Naming helpers
# ---------------------------------------------------------------------------

def build_pattern_smart(base_name):
    """
    Construit le pattern pré-rempli à partir du nom du fichier source.
    Ex: "2026-05_DVN Communication_Co2_maquette_v03"
     → "2026-05_DVN Communication_Co2_layout_$camera_01"
    Retourne None si le nom ne correspond pas au pattern attendu.
    """
    pattern = re.compile(
        r'^(.*?)(_maquette)?((?:_[a-zA-Z]+)*?)(_\d+)$',
        re.IGNORECASE
    )
    m = pattern.match(base_name)
    if not m:
        return None
    prefix      = m.group(1)
    maquette    = m.group(2)
    middle      = m.group(3)
    layout_part = "_layout" if maquette else ""
    return f"{prefix}{layout_part}{middle}_$camera_01"


def resolve_pattern(pattern_str, rig_name):
    """Remplace $camera par le nom du rig (espaces → underscore)."""
    safe = rig_name.replace(" ", "_").replace("/", "-")
    return pattern_str.replace("$camera", safe)


# ---------------------------------------------------------------------------
# Scene helpers
# ---------------------------------------------------------------------------

def find_camera(obj):
    """Cherche récursivement la première caméra (tous types) sous obj."""
    while obj:
        if obj.GetType() in CAMERA_TYPES:
            return obj
        result = find_camera(obj.GetDown())
        if result:
            return result
        obj = obj.GetNext()
    return None


def collect_camera_rigs(doc):
    """
    Retourne une liste de (rig_null, camera) pour chaque null racine
    contenant une caméra supportée.
    """
    rigs = []
    obj = doc.GetFirstObject()
    while obj:
        if obj.GetType() == c4d.Onull:
            cam = find_camera(obj.GetDown())
            if cam:
                rigs.append((obj, cam))
        obj = obj.GetNext()
    return rigs


def get_all_tracks_recursive(obj, tracks):
    if obj is None:
        return
    for track in obj.GetCTracks():
        tracks.append(track)
    child = obj.GetDown()
    while child:
        get_all_tracks_recursive(child, tracks)
        child = child.GetNext()


def get_all_tracks_in_doc(doc):
    tracks = []
    def walk(obj):
        while obj:
            get_all_tracks_recursive(obj, tracks)
            tag = obj.GetFirstTag()
            while tag:
                for t in tag.GetCTracks():
                    tracks.append(t)
                tag = tag.GetNext()
            walk(obj.GetDown())
            obj = obj.GetNext()
    walk(doc.GetFirstObject())
    mat = doc.GetFirstMaterial()
    while mat:
        for t in mat.GetCTracks():
            tracks.append(t)
        mat = mat.GetNext()
    return tracks


def get_earliest_key_frame(rig_root, fps):
    tracks = []
    get_all_tracks_recursive(rig_root, tracks)
    earliest = None
    for track in tracks:
        curve = track.GetCurve()
        if curve is None:
            continue
        for i in range(curve.GetKeyCount()):
            f = curve.GetKey(i).GetTime().GetFrame(fps)
            if earliest is None or f < earliest:
                earliest = f
    return earliest


def get_latest_key_frame(rig_root, fps):
    tracks = []
    get_all_tracks_recursive(rig_root, tracks)
    latest = None
    for track in tracks:
        curve = track.GetCurve()
        if curve is None:
            continue
        for i in range(curve.GetKeyCount()):
            f = curve.GetKey(i).GetTime().GetFrame(fps)
            if latest is None or f > latest:
                latest = f
    return latest


def offset_all_keys(doc, offset_frames, fps):
    if offset_frames == 0:
        return
    for track in get_all_tracks_in_doc(doc):
        curve = track.GetCurve()
        if curve is None:
            continue
        for i in range(curve.GetKeyCount() - 1, -1, -1):
            old_frame = curve.GetKey(i).GetTime().GetFrame(fps)
            curve.MoveKey(c4d.BaseTime(old_frame - offset_frames, fps), i)
    doc.SetChanged()


def remove_other_rigs_and_stage(new_doc, keep_rig_name):
    """Supprime tous les rigs caméra sauf keep_rig_name, et le Stage."""
    rigs = collect_camera_rigs(new_doc)
    guids_to_remove = set()
    target_cam = None

    for rig_null, cam in rigs:
        if rig_null.GetName() == keep_rig_name:
            target_cam = cam
        else:
            guids_to_remove.add(rig_null.GetGUID())

    def remove_pass(obj):
        while obj:
            nxt = obj.GetNext()
            if obj.GetType() == c4d.Ostage:
                obj.Remove()
            elif obj.GetGUID() in guids_to_remove:
                obj.Remove()
            else:
                remove_pass(obj.GetDown())
            obj = nxt

    remove_pass(new_doc.GetFirstObject())
    return target_cam



def rename_rig_objects(rig_root, old_name, new_name):
    """
    Remplace recursivement toutes les occurrences de old_name dans les noms
    des objets du rig (null root inclus).
    Ex: old_name="Cam_9", new_name="Camera"
      Cam_9         -> Camera
      Pan_Cam_9     -> Pan_Camera
      Cible_Cam_9   -> Cible_Camera
        Up_Cam_9    -> Up_Camera
        Focus_Cam_9 -> Focus_Camera
    """
    def rename_obj(obj):
        current = obj.GetName()
        if old_name in current:
            obj.SetName(current.replace(old_name, new_name))

    def walk_children(obj):
        """Parcourt les siblings et leurs enfants, sans remonter hors du rig."""
        while obj:
            rename_obj(obj)
            walk_children(obj.GetDown())
            obj = obj.GetNext()

    # Renommer le root lui-meme, puis descendre dans ses enfants uniquement
    rename_obj(rig_root)
    walk_children(rig_root.GetDown())


# ---------------------------------------------------------------------------
# Setup Dialog
# ---------------------------------------------------------------------------

class SetupDialog(c4d.gui.GeDialog):
    """
    Dialog unique : dossier + renommage caméra + pattern de nommage.
    Le pattern est pré-rempli avec la logique maquette→layout et $camera.
    """

    def __init__(self, default_folder, default_pattern, rig_names):
        super().__init__()
        self.default_folder  = default_folder
        self.default_pattern = default_pattern
        self.rig_names       = rig_names   # pour la prévisualisation
        self.out_folder      = None        # None = annulé
        self.rename_cam      = False
        self.pattern         = ""

    def CreateLayout(self):
        self.SetTitle("Split by Camera — Configuration")
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 1, 0)
        self.GroupBorderSpace(12, 12, 12, 12)

        # Dossier
        self.AddStaticText(0, c4d.BFH_LEFT, name="Dossier de destination :")
        self.GroupBegin(0, c4d.BFH_SCALEFIT, 2, 1)
        self.AddEditText(TXT_FOLDER, c4d.BFH_SCALEFIT, initw=400)
        self.SetString(TXT_FOLDER, self.default_folder)
        self.AddButton(BTN_BROWSE, c4d.BFH_RIGHT, name="Parcourir…")
        self.GroupEnd()

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)

        # Pattern
        self.AddStaticText(0, c4d.BFH_LEFT,
            name="Pattern de nommage  ($camera = nom du rig) :")
        self.AddEditText(TXT_PATTERN, c4d.BFH_SCALEFIT, initw=400)
        self.SetString(TXT_PATTERN, self.default_pattern)

        # Prévisualisation
        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)
        self.AddStaticText(0, c4d.BFH_LEFT, name="Prévisualisation :")
        preview = "\n".join(
            f"  {resolve_pattern(self.default_pattern, n)}.c4d"
            for n in self.rig_names
        )
        self.AddMultiLineEditText(200, c4d.BFH_SCALEFIT, initw=400, inith=120)
        self.SetString(200, preview)
        self.Enable(200, False)  # lecture seule

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)

        # Renommage caméra
        self.AddCheckbox(CHK_RENAME_CAM, c4d.BFH_LEFT, initw=0, inith=0,
                         name='Renommer la caméra en "Camera"')
        self.SetBool(CHK_RENAME_CAM, False)

        self.AddSeparatorH(0, c4d.BFH_SCALEFIT)

        # Boutons
        self.GroupBegin(0, c4d.BFH_RIGHT, 2, 1)
        self.AddButton(BTN_SETUP_CANCEL, c4d.BFH_LEFT,  name="Annuler")
        self.AddButton(BTN_SETUP_OK,     c4d.BFH_RIGHT, name="Lancer")
        self.GroupEnd()

        self.GroupEnd()
        return True

    def _refresh_preview(self):
        pat = self.GetString(TXT_PATTERN)
        preview = "\n".join(
            f"  {resolve_pattern(pat, n)}.c4d"
            for n in self.rig_names
        )
        self.SetString(200, preview)

    def Command(self, id, msg):
        if id == TXT_PATTERN:
            self._refresh_preview()

        elif id == BTN_BROWSE:
            folder = c4d.storage.LoadDialog(
                type=c4d.FILESELECTTYPE_ANYTHING,
                title="Choisir le dossier de destination",
                flags=c4d.FILESELECT_DIRECTORY,
                def_path=self.GetString(TXT_FOLDER)
            )
            if folder:
                self.SetString(TXT_FOLDER, folder)

        elif id == BTN_SETUP_OK:
            folder = self.GetString(TXT_FOLDER).strip()
            if not folder or not os.path.isdir(folder):
                c4d.gui.MessageDialog("Dossier invalide ou inexistant.")
                return True
            pat = self.GetString(TXT_PATTERN).strip()
            if not pat:
                c4d.gui.MessageDialog("Le pattern ne peut pas être vide.")
                return True
            self.out_folder = folder
            self.pattern    = pat
            self.rename_cam = self.GetBool(CHK_RENAME_CAM)
            self.Close()

        elif id == BTN_SETUP_CANCEL:
            self.Close()

        return True


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    doc       = c4d.documents.GetActiveDocument()
    fps       = doc.GetFps()
    doc_path  = doc.GetDocumentPath()
    doc_name  = doc.GetDocumentName()
    base_name = os.path.splitext(doc_name)[0]

    if not doc_path:
        c4d.gui.MessageDialog("Sauvegardez le document avant de lancer le script.")
        return

    # --- Collecter les rigs ---
    rigs = collect_camera_rigs(doc)
    if not rigs:
        c4d.gui.MessageDialog(
            "Aucun rig caméra trouvé.\n"
            "(Types supportés : C4D native, Redshift, Octane, Arnold)"
        )
        return

    rig_names = [r[0].GetName() for r in rigs]
    dupes = {n for n in rig_names if rig_names.count(n) > 1}
    if dupes:
        c4d.gui.MessageDialog(
            "⚠️ Plusieurs rigs ont le même nom :\n" +
            "\n".join(f"  • {n}" for n in sorted(dupes)) +
            "\n\nRenommez-les avant de continuer."
        )
        return

    print(f"[split_by_camera] {len(rigs)} rig(s) : {rig_names}")

    # Pattern pré-rempli
    default_pattern = build_pattern_smart(base_name)
    if default_pattern is None:
        # Fallback si le nom ne correspond pas
        default_pattern = f"{base_name}_$camera_01"

    # --- Dialog de setup unique ---
    setup = SetupDialog(doc_path, default_pattern, rig_names)
    setup.Open(c4d.DLG_TYPE_MODAL, defaultw=560, defaulth=350)

    if setup.out_folder is None:
        print("[split_by_camera] Annulé.")
        return

    out_folder = setup.out_folder
    pattern    = setup.pattern
    rename_cam = setup.rename_cam

    print(f"[split_by_camera] Dossier : {out_folder}")
    print(f"[split_by_camera] Pattern : {pattern}")
    print(f"[split_by_camera] Renommer cam : {rename_cam}")

    # --- Boucle ---
    saved_files = []
    for rig_null, rs_cam in rigs:
        rig_name   = rig_null.GetName()
        final_name = resolve_pattern(pattern, rig_name)
        out_path   = os.path.join(out_folder, final_name + ".c4d")

        print(f"\n[split_by_camera] {rig_name} → {final_name}.c4d")

        new_doc    = doc.GetClone(c4d.COPYFLAGS_NONE)
        target_cam = remove_other_rigs_and_stage(new_doc, rig_name)

        # Rig dans le clone pour l'offset (avant renommage éventuel)
        cloned_rigs = collect_camera_rigs(new_doc)
        target_rig  = next((r[0] for r in cloned_rigs if r[0].GetName() == rig_name), None)

        if rename_cam and target_rig:
            rename_rig_objects(target_rig, rig_name, "Camera")

        if target_rig:
            earliest = get_earliest_key_frame(target_rig, fps)
            latest   = get_latest_key_frame(target_rig, fps)
        else:
            earliest = latest = None

        if earliest is not None:
            offset       = earliest
            cam_duration = latest - earliest
        else:
            offset       = 0
            cam_duration = new_doc.GetMaxTime().GetFrame(fps) - new_doc.GetMinTime().GetFrame(fps)

        offset_all_keys(new_doc, offset, fps)
        new_doc.SetMinTime(c4d.BaseTime(0))
        new_doc.SetMaxTime(c4d.BaseTime(cam_duration, fps))
        new_doc.SetTime(c4d.BaseTime(0))

        print(f"  Offset : -{offset} frames | Durée : {cam_duration} frames")

        saved = c4d.documents.SaveDocument(
            new_doc, out_path,
            c4d.SAVEDOCUMENTFLAGS_NONE,
            c4d.FORMAT_C4DEXPORT
        )
        c4d.documents.KillDocument(new_doc)

        if saved:
            saved_files.append(final_name + ".c4d")
            print(f"  ✓ {out_path}")
        else:
            print(f"  ✗ Échec : {out_path}")

    if saved_files:
        c4d.gui.MessageDialog(
            f"Terminé ! {len(saved_files)} fichier(s) créé(s) dans :\n{out_folder}\n\n" +
            "\n".join(f"  • {f}" for f in saved_files)
        )
    else:
        c4d.gui.MessageDialog("Aucun fichier créé.")

    print("\n[split_by_camera] Done.")


if __name__ == "__main__":
    main()