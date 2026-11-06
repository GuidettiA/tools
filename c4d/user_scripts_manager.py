"""
Menu déroulant pour organiser et exécuter les scripts Python utilisateur dans C4D.

Basé sur le travail de Mike Udin (mikeudin.net).

Utilisation :
  1. Copier ce fichier dans le dossier library/scripts des préférences C4D
     (voir Readme.md)
  2. Lancer le script, puis ajouter les dossiers de scripts via
     "Add Scripts Folder"
"""

import c4d,os,codecs,threading,configparser
from c4d import storage as st
from c4d import gui

ADD_FOLDER = 999998
REMOVE_FOLDER = 999997
TOGGLE_DEFAULT_FOLDER = 999996
EDIT_LIST = 999999
SCRIPT_ICON = 1022807
DIRECTORY_ICON = 1026719
ERROR_ICON = c4d.RESOURCEIMAGE_CANCEL     # icone documentee (constante symbolique c4d, pas un ID devine)
REMOVE_ICON = c4d.RESOURCEIMAGE_CLOSERRELEASED  # choisie visuellement via icon_preview.py
CUSTOM_FOLDER_ICON = 12095    # icone utilisee pour tout dossier personnalise ajoute via le menu
SCAN_TIMEOUT_SECONDS = 5      # temps max pour scanner un dossier racine avant d'abandonner (evite de geler C4D)

def execute_script(filename,var):

    try:
        with open(filename, 'rb') as fl:
            code = compile(fl.read(), filename, 'exec')
    except Exception as e:
        import traceback
        traceback.print_exc()
        gui.MessageDialog('Impossible de lire/compiler le script :\n{0}\n\n{1}'.format(os.path.basename(filename), e))
        return

    doc = c4d.documents.GetActiveDocument()

    scope = {'__file__': filename,
            '__name__': '__main__',
            'input_key':var, #variable optionnelle transmise au script
            'doc': doc,
            'op': doc.GetActiveObject(),
            'tp': doc.GetParticleSystem()
            }

    try:
        exec(code, scope)
    except Exception as e:
        # On laisse l'erreur remonter dans la console C4D (utile pour debug)
        # tout en affichant un message clair a l'utilisateur.
        import traceback
        traceback.print_exc()
        gui.MessageDialog('Erreur pendant l\'execution du script :\n{0}\n\n{1}'.format(os.path.basename(filename), e))

def scan_directory_tree(dirName):
    """Scanne recursivement dirName et retourne une structure independante
    de tout objet C4D (donc utilisable depuis un thread separe) :
    {'error': str} si inaccessible, sinon
    {'entries': [ {'type':'dir','name':n,'subtree':{...}} | {'type':'file','name':n,'path':fullpath} ]}"""

    try:
        listOfFile = sorted(os.listdir(dirName),key=lambda x: os.path.isdir(os.path.join(dirName, x)), reverse=True)
    except Exception as e:
        return {'error': str(e)}

    entries = []
    for entry in listOfFile:
        fullPath = os.path.join(dirName, entry)
        if os.path.isdir(fullPath):
            entries.append({'type': 'dir', 'name': entry, 'subtree': scan_directory_tree(fullPath)})
        elif fullPath.endswith('.py'):
            entries.append({'type': 'file', 'name': entry, 'path': fullPath})

    return {'entries': entries}

def scan_with_timeout(dirName, timeout_seconds):
    """Lance scan_directory_tree() dans un thread separe pour eviter de geler
    C4D si le dossier est trop volumineux ou trop lent (reseau). Si le scan
    ne termine pas dans le delai imparti, on abandonne l'attente et on
    remonte une erreur de type 'timeout' ; le thread continue en arriere-plan
    (il n'y a pas de moyen propre de le tuer) mais ne bloque plus l'interface."""

    result = {}

    def worker():
        result['tree'] = scan_directory_tree(dirName)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    thread.join(timeout_seconds)

    if thread.is_alive():
        print('[UserScripts_Manager] Timeout ({0}s) sur le scan de : {1}'.format(timeout_seconds, dirName))
        return {'error': 'scan interrompu apres {0}s (dossier trop volumineux ou trop lent)'.format(timeout_seconds), 'timeout': True}

    return result.get('tree', {'error': 'erreur inconnue pendant le scan'})

def build_menu_from_tree(menu, files_list, counter, tree, dirName):
    """Construit le menu C4D (BaseContainer) a partir d'une arborescence
    deja scannee (voir scan_directory_tree/scan_with_timeout). Ne touche
    jamais au disque, donc s'execute toujours dans le thread principal."""

    if tree.get('error') is not None:
        # Dossier inaccessible OU scan trop long (timeout) : on ne bloque pas
        # tout le menu, on ajoute une entree desactivee informative.
        suffix = 'timeout' if tree.get('timeout') else 'inaccessible'
        if not tree.get('timeout'):
            print('[UserScripts_Manager] Dossier inaccessible : {0} ({1})'.format(dirName, tree['error']))
        menu.InsData(counter, '&i{1}&{0} ({2})&d&'.format(os.path.basename(dirName) or dirName, ERROR_ICON, suffix))
        files_list.InsData(counter, '')
        counter += 1
        return menu, files_list, counter

    for e in tree.get('entries', []):

        if e['type'] == 'dir':
            fullPath = os.path.join(dirName, e['name'])
            submenu = c4d.BaseContainer()
            submenu, files_list, counter = build_menu_from_tree(submenu, files_list, counter, e['subtree'], fullPath)
            postfix = '' if len(submenu) >= 1 else '&d&'
            submenu.InsData(1, '&i{1}&{0}{2}'.format(e['name'],DIRECTORY_ICON,postfix))
            if len(submenu) > 1:
                menu.SetContainer(counter, submenu)
        else:
            menu.InsData(counter,'&i{1}&{0}'.format(e['name'],SCRIPT_ICON))
            files_list.InsData(counter, e['path'])

        counter += 1

    return menu, files_list, counter

def new_config():
    # delimiters=('=',) : evite toute ambiguite avec les ':' des lettres de lecteur Windows (Z:\...)
    # interpolation=None : evite que configparser interprete un '%' present dans un chemin
    config = configparser.ConfigParser(delimiters=('=',), interpolation=None)
    config.optionxform = str  # preserve la casse des cles (les chemins de dossiers)
    return config

def load_config(config_file):
    """Charge la configuration unifiee (dossiers personnalises + reglages)
    depuis config_file. Si le fichier n'existe pas ou est illisible,
    retourne une configuration vide."""

    config = new_config()

    if os.path.exists(config_file):
        try:
            config.read(config_file, encoding='utf-8')
        except Exception as e:
            print('[UserScripts_Manager] Config illisible, reinitialisation : {0}'.format(e))
            config = new_config()

    return config

def save_config(config_file, config):
    try:
        with codecs.open(config_file, 'w', encoding='utf-8') as f:
            config.write(f)
    except Exception as e:
        print('[UserScripts_Manager] Impossible d\'ecrire la config : {0}'.format(e))

def main():

    c4d_user_dir = st.GeGetC4DPath(c4d.C4D_PATH_LIBRARY_USER)
    user_scripts_path = os.path.join(c4d_user_dir,'scripts')
    maxon_dir = os.path.split(st.GeGetStartupWritePath())[0]

    config_file = os.path.join(maxon_dir,'UserScripts_Config.ini')

    config = load_config(config_file)

    hide_default = config.has_section('settings') and config.getboolean('settings', 'hide_default_folder', fallback=False)

    points = [] if hide_default else [
        (1022735, 'C4D Scripts Folder',user_scripts_path)
        ]


    custom_entries_count = 0

    if config.has_section('folders'):
        for path, name in config.items('folders'):
            points.append((CUSTOM_FOLDER_ICON, name, path))
            custom_entries_count += 1

    menu = c4d.BaseContainer()
    files_list = c4d.BaseContainer()
    counter = c4d.FIRST_POPUP_ID

    for icon_id,name,n_dir in points:
        submenu = c4d.BaseContainer()

        tree = scan_with_timeout(n_dir, SCAN_TIMEOUT_SECONDS)
        submenu, files_list, counter = build_menu_from_tree(submenu, files_list, counter, tree, n_dir)

        postfix = '' if len(submenu) >= 1 else '&d&'
        submenu.InsData(1, '&i{0}&{1}{2}'.format(icon_id,name,postfix))

        menu.SetContainer(counter, submenu)
        counter += 1
        if counter >= ADD_FOLDER:
            # Limite de la plage d'Id's de menu (c4d.FIRST_POPUP_ID a c4d.FIRST_POPUP_ID + 99999) atteinte :
            # les dossiers/scripts suivants ne sont pas affiches.
            print('[UserScripts_Manager] Limite du nombre d\'entrees de menu atteinte : certains dossiers ou scripts ne sont pas affiches.')
            break

    menu.SetString(0,'')

    toggle_label = 'Show default scripts folder' if hide_default else 'Hide default scripts folder'
    menu.SetString(TOGGLE_DEFAULT_FOLDER, '&i{0}&{1}'.format(DIRECTORY_ICON, toggle_label))

    menu.SetString(ADD_FOLDER,'&i{0}&Add custom folder'.format(1027025))

    if custom_entries_count > 0:
        menu.SetString(REMOVE_FOLDER,'&i{0}&Remove custom folder'.format(REMOVE_ICON))
        menu.SetString(EDIT_LIST,'&i{0}&Edit config file'.format(1018423))

    result = gui.ShowPopupDialog(cd=None, bc=menu, x=c4d.MOUSEPOS, y=c4d.MOUSEPOS)

    # Aucune entree du menu selectionnee
    if result <= 0:
        return

    if result == EDIT_LIST:
        if os.path.exists(config_file):
            st.GeExecuteFile(config_file)
        else:
            gui.MessageDialog('Aucune liste a editer.')

        return

    if result == TOGGLE_DEFAULT_FOLDER:

        if not config.has_section('settings'):
            config.add_section('settings')

        config.set('settings', 'hide_default_folder', 'false' if hide_default else 'true')
        save_config(config_file, config)

        if hide_default:
            gui.MessageDialog('Le dossier de scripts par defaut sera de nouveau affiche.')
        else:
            gui.MessageDialog('Le dossier de scripts par defaut sera masque.')

        return

    if result == ADD_FOLDER:

        c_dir = st.LoadDialog(type=c4d.FILESELECTTYPE_ANYTHING,
                title="Add New Directory to list",
                flags=c4d.FILESELECT_DIRECTORY,
                force_suffix="")

        if not c_dir: return

        if not config.has_section('folders'):
            config.add_section('folders')

        # La cle est le chemin complet (garantit l'unicite, meme si deux
        # dossiers differents partagent le meme nom) ; la valeur est le nom affiche.
        config.set('folders', c_dir, os.path.split(c_dir)[1])
        save_config(config_file, config)

        gui.MessageDialog('Dossier ajoute :\n{0}'.format(c_dir))

        return

    if result == REMOVE_FOLDER:

        if not config.has_section('folders') or not config.items('folders'):
            gui.MessageDialog('Aucun dossier personnalise a supprimer.')
            return

        folder_items = list(config.items('folders'))  # [(path, name), ...]

        # Popup secondaire listant les dossiers personnalises.
        # Important : on utilise de grands Id's (comme partout ailleurs dans ce script) et
        # non des petits nombres sequentiels (1,2,3...) - l'Id '1' notamment a un role
        # reserve dans l'API popup de C4D (label de sous-menu) et n'est pas fiable
        # comme entree cliquable normale dans un popup top-level.
        REMOVE_MENU_BASE_ID = c4d.FIRST_POPUP_ID
        remove_menu = c4d.BaseContainer()
        remove_menu.SetString(0, '')
        for i, (path, name) in enumerate(folder_items):
            remove_menu.SetString(REMOVE_MENU_BASE_ID + i, name)

        choice = gui.ShowPopupDialog(cd=None, bc=remove_menu, x=c4d.MOUSEPOS, y=c4d.MOUSEPOS)

        if choice <= 0:
            return

        removed_path, _ = folder_items[choice - REMOVE_MENU_BASE_ID]

        config.remove_option('folders', removed_path)
        save_config(config_file, config)

        gui.MessageDialog('Dossier supprime :\n{0}'.format(removed_path))

        return


    selected = files_list.GetString(result)
    if not selected:
        # Entree "(inaccessible)" selectionnee par erreur -> rien a executer
        return

    execute_script(selected, 4)


if __name__=='__main__':
    main()
