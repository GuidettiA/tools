// Maintenir l'échelle visuellement même en temps qu'enfant

if (hasParent) {
    ps = parent.transform.scale.value;
    value.map((v, i) => v * 100 / (ps[i] || 0.0001));
} else {
    value;
}