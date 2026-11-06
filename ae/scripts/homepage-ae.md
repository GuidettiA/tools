# Homepage — panneau After Effects des projets en cours

Panneau ScriptUI dockable qui liste les projets en cours au lancement d'After Effects.
Il permet d'ouvrir un projet en un clic et de créer une nouvelle version ou de passer à l'étape suivante sans passer par l'Explorateur.

## Installation

1. Copier `homepage.jsx` dans :
   ```
   C:\Program Files\Adobe\Adobe After Effects <version>\Support Files\Scripts\ScriptUI Panels\
   ```
2. Relancer After Effects.
3. Ouvrir le panneau via **Fenêtre > homepage.jsx**, puis le docker dans l'espace de travail.
4. Cliquer sur le champ du chemin et choisir le dossier racine des projets.

Docké dans l'espace de travail, le panneau scanne le dossier à chaque ouverture d'AE.

## Organisation attendue

### Arborescence

```
<racine>/
└── <client>/
    └── <projet>/
        └── … /*.aep     jusqu'à 4 niveaux de profondeur
```

### Nommage des fichiers

```
date_client_projet_etape_version.aep
```

- **étape** : avant-dernier champ (`maquette`, `animatic`, `animation`).
- **version** : dernier champ, numérique (`01`, `02`… ; `v03` est aussi accepté).

Les nouveaux fichiers créés par le panneau sont toujours en minuscules.
Un fichier hors schéma reste affiché (exemple : `01-2`) ; son étape est alors déduite de son dossier, mais les actions de versionnage lui sont refusées.

### Éléments ignorés au scan

- Dossiers : toujours ignorés (renders, caches, proxys, textures, auto-saves AE), ceux listés dans la clé `skip` de la configuration, et tout dossier commençant par `.` ou `#`.
- Fichiers : auto-saves AE et projets temporaires `tmpAEtoAMEProject*` (envoi vers Media Encoder).

## Interface

| Zone | Rôle |
|---|---|
| ↻ (icône) | Relance le scan et relit le fichier de configuration. |
| Champ du chemin | Affiche le dossier scanné ; un clic permet d'en choisir un autre. |
| Tableau des projets | Client, projet, étape et date du dernier `.aep` modifié. Trié du plus récent au plus ancien. |
| Tableau des fichiers | Une ligne par étape du projet sélectionné, avec uniquement sa dernière version. |
| Ouvrir le dossier | Ouvre dans l'Explorateur le dossier du fichier sélectionné. |
| Ouvrir le fichier | Ouvre le `.aep` sélectionné. |
| Nouvelle version | Voir [Actions](#actions-sur-les-fichiers). |
| Étape suivante | Voir [Actions](#actions-sur-les-fichiers). |
| Dupliquer… | Voir [Actions](#actions-sur-les-fichiers). |
| Ligne d'état | Nombre de projets scannés, durée du scan et nombre de conflits éventuels. |

### Raccourcis

- **Double-clic sur un projet** : ouvre son `.aep` le plus récent (hors copie de conflit).
- **Double-clic sur un fichier** : ouvre ce fichier.

Après un scan, le projet le plus récent et sa dernière version sont présélectionnés : « Ouvrir le fichier » reprend directement le dernier travail.

Si le projet ouvert dans AE a des modifications non enregistrées, AE propose de les sauvegarder avant d'ouvrir un autre projet.

## Actions sur les fichiers

Elles s'appliquent au fichier sélectionné dans le second tableau.

| Action | Exemple | Destination |
|---|---|---|
| Nouvelle version | `…_animatic_01` → `…_animatic_02` | Même dossier |
| Étape suivante | `…_animatic_02` → `…_animation_01` | Dossier de l'étape suivante (créé si besoin) |
| Dupliquer… | Nom libre, prérempli | Même dossier |

Règles communes :

- Une confirmation affiche le fichier source et le fichier cible avant toute action.
- Rien n'est jamais écrasé : si le numéro de version visé existe déjà, le suivant est utilisé.
- Rien n'est supprimé ni déplacé : l'original reste en place.
- Si le fichier source est ouvert dans AE, l'action fait un **Enregistrer sous** : les modifications en cours sont incluses dans le nouveau fichier et AE bascule dessus. Sinon, le fichier est copié puis ouvert.
- Le nom saisi dans « Dupliquer… » doit respecter les conventions : minuscules, chiffres, `_` et `-` uniquement.
- Les copies de conflit et les fichiers hors schéma sont refusés, avec un message explicatif.

## Copies de conflit de synchronisation

Le panneau reconnaît les copies de conflit au format de Synology Drive :

```
<nom>_<poste>_<Mon-JJ-HHMM-AAAA>_Conflict.aep
```

Le panneau les signale :

- `(!) conflit` dans la colonne Étape du projet concerné ;
- préfixe `[conflit]` dans le tableau des fichiers, en fin de liste ;
- total dans la ligne d'état.

Elles ne sont jamais ouvertes par le double-clic sur un projet. La détection suppose que le nom du poste ne contient pas de `_`.

## Configuration

Fichier : `%APPDATA%\petit-studio\homepage.json`, soit `C:\Users\<utilisateur>\AppData\Roaming\petit-studio\homepage.json`.

Il est créé au premier lancement et se modifie à la main. Le bouton ↻ le relit.

```json
{
  "root": "D:\\projets",
  "stages": [
    { "name": "maquette",  "folder": "maquette/ae" },
    { "name": "animatic",  "folder": "animatic/ae" },
    { "name": "animation", "folder": "animation/ae" }
  ],
  "skip": ["temp", "archive"]
}
```

| Clé | Rôle |
|---|---|
| `root` | Dossier scanné. Modifié par le champ du chemin. |
| `stages` | Étapes **dans l'ordre** : « Étape suivante » prend l'entrée qui suit. `folder` est le dossier du `.aep`, relatif au dossier du projet. |
| `skip` | Noms de dossiers à ignorer pendant le scan, en plus de ceux ignorés d'office. Insensible à la casse. Commun avec le plugin Cinema 4D. |

Pour ajouter une étape, insérer une ligne à la bonne position dans `stages`, puis cliquer sur ↻.

## Réglages dans le script

En tête de `homepage.jsx` :

| Constante | Valeur | Rôle |
|---|---|---|
| `LIST_H` | 150 | Hauteur de départ des tableaux (px) |
| `LIST_H_MIN` | 80 | Hauteur minimale si le panneau est petit |
| `LIST_H_MAX` | 200 | Hauteur maximale si le panneau est grand |
| `MARGIN` | 8 | Marge intérieure du panneau |
| `MAX_DEPTH` | 4 | Profondeur de recherche des `.aep` dans un projet |
| `IGNORE_AEP` | regex | Fichiers `.aep` ignorés |
| `SKIP_BUILTIN` | regex | Dossiers toujours ignorés (rendus, caches…) |
| `DEFAULT_STAGES` | liste | Étapes écrites dans le JSON si `stages` est absent |
