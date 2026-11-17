// swap-pass.jsx — remplace, dans le projet After Effects ouvert, toutes les séquences
//   .../<FROM>/<rendu>_<FROM>_####.tif   par   .../<TO>/<rendu>_<TO>_####.tif
// (arborescence produite par exr2tiff : <rendu>/<passe>/<rendu>_<passe>_<frame>.tif)
//
// Usage : Fichier > Scripts > Exécuter le fichier de script…
// Annulable en une fois avec Ctrl+Z.

// ---- Réglages -------------------------------------------------------------
var FROM = "Beauty";   // passe à remplacer
var TO   = "main";     // passe de remplacement
var ASK  = true;       // true : demande les deux passes au lancement (pré-remplies)
// ---------------------------------------------------------------------------

(function () {
    var proj = app.project;
    if (!proj) { alert("Aucun projet ouvert."); return; }

    var from = FROM, to = TO;
    if (ASK) {
        from = prompt("Passe à remplacer :", FROM);
        if (from === null) return;
        to = prompt("Remplacer « " + from + " » par la passe :", TO);
        if (to === null) return;
    }
    // exr2tiff remplace les espaces des noms de passes par des _
    from = from.replace(/^\s+|\s+$/g, "").replace(/ /g, "_");
    to   = to.replace(/^\s+|\s+$/g, "").replace(/ /g, "_");
    if (!from || !to || from === to) { alert("Passes invalides."); return; }

    var esc = function (s) { return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); };
    var re = new RegExp("_" + esc(from) + "_(\\d+\\.tiff?)$", "i");

    var todo = [], missing = [];

    for (var i = 1; i <= proj.numItems; i++) {
        var it = proj.item(i);
        if (!(it instanceof FootageItem)) continue;
        var src = it.mainSource;
        if (!(src instanceof FileSource) || !src.file) continue;

        var f = src.file, dir = f.parent;
        if (!dir || decodeURI(dir.name).toLowerCase() !== from.toLowerCase()) continue;

        var name = decodeURI(f.name);
        if (!re.test(name)) continue;

        var nf = new File(dir.parent.fsName + "/" + to + "/" + name.replace(re, "_" + to + "_$1"));
        if (nf.exists) todo.push({ item: it, file: nf });
        else missing.push(it.name + "\n   → introuvable : " + nf.fsName);
    }

    if (!todo.length && !missing.length) {
        alert("Aucune séquence « " + from + " » trouvée dans le projet.");
        return;
    }

    var msg = todo.length + " séquence(s) " + from + " à remplacer par " + to + ".";
    if (missing.length) msg += "\n" + missing.length + " sans équivalent " + to + " (ignorées).";
    if (!todo.length) { alert(msg + "\n\n" + missing.join("\n")); return; }
    if (!confirm(msg + "\n\nContinuer ?")) return;

    app.beginUndoGroup(from + " → " + to);
    var done = 0, errors = [];
    for (var j = 0; j < todo.length; j++) {
        var t = todo[j], s = t.item.mainSource;
        // Interprétation à conserver
        var keep = {
            alphaMode: s.alphaMode,
            premulColor: s.premulColor,
            invertAlpha: s.invertAlpha,
            conformFrameRate: s.conformFrameRate,
            loop: s.loop
        };
        try {
            t.item.replaceWithSequence(t.file, false);
            var s2 = t.item.mainSource;
            try { if (keep.conformFrameRate > 0) s2.conformFrameRate = keep.conformFrameRate; } catch (e1) {}
            try { s2.loop = keep.loop; } catch (e2) {}
            try { s2.alphaMode = keep.alphaMode; } catch (e3) {}
            try { s2.invertAlpha = keep.invertAlpha; } catch (e4) {}
            try { if (keep.alphaMode === AlphaMode.PREMULTIPLIED) s2.premulColor = keep.premulColor; } catch (e5) {}
            done++;
        } catch (e) {
            errors.push(t.item.name + " : " + e.toString());
        }
    }
    app.endUndoGroup();

    var report = done + " séquence(s) remplacée(s) : " + from + " → " + to + ".";
    if (errors.length) report += "\n\nErreurs :\n" + errors.join("\n");
    if (missing.length) report += "\n\nIgnorées (pas de " + to + ") :\n" + missing.join("\n");
    alert(report);
})();
