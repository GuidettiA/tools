// Controller l'opacité d'un calque

// Afficher si la case est cochée
comp().layer().effect()(1) > 0 ? 100 : 0; // Sélectionner l'effet case à cocher

// ou si besoin de controller avec plusieurs cases
case1 = comp().layer().effect()(1) ; // Sélectionner l'effet case à cocher
case2 = comp().layer().effect()(1) ;// Sélectionner l'effet case à cocher
case1 > 0 && case2 > 0 ? 100 : 0; // exemple ici avec &&