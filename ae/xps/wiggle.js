// Wiggle sur une ou plusieurs dimensions avec ou sans boucle

freq = effect("freq")(1); // Sélectionner un slider
amp = effect("amp")(1); // Sélectionner un slider
// Sélectionner un slider pour controler la durée de la boucle (en seconde)
// si 0 : désactive l'effet de boucle
loopTime = effect("loopTime")(1);

// Choisir l'activation du wiggle sur chaque dimension
useX = true;
useY = true;
useZ = false;

if (loopTime > 0) {
    t = time % loopTime;
    w1 = wiggle(freq, amp, 1, 0.5, t);
    w2 = wiggle(freq, amp, 1, 0.5, t - loopTime);
    wCalc = linear(t, 0, loopTime, w1, w2);
} else {
    wCalc = wiggle(freq, amp);
}

w = wCalc - value;

x = value[0] + (useX ? w[0] : 0);
y = value[1] + (useY ? w[1] : 0);

if (value.length > 2) {
    z = value[2] + (useZ ? w[2] : 0);
    [x, y, z];
} else {
    [x, y];
}