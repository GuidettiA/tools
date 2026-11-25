# c4d (tools/c4d)

Outils python pour Cinema 4D : Script Manager + scripts métier


## Structure

```
tools/c4d/
├── user_scripts_manager.py      # Basé sur le travail de Mike Udin : https://mikeudin.net/
├── Readme.md
├── python/                      # dossier à ajouter dans le Script Manager (sous-dossiers = sous-menus)
│   ├── animation/               # offsetKeys
│   ├── camera/                  # cameraRigg, cameraBake
│   ├── geometry/                # splitObj, ObjToMtx, ObjToPoint
│   ├── instances/               # instancer, createInstance, createXref
│   ├── objects/                 # alignToWorld, setCoordinates, renameChildren, toggleVisibility
│   └── pipeline/                # usdz_pipeline, cleanUSDZ, splitByCamera
└── shell/
    └── run_batch.ps1            # orchestrateur c4dpy (un process par fichier)
```


## Déploiement sur une nouvelle machine

1. **Cloner le dépôt** à l'endroit souhaité.

2. **Copier `user_scripts_manager.py`** dans le dossier scripts de C4D pour qu'il soit lu au démarrage :
   ```
   C:\Users\<utilisateur>\AppData\Roaming\Maxon\<version_c4d>\library\scripts\
   ```

3. **Ajouter le dossier `python/`** en tant que dossier custom : lancer le Script Manager dans C4D → **"Add Scripts Folder"** → sélectionner `..\python\`.


## Batch export USDZ

Traite en masse un dossier de fichiers `.usdz` : nettoyage de la hiérarchie (logique héritée du script `cleanUSDZ.py`), sauvegarde du projet avec ses assets, export FBX, copie du `.usdz` source et nettoyage des fichiers texture intermédiaires générés par l'import USD + rendu du viewport (optionnel).

### Fichiers concernés

- **`usdz_pipeline.py`** — script unique dont le comportement s'adapte à la façon dont il est lancé :
  - **GUI** (C4D ouvert normalement, Script Manager) : une popup demande le dossier source, puis une fenêtre flottante déplaçable propose soit un rendu d'aperçu de la vue actuelle (cadrage manuel dans le viewport), soit de passer directement au fichier suivant.
  - **Headless** (avec `c4dpy.exe`) : archivage seul, sans popup ni rendu (pas de viewport disponible) — clean, save with assets, export FBX. Le dossier ou le fichier à traiter est passé en argument ; sans argument valide, le script s'arrête avec un message d'erreur clair plutôt que de deviner un dossier par défaut.
- **`run_batch.ps1`** — orchestrateur générique (pas spécifique à ce script) : relance un process `c4dpy.exe` **frais par fichier** trouvé dans un dossier, plutôt que de tout traiter dans un seul process : `c4dpy` accumule des fuites mémoire sur de gros lots et finit par planter ; isoler chaque fichier dans son propre process limite un plantage à ce seul fichier. Fonctionne avec n'importe quel script c4dpy conçu sur le modèle "un fichier = un argument = un process".

### Utilisation

**GUI** : ouvrir C4D normalement → Script Manager → ouvrir `usdz_pipeline.py` → Execute. La popup de choix du dossier s'affiche automatiquement.

> **Rendu d'aperçu = GUI uniquement.** En headless (`c4dpy`, donc aussi via `run_batch.ps1`), aucun `.png` n'est produit : pas de viewport à cadrer. Pour les aperçus, passer par le Script Manager.

**Headless via l'orchestrateur** (recommandé pour un lot complet) :
```powershell
powershell -ExecutionPolicy Bypass -File "tools\c4d\shell\run_batch.ps1"
```
Sans paramètres, `run_batch.ps1` demande interactivement : le dossier des fichiers à traiter, leur extension (`.usdz`), le dossier contenant `usdz_pipeline.py` (soit `python\pipeline\` ; le script complète le nom du fichier automatiquement, ou propose un choix s'il y en a plusieurs), et le dossier d'installation de Cinema 4D (le chemin de `c4dpy.exe` est complété automatiquement). Tout est validé avant de lancer le premier fichier, pour éviter de boucler sur une erreur de chemin.

Les mêmes valeurs peuvent être passées directement en paramètres :
```powershell
.\run_batch.ps1 -C4dpyPath "C:\...\c4dpy.exe" -ScriptPath "...\usdz_pipeline.py" -SourceFolder "..." -Extension ".usdz"
```

Pour tester sur un seul fichier ou un dossier sans passer par l'orchestrateur :
```powershell
& "C:\Program Files\Maxon Cinema 4D 2026\c4dpy.exe" "tools\c4d\python\pipeline\usdz_pipeline.py" "chemin\vers\fichier.usdz"
& "C:\Program Files\Maxon Cinema 4D 2026\c4dpy.exe" "tools\c4d\python\pipeline\usdz_pipeline.py" "chemin\vers\dossier"
```

**Depuis un PowerShell administrateur** : une session élevée ne voit pas les lecteurs réseau (`Z:`, `Y:`…) montés par la session normale — `Z:\tools\...` y est introuvable. Utiliser le chemin UNC complet, pour le script comme pour les dossiers demandés ensuite :
```powershell
powershell -ExecutionPolicy Bypass -File "\\192.168.1.20\shared\tools\c4d\shell\run_batch.ps1"
```
Ou lancer depuis un PowerShell non élevé, où `Z:\` fonctionne normalement. Même limite en SSH : la session ne reconnecte pas les lecteurs mémorisés (état « Non disponible » dans `net use`) faute d'identifiants Samba.

### Configuration

- `FBX_EXPORT_ID` en tête de `usdz_pipeline.py` : à revérifier après une mise à jour majeure de C4D.
- `DELETE_INTERMEDIATE_FILES` : passer à `False` pour lister sans supprimer les fichiers intermédiaires signalés par C4D (utile pour diagnostiquer des textures manquantes).

### Matériaux et textures

> **Utiliser Cinema 4D 2026, pas 2027 (GUI comme headless).** L'importeur USD de C4D 2027 échoue sur les UV des meshes : `Illegal state: UV indices invalid [ousd-import-mesh.cpp(112)]` (popup en GUI, ligne de log en headless).
>
> - **Conséquence** : aucune géométrie n'est créée. Seule la hiérarchie des groupes USD arrive, sous forme de Nulls vides ; les matériaux sont créés mais assignés à rien (`[DIAG] … 0 tag(s) matériau après import`).
> - **Piège** : le script ne plante pas et affiche `[OK]`, mais comme le nettoyage supprime les Nulls, les `.c4d` et `.fbx` produits sont **vides**. Tout lot traité en 2027 est à supprimer et relancer en 2026.
> - **Fichiers concernés** : constaté (novembre 2026) sur des USDZ Sketchfab convertis depuis du glTF (hiérarchie `Sketchfab_model` / `GLTF_SceneRootNode`). Les mêmes fichiers passent sans erreur en 2026 : régression de l'importeur 2027, pas un problème des fichiers.
> - **Avant de rebasculer sur une version 2027.x** : tester un seul fichier en GUI ; pas de popup UV et des objets polygonaux (pas seulement des Nulls) dans le gestionnaire d'objets = OK.

- Le `.usdz` est ouvert avec `SCENEFILTER_OBJECTS | SCENEFILTER_MATERIALS` (demande explicite des matériaux ; l'ancienne valeur `SCENEFILTER_NONE` fonctionnait aussi en 2026).
- Le nettoyage de hiérarchie supprime les Nulls ; les tags matériau qu'ils portaient (binding USD sur un Xform) sont recopiés sur la géométrie avant suppression, dans l'ordre d'héritage C4D.
- Le log contient des lignes `[DIAG]` (nombre de matériaux après import, tags matériau avant/après nettoyage, assets collectés par Save Project with Assets) pour repérer à quelle étape des textures se perdent.

### Sortie

Pour chaque `<nom>.usdz`, un dossier `<dossier source>\usdz_output\<nom>\` contenant :
- `<nom>.usdz` (copie du fichier source)
- `<nom>.c4d` + son dossier `tex\` (assets)
- `<nom>.fbx`

En GUI, un rendu d'aperçu optionnel est enregistré en `<dossier source>\usdz_output\<nom>.png`.

Logs dans `<dossier source>\usdz_output\_logs\` : un `.log` horodaté par session ou par fichier traité, et un `run_<timestamp>_echecs.txt` de `run_batch.ps1` listant les fichiers dont le process `c4dpy` a planté (dans `<dossier source>\_logs\`, uniquement généré s'il y a des échecs).
