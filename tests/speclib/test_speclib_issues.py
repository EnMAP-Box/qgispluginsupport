from qps import initAll
from qps.layerproperties import AttributeTableWidget
from qps.speclib.gui.spectrallibrarywidget import SpectralLibraryWidget
from qps.testing import TestCase, start_app, TestObjects

start_app()
initAll()


# registerSpectralProfileEditorWidget()
# registerEditorWidgets()
#
# registerMapLayerConfigWidgetFactories()

class SpeclibOtherIssueTests(TestCase):


    def test_edit_formview(self):

        lyr = TestObjects.createSpectralLibrary(2)

        w = SpectralLibraryWidget(speclib=lyr)
        w.setViewVisibility(SpectralLibraryWidget.ViewType.FormView | SpectralLibraryWidget.ViewType.ProfileView)
        lyr.startEditing()


        self.showGui(w)