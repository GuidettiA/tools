// apparition_points_null.jsx
// Fait apparaître chaque point d'un calque de forme (issu d'un .ai)
// à partir de la position d'un nul "Origine", via un linear de 0 à 100 %
// sur l'échelle de chaque point.
//
// Utilisation :
// 1. Le .ai doit être converti : clic droit > Créer > Créer des formes
//    à partir d'un calque vectoriel.
// 2. Sélectionner le calque de forme obtenu.
// 3. Fichier > Scripts > Exécuter le fichier de script…
//
// - Si un calque nommé "Origine" existe dans la compo, il est utilisé ;
//   sinon un nul "Origine" est créé au centre de la compo.
// - Curseurs ajoutés sur le calque de forme :
//   "Étalement" : temps (s) pour que la vague parcoure la demi-diagonale de la grille
//   "Durée"     : durée (s) de l'apparition de chaque point
// - Le script peut être relancé (il réutilise curseurs et nul, et ne
//   retouche pas les ancrages déjà en place, ce qui accélère la relance).

(function () {
    var ORIGIN_NAME = "Origine";

    var comp = app.project.activeItem;
    if (!(comp instanceof CompItem) || comp.selectedLayers.length !== 1) {
        alert("Sélectionne un seul calque de forme dans la compo.");
        return;
    }
    var layer = comp.selectedLayers[0];
    if (layer.matchName !== "ADBE Vector Layer") {
        alert("Le calque sélectionné doit être un calque de forme.");
        return;
    }

    app.beginUndoGroup("Apparition des points depuis un nul");

    // --- Nul d'origine ---
    var origin = null;
    for (var li = 1; li <= comp.numLayers; li++) {
        if (comp.layer(li).name === ORIGIN_NAME) { origin = comp.layer(li); break; }
    }
    if (!origin) {
        origin = comp.layers.addNull();
        origin.name = ORIGIN_NAME;
        origin.property("ADBE Transform Group").property("ADBE Position")
            .setValue([comp.width / 2, comp.height / 2]);
        layer.selected = true;
    }

    // --- Effets de contrôle (ajoutés AVANT de parcourir les groupes) ---
    var fx = layer.property("ADBE Effect Parade");
    function control(name, matchName, val) {
        var c = fx.property(name);
        if (!c) {
            c = fx.addProperty(matchName);
            c.name = name;
            if (val !== undefined) c.property(1).setValue(val);
        }
        return c;
    }
    control("Étalement", "ADBE Slider Control", 1.5);
    control("Durée", "ADBE Slider Control", 0.4);
    // Position du nul convertie dans l'espace du calque, calculée une seule
    // fois par image (bien plus léger que de la calculer dans chaque point).
    var originCtrl = control(ORIGIN_NAME, "ADBE Point Control");
    originCtrl.property(1).expression =
        "var n = thisComp.layer(\"" + ORIGIN_NAME + "\");\n" +
        "fromComp(n.toComp(n.anchorPoint));";

    // --- Centre local d'un groupe-point (boîte englobante du tracé) ---
    function localCenter(grp) {
        var items = grp.property("ADBE Vectors Group");
        for (var i = 1; i <= items.numProperties; i++) {
            var p = items.property(i);
            if (p.matchName === "ADBE Vector Shape - Group") {
                var v = p.property("ADBE Vector Shape").value.vertices;
                if (!v.length) continue;
                var x0 = v[0][0], x1 = v[0][0], y0 = v[0][1], y1 = v[0][1];
                for (var k = 1; k < v.length; k++) {
                    if (v[k][0] < x0) x0 = v[k][0];
                    if (v[k][0] > x1) x1 = v[k][0];
                    if (v[k][1] < y0) y0 = v[k][1];
                    if (v[k][1] > y1) y1 = v[k][1];
                }
                return [(x0 + x1) / 2, (y0 + y1) / 2];
            }
            if (p.matchName === "ADBE Vector Shape - Ellipse") {
                return p.property("ADBE Vector Ellipse Position").value;
            }
        }
        return null;
    }

    // --- Récupère tous les groupes qui contiennent directement un tracé ---
    var dots = [];
    function walk(container) {
        for (var i = 1; i <= container.numProperties; i++) {
            var g = container.property(i);
            if (g.matchName !== "ADBE Vector Group") continue;
            var c = localCenter(g);
            if (c) {
                var tr = g.property("ADBE Vector Transform Group");
                var A = tr.property("ADBE Vector Anchor").value;
                var P = tr.property("ADBE Vector Position").value;
                dots.push({
                    tr: tr,
                    local: c,
                    done: (Math.abs(A[0] - c[0]) < 0.01 && Math.abs(A[1] - c[1]) < 0.01),
                    pos: [P[0] + c[0] - A[0], P[1] + c[1] - A[1]]
                });
            } else {
                walk(g.property("ADBE Vectors Group"));
            }
        }
    }
    walk(layer.property("ADBE Root Vectors Group"));

    if (!dots.length) {
        app.endUndoGroup();
        alert("Aucun point trouvé dans ce calque.");
        return;
    }

    // --- Distance de référence : demi-diagonale de la grille ---
    var minX = dots[0].pos[0], maxX = minX, minY = dots[0].pos[1], maxY = minY;
    for (var i = 1; i < dots.length; i++) {
        var p = dots[i].pos;
        if (p[0] < minX) minX = p[0];
        if (p[0] > maxX) maxX = p[0];
        if (p[1] < minY) minY = p[1];
        if (p[1] > maxY) maxY = p[1];
    }
    var D = Math.sqrt(Math.pow(maxX - minX, 2) + Math.pow(maxY - minY, 2)) / 2;
    if (D === 0) D = 1;
    D = Math.round(D * 100) / 100;

    // --- Ancre au centre de chaque point + expression d'échelle ---
    for (i = 0; i < dots.length; i++) {
        var dt = dots[i];
        if (!dt.done) {
            dt.tr.property("ADBE Vector Anchor").setValue(dt.local);
            dt.tr.property("ADBE Vector Position").setValue(dt.pos);
        }
        var px = Math.round(dt.pos[0] * 100) / 100;
        var py = Math.round(dt.pos[1] * 100) / 100;
        dt.tr.property("ADBE Vector Scale").expression =
            "var d = length([" + px + ", " + py + "], effect(\"" + ORIGIN_NAME + "\")(1));\n" +
            "var t = time - inPoint - d / " + D + " * effect(\"Étalement\")(1);\n" +
            "var s = linear(t, 0, effect(\"Durée\")(1), 0, 100);\n" +
            "[s, s]";
    }

    app.endUndoGroup();
    alert(dots.length + " points animés depuis le nul \"" + ORIGIN_NAME + "\".");
})();
