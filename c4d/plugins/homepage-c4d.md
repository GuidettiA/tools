# Homepage — panneau Cinema 4D des projets en cours

Plugin qui liste les projets en cours au lancement de Cinema 4D.
Il permet d'ouvrir une scène en un clic, de créer une nouvelle version ou de passer à l'étape suivante sans passer par l'Explorateur.

C'est l'équivalent du panneau After Effects `homepage.jsx`, avec lequel il partage le fichier de configuration.

Testé sur Cinema 4D 2026.3.4.

## Installation

1. Ranger le plugin dans un dossier dédié :
   ```
   ...\Maxon\<Maxon Cinema 4D version>\plugins\homepage\homepage.pyp
   ```
2. Relancer Cinema 4D
3. Ouvrir le panneau via **Extensions > Homepage**

Attention : en placant le plugin `plugins` des préférences (**Édition > Préférences > Ouvrir le dossier des préférences…**), il faudra déplacer ce fichier à chaque mise à jour de version de C4D.
Pour éviter cela, on peut créer un dossier de plugins déclaré dans cinema 4D.

En cas de problème, les erreurs s'affichent dans **Extensions > Console**, onglet Python.

## Organisation attendue

### Arborescence

```
<racine>/
└── <client>/
    └── <projet>/
        └── … /*.c4d     jusqu'à 4 niveaux de profondeur
```

### Nommage des fichiers

```
date_client_projet_etape_version.c4d
```

- **étape** : avant-dernier champ (`maquette`, `layout`, `animation`).
- **version** : dernier champ, numérique (`01`, `02`… ; `v03` est aussi accepté).
- Les nouveaux fichiers créés par le panneau sont toujours en minuscules.

Un fichier hors schéma reste affiché (exemple `01-2`), son étape est alors déduite de son dossier, mais les actions de versionnage lui sont refusées.

### Éléments ignorés au scan

- Dossiers : toujours ignorés (renders, caches, proxys, textures, illumination, backups), ceux listés dans la clé `skip` de la configuration, et tout dossier commençant par `.` ou `#`.
- Fichiers : copies de sauvegarde de C4D (`_backup`, `autosave`).

## Interface

| Zone | Rôle |
|---|---|
| ↻ | Relance le scan et relit le fichier de configuration. |
| Bouton du chemin | Affiche le dossier scanné ; un clic permet d'en choisir un autre. |
| Tableau des projets | Client, projet, étape et date du dernier `.c4d` modifié. Trié du plus récent au plus ancien. |
| Tableau des fichiers | Une ligne par étape du projet sélectionné, avec uniquement sa dernière version, dans l'ordre de la configuration. |
| Ouvrir le dossier | Ouvre dans l'Explorateur le dossier du fichier sélectionné (ou du projet). |
| Ouvrir le fichier | Ouvre la scène sélectionnée. |
| Nouvelle version | Voir [Actions](#actions-sur-les-fichiers). |
| Étape suivante | Voir [Actions](#actions-sur-les-fichiers). |
| Dupliquer… | Voir [Actions](#actions-sur-les-fichiers). |
| Ligne d'état | Nombre de projets scannés, durée du scan et nombre de conflits éventuels. |

### Sélection et raccourcis

- **Clic sur une ligne** : la sélectionne (surbrillance sur toute la ligne).
- **Clic dans la zone vide d'un tableau** : désélectionne ; dans le tableau des projets, vide aussi le tableau des fichiers.
- **Double-clic sur un projet** : ouvre son `.c4d` le plus récent (hors copie de conflit).
- **Double-clic sur un fichier** : ouvre ce fichier.

Après un scan, le projet le plus récent et sa première étape sont présélectionnés.

### Ouverture des scènes

C4D gère plusieurs scènes à la fois : chaque ouverture crée un nouvel onglet de document. Si la scène est déjà ouverte, le panneau bascule simplement dessus.

## Actions sur les fichiers

Elles s'appliquent au fichier sélectionné dans le second tableau.

| Action | Exemple | Destination |
|---|---|---|
| Nouvelle version | `…_maquette_01` → `…_maquette_02` | Même dossier |
| Étape suivante | `…_maquette_02` → `…_layout_01` | Dossier de l'étape suivante (créé si besoin) |
| Dupliquer… | Nom libre, prérempli | Même dossier |

Règles communes :

- Une confirmation affiche le fichier source et le fichier cible avant toute action.
- Rien n'est jamais écrasé : si le numéro de version visé existe déjà, le suivant est utilisé.
- Rien n'est supprimé ni déplacé : l'original reste en place.
- Si la scène source est ouverte, l'action fait un **Enregistrer sous** : les modifications en cours sont incluses et le document ouvert bascule sur le nouveau fichier. Sinon, le fichier est copié puis ouvert.
- Le nom saisi dans « Dupliquer… » doit respecter les conventions : minuscules, chiffres, `_` et `-` uniquement.
- Les copies de conflit et les fichiers hors schéma sont refusés, avec un message explicatif.

### Textures lors du changement d'étape

Chaque dossier `c4d/` a son propre `tex/`. Lors d'un passage à l'étape suivante, le panneau recopie dans le `tex/` de destination **uniquement** les textures qui :

- sont réellement utilisées par la scène ;
- sont référencées en chemin relatif ;
- se trouvent dans le `tex/` de la scène source.

Les sous-dossiers de `tex/` sont conservés. Les textures situées ailleurs (chemin absolu, bibliothèque commune…) ne bougent pas : la scène continue de pointer vers elles. Une texture déjà présente dans la destination n'est jamais écrasée ; un message le signale.

Le nombre de textures à copier est indiqué dans la confirmation.

## Copies de conflit de synchronisation

Le panneau reconnaît les copies de conflit au format de Synology Drive :

```
<nom>_<poste>_<Mon-JJ-HHMM-AAAA>_Conflict.c4d
```

Le panneau les signale :

- `(!) conflit` dans la colonne Étape du projet concerné ;
- préfixe `[conflit]` dans le tableau des fichiers, en fin de liste ;
- total dans la ligne d'état.

Elles ne sont jamais ouvertes par le double-clic sur un projet. La détection suppose que le nom du poste ne contient pas de `_`.

## Configuration

Fichier partagé avec le panneau After Effects : `%APPDATA%\petit-studio\homepage.json`, soit `C:\Users\<utilisateur>\AppData\Roaming\petit-studio\homepage.json`.

Les clés `c4d_stages` et `skip` sont ajoutées automatiquement au premier lancement, sans toucher aux autres. Le fichier se modifie à la main ; le bouton ↻ le relit.

```json
{
  "root": "D:\\projets",
  "stages": [ "… étapes After Effects …" ],
  "c4d_stages": [
    { "name": "maquette",  "folder": "maquette/c4d" },
    { "name": "layout",    "folder": "layout/c4d" },
    { "name": "animation", "folder": "animation/c4d" }
  ],
  "skip": ["temp", "archive"]
}
```

| Clé | Rôle |
|---|---|
| `root` | Dossier scanné, **commun à AE et C4D** : le changer dans un logiciel le change pour l'autre. |
| `stages` | Étapes After Effects (non utilisées par C4D). |
| `c4d_stages` | Étapes C4D **dans l'ordre** : « Étape suivante » prend l'entrée qui suit. `folder` est le dossier du `.c4d`, relatif au dossier du projet. |
| `skip` | Noms de dossiers à ignorer pendant le scan, en plus de ceux ignorés d'office. Insensible à la casse. **Commun à AE et C4D.** |

Pour ajouter une étape, insérer une ligne à la bonne position dans `c4d_stages`, puis cliquer sur ↻ dans le plugins pour faire un nouveau scan avec ces paramètres.

## Réglages dans le script

En tête de `homepage.pyp` :

| Constante | Valeur | Rôle |
|---|---|---|
| `PLUGIN_ID` | 1000010 | Identifiant du plugin |
| `LIST_H` | 150 | Hauteur des tableaux (px) |
| `MAX_DEPTH` | 4 | Profondeur de recherche des `.c4d` dans un projet |
| `SKIP_BUILTIN` | regex | Dossiers toujours ignorés (rendus, caches…) |
| `IGNORE_FILE` | regex | Fichiers `.c4d` ignorés |
| `DEFAULT_C4D_STAGES` | liste | Étapes écrites dans le JSON si `c4d_stages` est absent |

## Limites connues

- `PLUGIN_ID` est un identifiant de test réservé par Maxon (1000001 à 1000010). Si un autre plugin installé utilise le même, l'un des deux ne se chargera pas : obtenir un identifiant unique sur developers.maxon.net et le remplacer.
- La hauteur des tableaux est fixe ; elle ne suit pas le redimensionnement de la fenêtre.
- Le bouton du chemin centre le texte : un chemin très long peut être tronqué.
- Lors d'un changement d'étape, seules les textures sont recopiées : les autres fichiers référencés en relatif (caches Alembic, VDB…) ne suivent pas.
