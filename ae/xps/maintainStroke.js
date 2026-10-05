// Pour faire en sorte que l'épaisseur du contour soit toujours visuellement constant

stroke = effect("stroke")(1); // Sélectionner un slider 
s = transform.scale;

Math.abs(stroke / (s[0] / 100));