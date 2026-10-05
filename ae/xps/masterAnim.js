// Pour suivre une animation sur une propriété avec offset

target = thisComp.layer("master"); // Sélectionner le calque master
delay = effect("Offset")(1); // Sélectionner un slider (en secondes)
masterProp = target.transform(thisProperty.name); // Récupère dynamiquement la même propriété sur le master

tDelayed = time - inPoint + target.inPoint - delay;
tStart = target.inPoint;
delta = masterProp.valueAtTime(tDelayed) - masterProp.valueAtTime(tStart);
value + delta;