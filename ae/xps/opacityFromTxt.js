// Controler l'opcacité d'un calque en fonction d'un calque de texte

ref = thisComp.layer("texte"); // Sélectionner le calque texte
txt = "VISIBLE"; // Changer la valeur du texte qui rend le calque visible
ref.text.sourceText.value == txt ? 100 : 0;