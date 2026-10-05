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

### Configuration

Seule la constante `FBX_EXPORT_ID` en tête de `usdz_pipeline.py` est à revérifier après une mise à jour majeure de C4D.

### Sortie

Pour chaque `<nom>.usdz`, un dossier `<dossier source>\usdz_output\<nom>\` contenant :
- `<nom>.usdz` (copie du fichier source)
- `<nom>.c4d` + son dossier `tex\` (assets)
- `<nom>.fbx`

En GUI, un rendu d'aperçu optionnel est enregistré en `<dossier source>\usdz_output\<nom>.png`.

Logs dans `<dossier source>\usdz_output\_logs\` : un `.log` horodaté par session ou par fichier traité, et un `run_<timestamp>_echecs.txt` de `run_batch.ps1` listant les fichiers dont le process `c4dpy` a planté (dans `<dossier source>\_logs\`, uniquement généré s'il y a des échecs).
