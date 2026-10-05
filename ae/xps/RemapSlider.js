// Controler le remappage temporel avec un slider entre 0% et 100%

ctrl = effect("remap")(1); // Sélectionner un slider

debut = key(1).value;
fin = key(2).value;
linear(ctrl, 0, 100, debut, fin);