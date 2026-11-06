// Générer un nombre aléatoire fixe

seed = 12; // Changer pour faire varier le nombre
decimals = 1; // Nombre de chiffres après la virgule

seedRandom(index, true);
myValue = random(seed);
factor = Math.pow(10, decimals);
Math.round(myValue * factor) / factor;