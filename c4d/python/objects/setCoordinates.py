"""
Copie la position, la rotation et l'échelle d'un objet sur un autre.

Utilisation :
  1. Sélectionner l'objet source, puis l'objet cible
     (l'ordre de sélection compte)
  2. Lancer le script
"""

import c4d
from c4d import gui

def main(): 
    obj = doc.GetOrderedActiveObjects()  
    if len(obj)!= 2:
        gui.MessageDialog('Select two objects please')
        
    source = obj[0]
    target = obj[1]
    sourcePos = source.GetAbsPos()
    sourceScale = source.GetAbsScale()
    sourceRot = source.GetAbsRot()
    
    doc.AddUndo(c4d.UNDOTYPE_CHANGE, target)

    doc.StartUndo()
    target.SetAbsPos(sourcePos)
    target.SetAbsScale(sourceScale)
    target.SetAbsRot(sourceRot)
    c4d.EventAdd()
    doc.EndUndo()
    

if __name__=='__main__':
    main()