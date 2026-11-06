//SCRIPT TO DUPLICATE LAYERS

//UI PANEL
{
    function myScript(thisObj) {

        var myPanel;

        function myScript_buildUI(thisObj) {
            myPanel = (thisObj instanceof Panel) ? thisObj : new Window("palette", "SDuplicate_Layers", undefined, {resizeable:true});

            res = "group{\
                orientation:'row',\
                groupOne: Group{\
                    orientation:'column',\
                    myEditText: EditText{\
                        text:'NumberOfLayer'\
                    },\
                    myButton: Button{\
                        text: 'Duplicate'\
                    },\
                },\
            }";

            myPanel.grp = myPanel.add(res);

            //SCRIPT FUNCTION
            myPanel.grp.groupOne.myButton.onClick = function() {
               duplicate();
            }

            myPanel.layout.layout(true);

            return myPanel;
        }


        function on_textInput_changed() {
        // Set the duplicate number based on the text.
        // check that its a number not letters

            var value = parseInt(myPanel.grp.groupOne.myEditText.text);

            if ( !value || value < 0 ) {
                alert(value + " is not a number. Please enter a number.", scriptName);
            } else {
                theNumVal = value;
            }
        }


        function duplicate() {
        // Duplicate layers

            var undoStr = "Duplicate Layers";
            
            app.beginUndoGroup( undoStr );
            
            on_textInput_changed();

            var myComp = app.project.activeItem;

            if (myComp == null || !(myComp instanceof CompItem)) { 

                alert("A Composition must be active to run this script");

            } else {

                var myLayer = myComp.selectedLayers;
                
                if (myLayer == null) {
                    alert ("Select a Layer");
                } else {
                
                    var thisLayer = myComp.selectedLayers[0];
                    
                    if(thisLayer){

                        thisLayer.threeDLayer = false;
                        
                        thisLayer.duplicate();

                        for (i = 0; i < (theNumVal-1); i++) { 
                            thisLayer.duplicate();
                        }

                    } else {
                        alert("Select a layer first to Duplicate.")
                        app.endUndoGroup();
                    }
                }
            }
        } 

        var myScriptPal = myScript_buildUI(thisObj);

        if ((myScriptPal!= null) && (myScriptPal instanceof Window)) {
            myScriptPal.center();
            myScriptPal.show();
        }
    }

    myScript(this);
}