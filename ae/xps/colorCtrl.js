// Controler la couleur en faisant varier uniquement la teinte

var ctrl = effect("HueValue")(1); // Sélectionner un slider
h = ((ctrl % 360) + 360) % 360;


function hsbToRgb(h, s, b) {
  h = h / 360;
  s = s / 100;
  b = b / 100;
  var r, g, bl;
  var i = Math.floor(h * 6);
  var f = h * 6 - i;
  var p = b * (1 - s);
  var q = b * (1 - f * s);
  var t = b * (1 - (1 - f) * s);

  switch (i % 6) {
    case 0: r = b; g = t; bl = p; break;
    case 1: r = q; g = b; bl = p; break;
    case 2: r = p; g = b; bl = t; break;
    case 3: r = p; g = q; bl = b; break;
    case 4: r = t; g = p; bl = b; break;
    case 5: r = b; g = p; bl = q; break;
  }
  return [r, g, bl, 1];
}

hsbToRgb(h, 100, 33);