// Obtenir une position relative en pourcentage entre deux calques

obj1 = thisComp.layer("calque 1"); // Sélectionner le premier objet
obj2 = thisComp.layer("calque 2");// Sélectionner le second objet
factor = effect("relative")(1); // Sélectionner le slider pour la position relative entre les deux objets (en pourcentage)

p1 = obj1.transform.position;
p2 = obj2.transform.position;
linear(factor, 0, 100, p2, p1);