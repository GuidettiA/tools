// Applique une animation auto au début et à la fin d'un calque

// à 1 dimension
easeInDuration = 1;  // Durée de l'ease in (secondes)
easeOutDuration = 2; // Durée de l'ease out (secondes)
startValue = 0;   // Valeur minimale
endValue = 100;   // Valeur maximale

totalDuration = outPoint - inPoint;
easeInEnd = inPoint + easeInDuration;
easeOutStart = outPoint - easeOutDuration;

if (time < easeInEnd) {
    ease(time, inPoint, easeInEnd, startValue, endValue);
} else if (time > easeOutStart) {
    ease(time, easeOutStart, outPoint, endValue, startValue);
} else {
    endValue;
}


// à 2 dimensions
easeInDuration = 1;  // Durée de l'ease in (secondes)
easeOutDuration = 2; // Durée de l'ease out (secondes)
startValue = [0, 0];   // Valeur minimale
endValue = [500, 300]; // Valeur maximale

totalDuration = outPoint - inPoint;
easeInEnd = inPoint + easeInDuration;
easeOutStart = outPoint - easeOutDuration;

if (time < easeInEnd) {
    t = (time - inPoint) / easeInDuration;
    result = [];
    for (i = 0; i < startValue.length; i++) {
        result[i] = ease(t, 0, 1, startValue[i], endValue[i]);
    }
    result;
} else if (time > easeOutStart) {
    t = (time - easeOutStart) / easeOutDuration;
    result = [];
    for (i = 0; i < startValue.length; i++) {
        result[i] = ease(t, 0, 1, endValue[i], startValue[i]);
    }
    result;
} else {
    endValue;
}