/*
    Homepage — panneau ScriptUI pour After Effects listant les projets en cours

    Installation :
      1. Copier ce fichier dans
      C:\Program Files\Adobe\Adobe After Effects <version>\Support Files\Scripts\ScriptUI Panels\
      2. Relancer AE, puis Fenêtre > homepage.jsx

    Fonctionnement :
      - Au premier lancement, cliquer sur le champ du chemin et choisir le dossier racine
      - Structure attendue : racine / client / projet / ... / *.aep
      - Nommage : date_client_projet_etape_version.aep
      - Projets triés par dernier .aep modifié
      - Double-clic pour ouvrir

    Configuration :
      %APPDATA%\petit-studio\homepage.json (créé au premier lancement)
        root   : dossier scanné
        stages : étapes dans l'ordre, avec le dossier du .aep relatif au projet
        skip   : noms de dossiers à ignorer pendant le scan (en plus des dossiers
                 de rendu/cache ignorés d'office)
      Modifiable à la main : le bouton d'actualisation relit le fichier.
*/

(function (thisObj) {

    // ---------- Réglages ----------
    var LIST_H     = 150; // hauteur de départ des tableaux (px)
    var LIST_H_MIN = 80;  // hauteur minimale si le panneau est petit
    var LIST_H_MAX = 200; // hauteur maximale si le panneau est grand
    var MARGIN     = 8;   // marge intérieure du panneau (px)
    var MAX_DEPTH  = 4;   // profondeur max de recherche des .aep dans un projet
    // .aep ignorés : auto-saves AE et projets temporaires créés par l'envoi vers Media Encoder
    var IGNORE_AEP = /(auto-save|^tmpAEtoAMEProject)/i;
    // Dossiers toujours ignorés pendant le scan ; les autres se règlent dans la clé « skip » du JSON
    var SKIP_BUILTIN = /^(renders?|caches?|proxy|tex|adobe after effects auto-save)$/i;

    // ---------- Utilitaires ----------
    function padN(n, w) {
        var s = String(n);
        while (s.length < w) s = "0" + s;
        return s;
    }

    function fmt(d) {
        if (!d) return "—";
        return padN(d.getDate(), 2) + "/" + padN(d.getMonth() + 1, 2) + "/" + String(d.getFullYear()).substr(2) +
               " " + padN(d.getHours(), 2) + ":" + padN(d.getMinutes(), 2);
    }

    // ---------- Configuration (fichier JSON) ----------
    var CONFIG_FILE = new File(Folder.userData.fsName + "/petit-studio/homepage.json");

    var DEFAULT_STAGES = [
        { name: "maquette",  folder: "maquette/ae" },
        { name: "animatic",  folder: "animatic/ae" },
        { name: "animation", folder: "animation/ae" }
    ];

    var cfg = null;
    var skipMap = {}; // noms de dossiers de « skip », en minuscules

    // Sérialiseur JSON minimal (ExtendScript n'a pas d'objet JSON natif)
    function toJSON(v, ind) {
        ind = ind || "";
        var next = ind + "  ", i, out;
        if (v === null || v === undefined) return "null";
        if (typeof v === "string") {
            return '"' + v.replace(/\\/g, "\\\\").replace(/"/g, '\\"')
                          .replace(/\n/g, "\\n").replace(/\r/g, "\\r").replace(/\t/g, "\\t") + '"';
        }
        if (typeof v === "number" || typeof v === "boolean") return String(v);
        if (v instanceof Array) {
            if (!v.length) return "[]";
            out = [];
            for (i = 0; i < v.length; i++) out.push(next + toJSON(v[i], next));
            return "[\n" + out.join(",\n") + "\n" + ind + "]";
        }
        out = [];
        for (var k in v) if (v.hasOwnProperty(k)) out.push(next + toJSON(k) + ": " + toJSON(v[k], next));
        return "{\n" + out.join(",\n") + "\n" + ind + "}";
    }

    function mkdirs(folder) {
        if (folder.exists) return true;
        if (folder.parent && !folder.parent.exists) mkdirs(folder.parent);
        return folder.create();
    }

    function saveConfig() {
        mkdirs(CONFIG_FILE.parent);
        CONFIG_FILE.encoding = "UTF-8";
        if (CONFIG_FILE.open("w")) {
            CONFIG_FILE.write(toJSON(cfg));
            CONFIG_FILE.close();
        }
    }

    function loadConfig() {
        var c = null;
        if (CONFIG_FILE.exists) {
            CONFIG_FILE.encoding = "UTF-8";
            if (CONFIG_FILE.open("r")) {
                var txt = CONFIG_FILE.read();
                CONFIG_FILE.close();
                try { c = eval("(" + txt + ")"); }
                catch (e) { alert("Fichier de configuration illisible :\n" + CONFIG_FILE.fsName + "\n\n" + e.message); }
            }
        }
        var isNew = !c || typeof c !== "object";
        if (isNew) c = {};
        if (!(c.stages instanceof Array) || !c.stages.length) { c.stages = DEFAULT_STAGES; isNew = true; }
        if (!(c.skip instanceof Array)) { c.skip = []; isNew = true; }
        skipMap = {};
        for (var i = 0; i < c.skip.length; i++) skipMap[String(c.skip[i]).toLowerCase()] = true;
        cfg = c;
        if (isNew) saveConfig();
    }

    function getRoot() {
        if (cfg.root) {
            var f = new Folder(cfg.root);
            if (f.exists) return f;
        }
        return null;
    }

    function setRoot(folder) {
        cfg.root = folder.fsName;
        saveConfig();
    }

    function stageIndex(name) {
        name = String(name).toLowerCase();
        for (var i = 0; i < cfg.stages.length; i++) {
            if (String(cfg.stages[i].name).toLowerCase() === name) return i;
        }
        return -1;
    }

    function subFolders(folder) {
        var out = [];
        var items = folder.getFiles();
        for (var i = 0; i < items.length; i++) {
            var n = items[i].displayName;
            if (items[i] instanceof Folder && n.charAt(0) !== "." && n.charAt(0) !== "#") out.push(items[i]);
        }
        return out;
    }

    function findAep(folder, depth, out) {
        if (depth > MAX_DEPTH) return;
        var items = folder.getFiles();
        for (var i = 0; i < items.length; i++) {
            var it = items[i];
            var name = it.displayName;
            if (name.charAt(0) === ".") continue;
            if (it instanceof Folder) {
                if (!SKIP_BUILTIN.test(name) && !skipMap[name.toLowerCase()]) findAep(it, depth + 1, out);
            } else if (/\.aep$/i.test(name) && !IGNORE_AEP.test(name)) {
                out.push(it);
            }
        }
    }

    // ---------- Analyse des noms ----------
    // Schéma : date_client_projet_etape_version.aep
    // Copie de conflit Synology Drive : nom_<client>_<Mon-JJ-HHMM-AAAA>_Conflict.aep
    var CONFLICT = /_[^_]+_[^_]+_conflict$/i;

    function isConflict(file) {
        return CONFLICT.test(file.displayName.replace(/\.aep$/i, ""));
    }

    // Découpe le nom (suffixe de conflit ignoré) ; null s'il ne suit pas le schéma
    function parseName(file) {
        var base = file.displayName.replace(/\.aep$/i, "").replace(CONFLICT, "");
        var parts = base.split("_");
        if (parts.length < 3) return null;
        var m = /^(v?)(\d+)$/i.exec(parts[parts.length - 1]);
        if (!m) return null;
        return {
            prefix:  parts.slice(0, parts.length - 2).join("_"),
            stage:   parts[parts.length - 2],
            version: parseInt(m[2], 10),
            label:   m[2],                    // version telle qu'écrite (ex. "01")
            vchar:   m[1],                    // préfixe « v » éventuel
            width:   Math.max(2, m[2].length)
        };
    }

    // Étape d'un fichier hors schéma : chemin de son dossier dans le projet
    function folderStage(file, projectFolder) {
        var p = file.parent.fsName.substr(projectFolder.fsName.length + 1);
        return p.replace(/\\/g, "/") || "(racine)";
    }

    // Une ligne par étape : la version la plus haute (puis la plus récente).
    // Ordre des étapes selon la config ; copies de conflit ajoutées à la fin.
    function latestByStage(aeps) {
        var map = {}, keys = [], conflicts = [], i, a, k;
        function num(x) { return x.info ? x.info.version : -1; }
        for (i = 0; i < aeps.length; i++) {
            a = aeps[i];
            if (a.conflict) { conflicts.push(a); continue; }
            k = String(a.stage).toLowerCase();
            if (!map[k]) { map[k] = a; keys.push(k); continue; }
            var b = map[k];
            if (num(a) > num(b) || (num(a) === num(b) && a.file.modified.getTime() > b.file.modified.getTime())) map[k] = a;
        }
        keys.sort(function (x, y) {
            var ix = stageIndex(x), iy = stageIndex(y);
            if (ix < 0) ix = 999;
            if (iy < 0) iy = 999;
            return ix - iy;
        });
        var rows = [];
        for (i = 0; i < keys.length; i++) rows.push(map[keys[i]]);
        return rows.concat(conflicts);
    }

    // ---------- Nommage des nouveaux fichiers ----------
    function buildName(info, stage, version) {
        return (info.prefix + "_" + stage + "_" + info.vchar + padN(version, info.width)).toLowerCase() + ".aep";
    }

    // Premier numéro libre à partir de startV dans le dossier : rien n'est jamais écrasé
    function freeFile(folder, info, stage, startV) {
        var v = startV;
        while (new File(folder.fsName + "/" + buildName(info, stage, v)).exists) v++;
        return new File(folder.fsName + "/" + buildName(info, stage, v));
    }

    function scan(root) {
        var projects = [];
        var clients = subFolders(root);
        for (var c = 0; c < clients.length; c++) {
            var projs = subFolders(clients[c]);
            for (var p = 0; p < projs.length; p++) {
                var files = [];
                findAep(projs[p], 1, files);
                files.sort(function (a, b) { return b.modified.getTime() - a.modified.getTime(); });
                var aeps = [], latest = null, conflicts = 0;
                for (var i = 0; i < files.length; i++) {
                    var info = parseName(files[i]);
                    var a = {
                        file:     files[i],
                        info:     info,
                        stage:    info ? info.stage : folderStage(files[i], projs[p]),
                        version:  info ? info.label : "—",
                        conflict: isConflict(files[i])
                    };
                    if (a.conflict) conflicts++;
                    else if (!latest) latest = a; // .aep le plus récent hors conflit
                    aeps.push(a);
                }
                if (!latest && aeps.length) latest = aeps[0];
                projects.push({
                    client:    clients[c].displayName,
                    name:      projs[p].displayName,
                    folder:    projs[p],
                    aeps:      aeps,
                    latest:    latest,
                    conflicts: conflicts,
                    stage:     latest ? latest.stage : "—",
                    last:      latest ? latest.file.modified : null
                });
            }
        }
        // Plus récent en haut, projets sans .aep à la fin
        projects.sort(function (a, b) {
            if (!a.last && !b.last) return 0;
            if (!a.last) return 1;
            if (!b.last) return -1;
            return b.last.getTime() - a.last.getTime();
        });
        return projects;
    }

    function openAep(file) {
        if (!file || !file.exists) { alert("Fichier introuvable."); return; }
        if (app.project && app.project.file && app.project.file.fsName === file.fsName) return;
        if (app.project && app.project.dirty) {
            if (!app.project.close(CloseOptions.PROMPT_TO_SAVE_CHANGES)) return; // annulé
        }
        app.open(file);
    }

    // ---------- Dessin des contrôles personnalisés ----------
    function rgb(v) { return [v, v, v, 1]; }

    function drawFrame(g, w, h, hover) {
        g.newPath();
        g.rectPath(0, 0, w, h);
        g.fillPath(g.newBrush(g.BrushType.SOLID_COLOR, rgb(hover ? 0.17 : 0.11)));
        g.newPath();
        g.rectPath(0.5, 0.5, w - 1, h - 1);
        g.strokePath(g.newPen(g.PenType.SOLID_COLOR, rgb(hover ? 0.45 : 0.24), 1));
    }

    // Tronque le texte par la gauche pour garder la fin du chemin visible
    function fitLeft(g, txt, maxW) {
        if (g.measureString(txt)[0] <= maxW) return txt;
        var s = txt;
        while (s.length > 1 && g.measureString("…" + s)[0] > maxW) s = s.substr(1);
        return "…" + s;
    }

    function drawPathField(state) {
        var g = this.graphics, w = this.size[0], h = this.size[1];
        var hover = state && state.mouseOver;
        drawFrame(g, w, h, hover);

        // Icône dossier
        var x = 8, y = Math.round(h / 2) - 6;
        g.newPath();
        g.moveTo(x, y);
        g.lineTo(x + 6, y);
        g.lineTo(x + 8, y + 2);
        g.lineTo(x + 16, y + 2);
        g.lineTo(x + 16, y + 12);
        g.lineTo(x, y + 12);
        g.closePath();
        g.fillPath(g.newBrush(g.BrushType.SOLID_COLOR, rgb(hover ? 0.85 : 0.65)));

        // Chemin
        var txt = fitLeft(g, this.pathText, w - 38);
        var sz = g.measureString(txt);
        g.drawString(txt, g.newPen(g.PenType.SOLID_COLOR, rgb(hover ? 0.95 : 0.78), 1),
                     32, Math.round((h - sz[1]) / 2));
    }

    function drawRefreshIcon(state) {
        var g = this.graphics, w = this.size[0], h = this.size[1];
        var hover = state && state.mouseOver;
        drawFrame(g, w, h, hover);

        var col = rgb(hover ? 0.9 : 0.7);
        var cx = w / 2, cy = h / 2, r = 6;
        var a0 = -1.2, a1 = 4.0; // arc ouvert en haut à droite

        g.newPath();
        g.moveTo(cx + r * Math.cos(a0), cy + r * Math.sin(a0));
        for (var a = a0 + 0.2; a <= a1; a += 0.2) g.lineTo(cx + r * Math.cos(a), cy + r * Math.sin(a));
        g.strokePath(g.newPen(g.PenType.SOLID_COLOR, col, 1.6));

        // Pointe de flèche au début de l'arc
        var px = cx + r * Math.cos(a0), py = cy + r * Math.sin(a0);
        var tx = Math.sin(a0), ty = -Math.cos(a0);   // tangente (sens inverse)
        var nx = Math.cos(a0), ny = Math.sin(a0);    // normale
        g.newPath();
        g.moveTo(px + tx * 4, py + ty * 4);
        g.lineTo(px + nx * 3, py + ny * 3);
        g.lineTo(px - nx * 3, py - ny * 3);
        g.closePath();
        g.fillPath(g.newBrush(g.BrushType.SOLID_COLOR, col));
    }

    // ---------- Hauteur des tableaux : départ, min et max ----------
    function sizeList(list, h) {
        h = Math.max(LIST_H_MIN, Math.min(LIST_H_MAX, Math.round(h)));
        list.preferredSize = [380, h];
        list.minimumSize.height = h;
        list.maximumSize.height = h;
    }

    // ---------- Interface ----------
    function buildUI(thisObj) {
        var win = (thisObj instanceof Panel)
            ? thisObj
            : new Window("palette", "Homepage", undefined, { resizeable: true });
        win.orientation = "column";
        win.alignChildren = ["fill", "top"];
        win.margins = MARGIN;

        // Tout le contenu est dans un groupe collé en haut : la place en trop
        // reste sous la ligne d'état au lieu d'écarter les éléments.
        var main = win.add("group");
        main.orientation = "column";
        main.alignment = ["fill", "top"];
        main.alignChildren = ["fill", "top"];
        main.spacing = 6;
        main.margins = 0;

        var top = main.add("group");
        top.alignment = ["fill", "top"];
        top.alignChildren = ["left", "center"];
        top.spacing = 4;

        // Bouton icône : relancer le scan
        var btnRefresh = top.add("button", undefined, "");
        btnRefresh.preferredSize = [26, 26];
        btnRefresh.alignment = ["left", "center"];
        btnRefresh.helpTip = "Relancer le scan";
        btnRefresh.onDraw = drawRefreshIcon;

        // Champ cliquable : icône dossier + chemin (clic = choisir le dossier)
        var pathBtn = top.add("button", undefined, "");
        pathBtn.alignment = ["fill", "center"];
        pathBtn.preferredSize = [200, 26];
        pathBtn.pathText = "Cliquer pour choisir le dossier à scanner";
        pathBtn.helpTip = "Choisir le dossier à scanner";
        pathBtn.onDraw = drawPathField;

        var listProj = main.add("listbox", undefined, [], {
            numberOfColumns: 4, showHeaders: true,
            columnTitles: ["Client", "Projet", "Étape", "Modifié"],
            columnWidths: [100, 120, 90, 100]
        });
        listProj.alignment = ["fill", "top"];
        sizeList(listProj, LIST_H);

        var listAep = main.add("listbox", undefined, [], {
            numberOfColumns: 4, showHeaders: true,
            columnTitles: ["Fichier", "Étape", "Version", "Modifié"],
            columnWidths: [170, 90, 60, 100]
        });
        listAep.alignment = ["fill", "top"];
        sizeList(listAep, LIST_H);

        var bottom = main.add("group");
        bottom.alignment = ["fill", "top"];
        var btnFolder = bottom.add("button", undefined, "Ouvrir le dossier");
        btnFolder.alignment = ["left", "center"];
        var btnOpen = bottom.add("button", undefined, "Ouvrir le fichier");
        btnOpen.alignment = ["left", "center"];

        var actions = main.add("group");
        actions.alignment = ["fill", "top"];
        var btnVersion = actions.add("button", undefined, "Nouvelle version");
        btnVersion.alignment = ["left", "center"];
        btnVersion.helpTip = "Copie le fichier sélectionné avec la version suivante, dans le même dossier";
        var btnStage = actions.add("button", undefined, "Étape suivante");
        btnStage.alignment = ["left", "center"];
        btnStage.helpTip = "Copie le fichier dans le dossier de l'étape suivante, en version 01";
        var btnDup = actions.add("button", undefined, "Dupliquer…");
        btnDup.alignment = ["left", "center"];
        btnDup.helpTip = "Copie le fichier sélectionné sous un nouveau nom, dans le même dossier";

        var status = main.add("statictext", undefined, "");
        status.alignment = ["fill", "top"];

        // ---------- Logique ----------
        var all = [];      // projets scannés, dans l'ordre d'affichage
        var current = [];  // lignes du tableau des fichiers

        function fillProjects() {
            listProj.removeAll();
            listAep.removeAll();
            current = [];
            for (var i = 0; i < all.length; i++) {
                var p = all[i];
                var row = listProj.add("item", p.client);
                row.subItems[0].text = p.name;
                row.subItems[1].text = p.stage + (p.conflicts ? "  (!) conflit" : "");
                row.subItems[2].text = fmt(p.last);
            }
            if (listProj.items.length) listProj.selection = 0;
        }

        function selectedProject() {
            return listProj.selection ? all[listProj.selection.index] : null;
        }

        function selectedAep() {
            return listAep.selection ? current[listAep.selection.index] : null;
        }

        listProj.onChange = function () {
            listAep.removeAll();
            var p = selectedProject();
            current = p ? latestByStage(p.aeps) : [];
            for (var i = 0; i < current.length; i++) {
                var label = (current[i].conflict ? "[conflit] " : "") + current[i].file.displayName;
                var row = listAep.add("item", label);
                row.subItems[0].text = current[i].stage;
                row.subItems[1].text = current[i].version;
                row.subItems[2].text = fmt(current[i].file.modified);
            }
            if (listAep.items.length) listAep.selection = 0;
        };

        function refresh() {
            loadConfig(); // relit le JSON à chaque scan
            var root = getRoot();
            pathBtn.pathText = root ? root.fsName : "Cliquer pour choisir le dossier à scanner";
            pathBtn.helpTip = root ? root.fsName + "\nCliquer pour changer de dossier" : "Choisir le dossier à scanner";
            pathBtn.hide(); pathBtn.show(); // force le redessin
            if (!root) {
                status.text = "Aucun dossier sélectionné";
                return;
            }
            status.text = "Scan en cours…";
            var t0 = new Date().getTime();
            all = scan(root);
            var dt = ((new Date().getTime() - t0) / 1000).toFixed(1);
            var nc = 0;
            for (var i = 0; i < all.length; i++) nc += all[i].conflicts;
            status.text = all.length + " projet(s) scanné(s) en " + dt + " s" +
                          (nc ? " — " + nc + " conflit(s)" : "");
            fillProjects();
        }

        btnRefresh.onClick = refresh;

        pathBtn.onClick = function () {
            var f = Folder.selectDialog("Dossier des projets en cours");
            if (f) { setRoot(f); refresh(); }
        };

        btnOpen.onClick = function () {
            var a = selectedAep();
            if (a) openAep(a.file);
        };
        listAep.onDoubleClick = btnOpen.onClick;

        // Double-clic sur un projet = ouvre son .aep le plus récent
        listProj.onDoubleClick = function () {
            var p = selectedProject();
            if (p && p.latest) openAep(p.latest.file);
        };

        // ---------- Actions sur les fichiers ----------
        var NAME_RULE = /^[a-z0-9]+([_-][a-z0-9]+)*$/;

        // .aep sélectionné et valide pour une action, sinon null (avec message)
        function actionSource(needParse) {
            var a = selectedAep();
            if (!a) { alert("Sélectionne d'abord un fichier dans la liste du bas."); return null; }
            if (a.conflict) { alert("C'est une copie de conflit Synology : règle d'abord le conflit."); return null; }
            if (needParse && !parseName(a.file)) {
                alert("Le nom ne suit pas le schéma date_client_projet_etape_version :\n" + a.file.displayName);
                return null;
            }
            return a;
        }

        function relToProject(file) {
            var p = selectedProject();
            var base = p ? p.folder.fsName : "";
            var s = file.fsName;
            if (base && s.indexOf(base) === 0) s = s.substr(base.length + 1);
            return s.replace(/\\/g, "/");
        }

        // Crée dest à partir de a, après confirmation, puis ouvre le nouveau fichier
        function createFrom(a, dest, title) {
            if (dest.exists) { alert("Ce fichier existe déjà :\n" + relToProject(dest)); return; }
            var isOpen = app.project && app.project.file && app.project.file.fsName === a.file.fsName;
            var msg = title + "\n\nDe :     " + relToProject(a.file) + "\nVers :  " + relToProject(dest);
            if (isOpen) msg += "\n\nFichier ouvert : « Enregistrer sous » (les modifications en cours sont incluses).";
            if (!confirm(msg + "\n\nContinuer ?", false, title)) return;

            if (!mkdirs(dest.parent)) { alert("Impossible de créer le dossier :\n" + dest.parent.fsName); return; }

            if (isOpen) {
                app.project.save(dest);
            } else {
                if (!a.file.copy(dest.fsName)) { alert("Copie impossible :\n" + a.file.error); return; }
                openAep(dest);
            }
            refresh();
        }

        function askName(def) {
            var d = new Window("dialog", "Dupliquer sous…");
            d.alignChildren = ["fill", "top"];
            d.add("statictext", undefined, "Nouveau nom (sans .aep) :");
            var et = d.add("edittext", undefined, def);
            et.characters = 45;
            et.active = true;
            var hint = d.add("statictext", undefined, "Minuscules, chiffres, « _ » et « - » uniquement");
            var g = d.add("group");
            g.alignment = ["right", "top"];
            var bCancel = g.add("button", undefined, "Annuler", { name: "cancel" });
            var bOk = g.add("button", undefined, "Dupliquer", { name: "ok" });
            var result = null;
            bOk.onClick = function () {
                var v = et.text.replace(/\.aep$/i, "");
                if (!NAME_RULE.test(v)) {
                    hint.text = "Nom invalide : minuscules, chiffres, « _ » et « - » uniquement";
                    return;
                }
                result = v;
                d.close(1);
            };
            bCancel.onClick = function () { d.close(2); };
            d.show();
            return result;
        }

        btnVersion.onClick = function () {
            var a = actionSource(true);
            if (!a) return;
            var info = parseName(a.file);
            var dest = freeFile(a.file.parent, info, info.stage, info.version + 1);
            createFrom(a, dest, "Nouvelle version");
        };

        btnStage.onClick = function () {
            var a = actionSource(true);
            if (!a) return;
            var info = parseName(a.file);
            var idx = stageIndex(info.stage);
            if (idx < 0) {
                alert("L'étape « " + info.stage + " » n'est pas dans la configuration :\n" + CONFIG_FILE.fsName);
                return;
            }
            if (idx >= cfg.stages.length - 1) { alert("« " + info.stage + " » est déjà la dernière étape."); return; }
            var next = cfg.stages[idx + 1];
            var folder = new Folder(selectedProject().folder.fsName + "/" + next.folder);
            var dest = freeFile(folder, info, next.name, 1);
            createFrom(a, dest, "Passer à l'étape « " + next.name + " »");
        };

        btnDup.onClick = function () {
            var a = actionSource(false);
            if (!a) return;
            var name = askName(a.file.displayName.replace(/\.aep$/i, "").toLowerCase());
            if (!name) return;
            createFrom(a, new File(a.file.parent.fsName + "/" + name + ".aep"), "Dupliquer");
        };

        btnFolder.onClick = function () {
            var a = selectedAep();
            var p = selectedProject();
            if (a) a.file.parent.execute();
            else if (p) p.folder.execute();
        };

        // Les tableaux se partagent la hauteur disponible, entre LIST_H_MIN et LIST_H_MAX
        function fitLists() {
            if (!main.size || !win.size) return;
            var fixed = main.size[1] - listProj.size[1] - listAep.size[1];
            var h = (win.size[1] - 2 * MARGIN - fixed) / 2;
            sizeList(listProj, h);
            sizeList(listAep, h);
            win.layout.layout(true);
        }

        win.onResizing = win.onResize = function () {
            this.layout.resize();
            fitLists();
        };

        refresh();

        if (win instanceof Window) {
            win.center();
            win.show();
            fitLists();
        } else {
            win.layout.layout(true);
            fitLists();
        }
        return win;
    }

    buildUI(thisObj);

})(this);
