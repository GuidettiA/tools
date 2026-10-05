"""
Décale les clés d'animation d'un nombre de frames donné.

Traite les clés sélectionnées, ou toutes les clés des objets sélectionnés.

Utilisation :
  1. Lancer le script depuis le Script Manager (Extensions > Script Manager)
  2. Saisir le décalage et choisir le mode dans la boîte de dialogue

Modes (case à cocher dans la boîte de dialogue) :
  - Décoché (défaut) : traite les clés SÉLECTIONNÉES dans la Timeline/Dope
    Sheet, sur toute la scène (objets, tags, matériaux).
  - Coché : ignore la sélection de clés et traite TOUTES les clés des
    objets actuellement sélectionnés dans l'Object Manager (+ leurs tags).

Valeur positive -> décalage vers la fin de la timeline.
Valeur négative -> décalage vers le début de la timeline.

Systèmes d'animation couverts :
  1. CTrack/CKey classique (objets, tags, matériaux non node-based).
  2. Node graph via NimbusBaseRef (matériaux node-based type OpenPBR/
     Redshift, et objets Scene Nodes qui exposent un CTrack via ce
     mécanisme -- voir « Limitation connue » ci-dessous pour ce qui n'est
     PAS couvert).

     Séquence API (confirmée fonctionnelle en C4D 2026) :
       handler = owner.GetNimbusRef(space_id)
       graph   = handler.GetGraph()
       root    = graph.GetViewRoot()
       entities = root.GetInnerNodes(maxon.NODE_KIND.ALL_MASK, False, None)
       pour chaque "vrai" node (kind == maxon.NODE_KIND.NODE) :
           surrogate = handler.FindOrCreateCorrespondingBaseList(entity.GetPath())
           pour chaque CTrack du surrogate (surrogate.GetFirstCTrack()/.GetNext()) :
               -> track prêt à être décalé (shift_keys_on_track n'a besoin
                  que de track.GetCurve(), pas de son DescID)

     NB : une approche passant par chaque PORT du node
     (handler.GetDescID(port) -> surrogate.FindCTrack(did)) a été
     abandonnée : confirmée incomplète en prod sur une track Color
     (seul le port "R" aboutissait à une CTrack sur 82 ports scannés,
     alors que G et B existaient déjà sur le même surrogate). Lister
     directement toutes les CTracks du surrogate est à la fois plus
     simple et plus fiable.

     Le graphe Scene Nodes est PARTAGÉ par tous les objets qui le
     référencent (contrairement à un graphe de matériau, propre à chaque
     matériau même si le space_id est identique entre matériaux). Il n'est
     donc parcouru en entier qu'une seule fois par run, peu importe le
     nombre d'objets qui le référencent (voir `processed_shared_spaces`).

Paramètres vectoriels (Color R/G/B, Position/Scale X/Y/Z...) :
  Un paramètre vectoriel est stocké comme plusieurs CTrack sœurs (une par
  composante). Le Dope Sheet affiche ces composantes comme une seule
  ligne mais ne pose en pratique le bit de sélection QUE sur la première
  composante -- d'où un bug où seule la piste "R" (ou "X") bougeait. Le
  script regroupe les tracks composantes d'un même paramètre (même owner
  réel) et applique l'union des frames sélectionnées, toutes composantes
  confondues, à tout le groupe (en mode "clés sélectionnées"
  uniquement -- CTrack.IsSynchronized() s'est révélé peu fiable pour
  distinguer un vecteur "lié" d'un vecteur désynchronisé et n'est plus
  utilisé comme filtre). Voir vector_group_key() / shift_vector_group().

Limitation connue :
  Certains objets de type "Scene Node Generator" (ex. un générateur de
  spline custom basé sur les Scene Nodes) peuvent afficher un losange
  rouge de clé standard dans l'Attribute Manager pour un paramètre sans
  que ce paramètre soit porté par une CTrack accessible -- confirmé par
  deux méthodes indépendantes (parcours complet du graphe partagé, et
  FindCTrack() avec le DescID exact tel que vu par GetDescription()).
  Ce type d'animation est vraisemblablement stocké comme donnée de
  courbe native embarquée dans un node du graphe, un mécanisme différent
  de CTrack/CKey, non couvert par ce script. Voir le Readme du dépôt pour
  le détail de l'investigation.
"""

import c4d
from c4d import gui

try:
    import maxon
except ImportError:
    maxon = None

ID_OFFSET = 1000
ID_LIMIT_TO_SELECTED_OBJ = 1001
ID_OK = 1002
ID_CANCEL = 1003

# Passe à True pour un log détaillé par track traité (utile pour diagnostiquer
# un écart entre les clés sélectionnées visuellement et celles réellement
# détectées/déplacées). Laisser à False en usage normal.
DEBUG = False

# Si DEBUG_FILTER est non vide, seuls les logs dont le chemin hiérarchique de
# l'owner contient cette sous-chaîne (insensible à la casse) sont affichés --
# pratique pour isoler un seul objet sur une grosse scène sans être noyé.
DEBUG_FILTER = ""


def _debug_match(owner_label):
    if not DEBUG_FILTER:
        return True
    return DEBUG_FILTER.lower() in owner_label.lower()


# CKey n'a pas de méthode GetSelectionState() ni de GetBit() simple (il
# n'hérite pas de BaseList2D). La sélection d'une clé se lit via GetNBit()
# avec les flags du Timeline.
#
# NB: on ne teste QUE l'instance TL1 (Dope Sheet). NBIT_TL1_SELECT2
# (F-Curve Manager) s'est révélé peu fiable en prod : confirmé qu'il peut
# rester actif sur la totalité des clés d'une courbe (ex: Position.Z) alors
# que seules quelques clés étaient réellement sélectionnées dans le Dope
# Sheet sur une courbe voisine (Position.X) -- probablement un bit resté
# "collé" après une sélection complète antérieure dans le F-Curve Manager.
# Les instances TL2/TL3/TL4 sont un mécanisme legacy multi-fenêtres
# quasiment jamais utilisé et peuvent aussi porter des bits résiduels.
_KEY_SELECTION_BITS = [
    c4d.NBIT_TL1_SELECT,
]


def is_key_selected(key):
    """Une clé est considérée sélectionnée si l'un des bits de sélection
    Dope Sheet retenus est actif."""
    for bit in _KEY_SELECTION_BITS:
        if key.GetNBit(bit):
            return True
    return False


def vector_group_key(track):
    """Si `track` est l'une des tracks composantes d'un paramètre
    multi-composantes (vecteur Position/Scale X/Y/Z, Color R/G/B...),
    retourne une clé de regroupement identifiant ce paramètre (commune à
    toutes ses composantes, indépendante de laquelle) -- sinon None.

    Un tel paramètre est stocké comme plusieurs CTrack SŒURS (une par
    composante), dont le DescID ne diffère que sur son DERNIER niveau
    (ex: c4d.VECTOR_X / VECTOR_Y / VECTOR_Z pour un vecteur -- mais on ne
    fixe pas la liste des ids possibles en dur : on regroupe simplement
    par préfixe de DescID commun, voir note ci-dessous). Le Dope Sheet
    affiche ces composantes comme une seule ligne, mais ne pose en
    pratique le bit de sélection QUE sur la première composante -- d'où
    le bug "seule la piste R (ou X) bouge". Voir `shift_vector_group()`.

    NB : une première version ne reconnaissait comme "composante" qu'un
    dernier niveau de DescID valant VECTOR_X/Y/Z. En pratique, confirmé
    en prod, ça ne suffisait pas à regrouper une track Color de matériau
    (bug persistant). On se base donc uniquement sur la STRUCTURE du
    DescID (au moins 2 niveaux, préfixe identique entre tracks) plutôt
    que sur la valeur exacte du dernier niveau -- le regroupement par
    owner + préfixe reste sûr : des tracks sans sœur partageant le même
    préfixe restent seules (groupe de taille 1, traitées individuellement
    comme avant, voir main())."""
    try:
        did = track.GetDescID()
    except Exception:
        return None
    if did is None:
        return None
    depth = did.GetDepth()
    if depth < 2:
        return None
    try:
        prefix = tuple((did[i].id, did[i].dtype) for i in range(depth - 1))
    except Exception:
        return None
    return prefix


def get_hierarchy_path(obj):
    """Chemin complet parent > ... > obj, pour lever toute ambiguïté dans
    les logs (deux objets peuvent porter le même nom à des profondeurs
    différentes de la hiérarchie)."""
    names = []
    node = obj
    while node:
        names.append(node.GetName())
        node = node.GetUp()
    return " > ".join(reversed(names))


def collect_objects_recursive(op):
    """Retourne un objet + tous ses enfants (récursif)."""
    objs = []
    while op:
        objs.append(op)
        objs += collect_objects_recursive(op.GetDown())
        op = op.GetNext()
    return objs


def get_owners_full_scene(doc):
    """Tous les objets + tags de la scène, plus la liste des matériaux.

    Les matériaux vivent dans une liste séparée du document
    (doc.GetFirstMaterial()), jamais traversée par un parcours de
    doc.GetFirstObject() -- il faut donc les ajouter explicitement."""
    owners = []
    for obj in collect_objects_recursive(doc.GetFirstObject()):
        owners.append(obj)
        owners += obj.GetTags()

    mat = doc.GetFirstMaterial()
    while mat:
        owners.append(mat)
        mat = mat.GetNext()

    return owners


def get_owners_selected_objects(doc):
    """Objets sélectionnés dans l'Object Manager (sans descendre dans les
    enfants) + leurs tags."""
    owners = []
    selected = doc.GetActiveObjects(c4d.GETACTIVEOBJECTFLAGS_NONE)
    for obj in selected:
        owners.append(obj)
        owners += obj.GetTags()
    return owners


def get_node_graph_ctracks(owner, processed_shared_spaces=None, debug_owner_label=None):
    """Retourne une liste de (surrogate_base_list, ctrack, label) pour
    toutes les CTracks accessibles via le système de node graph (Scene
    Nodes / matériaux node-based) porté par `owner`.

    Fonctionne pour tout BaseList2D (objet, matériau...) qui expose
    GetAllNimbusRefs()/GetNimbusRef(). Renvoie une liste vide immédiatement
    pour les owners sans aucun node graph (la grande majorité).

    `processed_shared_spaces`, si fourni, est un `set()` partagé entre
    appels successifs sur toute la scène : il évite de reparcourir le
    graphe Scene Nodes (potentiellement plusieurs milliers d'entités) une
    fois par objet qui le référence, puisque ce graphe est unique et
    partagé pour tout le document.

    `debug_owner_label`, si fourni et que DEBUG est actif et matche
    DEBUG_FILTER, active un log détaillé par node/surrogate.

    NB : une version précédente retrouvait les CTracks en passant par
    chaque PORT du node (handler.GetDescID(port) -> surrogate.FindCTrack(did)).
    Ca s'est révélé incomplet en prod sur une track Color de matériau
    node-based : un seul port (R) menait effectivement à une CTrack alors
    que G et B existaient très probablement sur le même surrogate --
    simplement non atteintes par cette résolution port-par-port (diagnostic
    confirmé : sur 82 ports scannés, un seul DescID a mené à une CTrack).
    En réalité shift_keys_on_track() n'a besoin que de la CTrack elle-même
    (via GetCurve()), jamais de son DescID -- la résolution par port était
    donc un détour inutile ET incomplet. On énumère maintenant directement
    TOUTES les CTracks portées par le surrogate via GetFirstCTrack(), comme
    pour n'importe quel autre owner (pas besoin de DescID du tout)."""
    results = []
    node_debug = bool(DEBUG and debug_owner_label and _debug_match(debug_owner_label))
    if maxon is None:
        return results

    # Les tags n'ont quasiment jamais de node graph propre, et il peut y en
    # avoir des centaines dans une grosse scène : on les exclut pour éviter
    # un GetAllNimbusRefs() coûteux (~5ms/appel, mesuré) appelé des
    # centaines de fois pour rien.
    if isinstance(owner, c4d.BaseTag):
        return results
    if not hasattr(owner, "GetAllNimbusRefs"):
        return results

    try:
        nimbus_refs = owner.GetAllNimbusRefs()
    except Exception:
        return results
    if not nimbus_refs:
        return results

    for space_id, _ in nimbus_refs:
        # Le graphe Scene Nodes est PARTAGÉ par tous les objets qui le
        # référencent (contrairement aux matériaux, dont chaque instance a
        # son propre graphe même si leur space_id -- ex. l'id "redshift"
        # pour OpenPBR -- est identique entre matériaux). Pour un space_id
        # Scene Nodes déjà traité, on saute directement au lieu de
        # reparcourir ce graphe pour chaque objet qui le référence.
        is_scene_nodes_space = False
        try:
            is_scene_nodes_space = (space_id == maxon.NodeSpaceIdentifiers.SceneNodes)
        except Exception:
            is_scene_nodes_space = False

        if is_scene_nodes_space and processed_shared_spaces is not None:
            if space_id in processed_shared_spaces:
                continue

        try:
            handler = owner.GetNimbusRef(space_id)
        except Exception:
            continue
        if not handler:
            continue

        try:
            graph = handler.GetGraph()
            root = graph.GetViewRoot()
            entities = root.GetInnerNodes(maxon.NODE_KIND.ALL_MASK, False, None)
        except Exception:
            continue

        # Garde-fou : si deux entités du graphe se résolvent vers le même
        # surrogate (improbable mais pas exclu), on ne veut pas compter ses
        # CTracks deux fois.
        seen_surrogates = set()

        for entity in entities or []:
            try:
                if entity.GetKind() != maxon.NODE_KIND.NODE:
                    continue
            except Exception:
                continue

            try:
                surrogate = handler.FindOrCreateCorrespondingBaseList(entity.GetPath())
            except Exception:
                continue
            if surrogate is None:
                continue
            if id(surrogate) in seen_surrogates:
                continue
            seen_surrogates.add(id(surrogate))

            try:
                node_name = entity.GetPath().ToString() if hasattr(entity.GetPath(), "ToString") else str(entity.GetPath())
            except Exception:
                node_name = "?"

            found_here = 0
            track = surrogate.GetFirstCTrack()
            while track:
                results.append((surrogate, track, "[node]{}".format(node_name)))
                found_here += 1
                track = track.GetNext()

            if node_debug and found_here:
                names = []
                t = surrogate.GetFirstCTrack()
                while t:
                    names.append(t.GetName())
                    t = t.GetNext()
                print("  [node_entity] node={} surrogate={} -> {} CTrack(s) : {}".format(
                    node_name, surrogate.GetName() if hasattr(surrogate, "GetName") else surrogate,
                    found_here, names))

        if is_scene_nodes_space and processed_shared_spaces is not None:
            processed_shared_spaces.add(space_id)

    return results


def shift_keys_on_track(track, offset, fps, offset_time, only_selected_keys, doc, owner_label):
    """Décale les clés d'un CTrack. Retourne le nombre de clés déplacées."""
    curve = track.GetCurve()
    if not curve:
        return 0

    key_count = curve.GetKeyCount()
    indices_to_move = []

    for i in range(key_count):
        key = curve.GetKey(i)
        if only_selected_keys:
            if is_key_selected(key):
                indices_to_move.append(i)
        else:
            indices_to_move.append(i)

    if not indices_to_move:
        return 0

    log_this = DEBUG and _debug_match(owner_label)
    if log_this:
        track_name = track.GetName()
        all_frames = [curve.GetKey(i).GetTime().GetFrame(fps) for i in range(key_count)]
        sel_frames = [curve.GetKey(i).GetTime().GetFrame(fps) for i in indices_to_move]
        print("[shift_keys] {} / track={} / {} clé(s) sélectionnée(s) sur {} au total".format(
            owner_label, track_name, len(indices_to_move), key_count))
        print("  toutes les clés du track (frames) : {}".format(all_frames))
        print("  clés détectées comme sélectionnées : {}".format(sel_frames))

    key_count_before = key_count

    doc.AddUndo(c4d.UNDOTYPE_CHANGE, track)

    # On traite les clés dans l'ordre qui évite qu'une clé déjà décalée ne
    # vienne perturber la recherche/le tri des clés pas encore traitées
    # pendant le retri interne de la courbe déclenché par SetTime().
    indices_to_move.sort(reverse=(offset > 0))

    moved = 0
    for i in indices_to_move:
        key = curve.GetKey(i)
        if key is None:
            continue
        old_frame = key.GetTime().GetFrame(fps)
        new_time = key.GetTime() + offset_time
        key.SetTime(curve, new_time)
        moved += 1
        if log_this:
            # Relit la clé après coup : une clé verrouillée ou fusionnée
            # avec une autre ne bougera pas réellement même si SetTime()
            # n'a levé aucune erreur.
            check = curve.GetKey(i)
            actual_frame = check.GetTime().GetFrame(fps) if check else None
            expected_frame = new_time.GetFrame(fps)
            if actual_frame != expected_frame:
                print("  !! clé frame {} -> attendu {} mais lu {} après SetTime (verrou ou fusion probable)".format(
                    old_frame, expected_frame, actual_frame))

    if log_this:
        key_count_after = curve.GetKeyCount()
        if key_count_after != key_count_before:
            print("  !! le nombre de clés sur ce track a changé pendant le déplacement : {} -> {} (fusion probable)".format(
                key_count_before, key_count_after))

    return moved


def shift_vector_group(tracks, offset, fps, offset_time, only_selected_keys, doc, owner_label):
    """Décale ensemble les tracks composantes (X/Y/Z) d'un même paramètre
    vectoriel (voir `vector_group_key`).

    En mode "clés sélectionnées", le Dope Sheet ne pose le bit de
    sélection que sur la première composante alors que visuellement
    l'utilisateur sélectionne la ligne entière du paramètre (ex: Color
    R/G/B, confirmé en prod). On calcule donc l'UNION des frames
    sélectionnées sur toutes les composantes du groupe, puis on déplace
    les clés à ces frames sur CHAQUE composante qui en possède une.

    NB : une première version gatait ce comportement derrière
    `CTrack.IsSynchronized()`, en pensant que ce flag distinguait les
    vecteurs "liés" dans le Dope Sheet des vecteurs volontairement
    désynchronisés. En pratique, confirmé en prod sur une track Color de
    matériau, `IsSynchronized()` ne reflète pas la sélection Dope Sheet et
    bloquait le regroupement en tombant systématiquement en traitement
    individuel (reproduisant exactement le bug d'origine). Le
    regroupement est donc désormais appliqué dès que plusieurs tracks
    composantes d'un même paramètre sont détectées sur le même owner, que
    `IsSynchronized()` soit vrai ou non.

    En mode "toutes les clés" (only_selected_keys=False), le regroupement
    n'apporte rien (chaque track bouge de toute façon intégralement) --
    chaque track est alors traitée individuellement.

    Retourne le nombre de clés déplacées."""
    curves = [t.GetCurve() for t in tracks]
    if any(c is None for c in curves):
        moved = 0
        for t in tracks:
            moved += shift_keys_on_track(t, offset, fps, offset_time, only_selected_keys, doc, owner_label)
        return moved

    if not only_selected_keys:
        moved = 0
        for t in tracks:
            moved += shift_keys_on_track(t, offset, fps, offset_time, only_selected_keys, doc, owner_label)
        return moved

    selected_frames = set()
    for curve in curves:
        for i in range(curve.GetKeyCount()):
            key = curve.GetKey(i)
            if is_key_selected(key):
                selected_frames.add(key.GetTime().GetFrame(fps))

    if not selected_frames:
        return 0

    log_this = DEBUG and _debug_match(owner_label)
    if log_this:
        print("[shift_vector_group] {} / groupe de {} track(s) synchronisée(s) / union des frames sélectionnées : {}".format(
            owner_label, len(tracks), sorted(selected_frames)))

    for t in tracks:
        doc.AddUndo(c4d.UNDOTYPE_CHANGE, t)

    moved = 0
    reverse = offset > 0
    for curve in curves:
        indices = [i for i in range(curve.GetKeyCount())
                   if curve.GetKey(i).GetTime().GetFrame(fps) in selected_frames]
        indices.sort(reverse=reverse)
        for i in indices:
            key = curve.GetKey(i)
            if key is None:
                continue
            new_time = key.GetTime() + offset_time
            key.SetTime(curve, new_time)
            moved += 1

    return moved


class ShiftKeysDialog(gui.GeDialog):
    """Boîte de dialogue : décalage en frames + mode de traitement."""

    def __init__(self):
        self.offset = 0
        self.limit_to_selected_obj = False
        self.canceled = True

    def CreateLayout(self):
        self.SetTitle("Décaler les clés d'animation")

        self.GroupBegin(0, c4d.BFH_SCALEFIT, 1, 0, "", 0)
        self.GroupBorderSpace(10, 10, 10, 10)

        self.AddStaticText(0, c4d.BFH_LEFT, name="Décalage en frames (négatif = vers le début) :")
        self.AddEditNumberArrows(ID_OFFSET, c4d.BFH_SCALEFIT)

        self.AddStaticText(0, c4d.BFH_LEFT, name="")  # espacement
        self.AddCheckbox(ID_LIMIT_TO_SELECTED_OBJ, c4d.BFH_LEFT, 0, 0,
                          "Traiter toutes les clés des objets sélectionnés\n(ignore la sélection de clés dans la Timeline)")

        self.GroupEnd()

        self.GroupBegin(0, c4d.BFH_SCALEFIT, 2, 0, "", 0)
        self.GroupBorderSpace(10, 5, 10, 10)
        self.AddButton(ID_OK, c4d.BFH_SCALEFIT, name="OK")
        self.AddButton(ID_CANCEL, c4d.BFH_SCALEFIT, name="Annuler")
        self.GroupEnd()

        return True

    def InitValues(self):
        self.SetLong(ID_OFFSET, 0)
        self.SetBool(ID_LIMIT_TO_SELECTED_OBJ, False)
        return True

    def Command(self, id, msg):
        if id == ID_OK:
            self.offset = self.GetLong(ID_OFFSET)
            self.limit_to_selected_obj = self.GetBool(ID_LIMIT_TO_SELECTED_OBJ)
            self.canceled = False
            self.Close()
        elif id == ID_CANCEL:
            self.canceled = True
            self.Close()
        return True


def main():
    dlg = ShiftKeysDialog()
    dlg.Open(c4d.DLG_TYPE_MODAL, defaultw=380, defaulth=140)

    if dlg.canceled:
        return

    offset = dlg.offset
    if offset == 0:
        return

    limit_to_selected_obj = dlg.limit_to_selected_obj

    doc = c4d.documents.GetActiveDocument()
    fps = doc.GetFps()
    offset_time = c4d.BaseTime(offset, fps)

    if limit_to_selected_obj:
        owners = get_owners_selected_objects(doc)
        if not owners:
            gui.MessageDialog("Aucun objet sélectionné dans l'Object Manager.")
            return
    else:
        owners = get_owners_full_scene(doc)

    doc.StartUndo()

    moved_count = 0
    # Partagé entre tous les owners pour éviter de reparcourir le graphe
    # Scene Nodes (partagé/global) plusieurs fois -- voir
    # get_node_graph_ctracks().
    processed_shared_spaces = set()

    # -- Collecte de toutes les tracks (sans encore les déplacer) --
    # Nécessaire pour pouvoir regrouper les tracks composantes d'un même
    # paramètre vectoriel (Color R/G/B, Position X/Y/Z...) AVANT de les
    # traiter -- voir vector_group_key()/shift_vector_group(). On garde le
    # "vrai" owner de chaque track (le surrogate pour les tracks node
    # graph) car le regroupement doit se faire par paramètre ET par objet.
    items = []  # (true_owner, track, owner_label)

    for owner in owners:
        if isinstance(owner, c4d.BaseTag):
            host = owner.GetObject()
            path = get_hierarchy_path(host) if host else "?"
            owner_label = "{} > [Tag]{}".format(path, owner.GetName())
        elif isinstance(owner, c4d.BaseMaterial):
            owner_label = "Materials > {}".format(owner.GetName())
        else:
            owner_label = get_hierarchy_path(owner)

        # -- 1. Chemin classique CTrack --
        track = owner.GetFirstCTrack()
        while track:
            items.append((owner, track, owner_label))
            track = track.GetNext()

        # -- 2. Chemin node graph (matériaux node-based + objets Scene
        # Nodes qui exposent un CTrack via ce mécanisme -- voir
        # LIMITATION CONNUE en tête de fichier pour ce qui n'est pas
        # couvert) --
        for surrogate, node_track, node_label in get_node_graph_ctracks(owner, processed_shared_spaces, debug_owner_label=owner_label):
            items.append((surrogate, node_track, "{} {}".format(owner_label, node_label)))

    # -- Regroupement par (owner réel, paramètre vectoriel) --
    groups = {}
    singles = []
    for true_owner, track, owner_label in items:
        gkey = vector_group_key(track)
        if gkey is None:
            singles.append((track, owner_label))
            continue
        groups.setdefault((id(true_owner), gkey), []).append((track, owner_label))

    for track, owner_label in singles:
        moved_count += shift_keys_on_track(
            track, offset, fps, offset_time,
            only_selected_keys=not limit_to_selected_obj,
            doc=doc,
            owner_label=owner_label
        )

    for group_items in groups.values():
        group_tracks = [t for t, _ in group_items]
        group_label = group_items[0][1]
        if DEBUG and _debug_match(group_label) and len(group_tracks) >= 2:
            print("[vector_group] {} / {} composante(s) groupée(s) : {}".format(
                group_label, len(group_tracks), [t.GetName() for t in group_tracks]))
        if len(group_tracks) < 2:
            # Composante seule trouvée sans ses sœurs (cas rare) : rien à
            # grouper, traitement individuel classique.
            moved_count += shift_keys_on_track(
                group_tracks[0], offset, fps, offset_time,
                only_selected_keys=not limit_to_selected_obj,
                doc=doc,
                owner_label=group_label
            )
            continue
        moved_count += shift_vector_group(
            group_tracks, offset, fps, offset_time,
            only_selected_keys=not limit_to_selected_obj,
            doc=doc,
            owner_label=group_label
        )

    doc.EndUndo()
    c4d.EventAdd()

    # Force un rafraîchissement du Timeline/Dope Sheet : EventAdd() seul ne
    # suffit pas toujours à rafraîchir tous les panneaux ouverts.
    c4d.gui.GeUpdateUI()
    current_time = doc.GetTime()
    doc.SetTime(current_time)
    c4d.EventAdd()

    gui.MessageDialog("{} clé(s) déplacée(s) de {} frame(s).".format(moved_count, offset))


if __name__ == '__main__':
    main()
