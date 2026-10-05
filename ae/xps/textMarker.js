// Controler un calque texte avec des marqueurs

ref = thisLayer; // Le calque courant, sinon sélectionner un autre calque

if (ref.marker.numKeys > 0) {
    m = ref.marker.nearestKey(time);
    mTime = m.time > time && m.index > 1 ? ref.marker.key(m.index - 1).time : m.time;
    time >= mTime ? ref.marker.nearestKey(mTime).comment : value;
} else {
    value;
}