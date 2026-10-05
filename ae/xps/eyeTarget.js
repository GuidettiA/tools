// Pour créer un controller permettant d'animer facilement les yeux d'un personnage
// Appliquer sur la position de chaque pupille

target = thisComp.layer("Target"); // Sélectionner le calque cible
maxRadius = target.effect("maxDep")(1); // Créer un slider pour controler le rayon max de déplacement (en pixels)

baseWorldPos = toWorld(transform.anchorPoint);
targetWorldPos = target.toWorld(target.transform.anchorPoint);
delta = targetWorldPos - baseWorldPos;

if (delta.length > 0) {
    d = length([delta[0], delta[1]]);
    
    if (d > 0) {
        dir = [delta[0], delta[1]] / d;
        offset = dir * Math.min(d, maxRadius);
        value + offset;
    } else {
        value;
    }
} else {
    value;
}