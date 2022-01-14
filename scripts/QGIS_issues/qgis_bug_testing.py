
from qgis.testing import TestCase, start_app
from qps.testing import start_app as start_app2
from qps.plotstyling.plotstyling import PlotStyleButton, pen2tuple, PlotStyle, XMLTAG_PLOTSTYLENODE, \
    createSetPlotStyleAction, MarkerSymbol, tuple2pen, registerPlotStyleEditorWidget, PlotStyleEditorWidgetFactory, \
    PlotStyleEditorWidgetWrapper, PlotStyleWidget, MarkerSymbolComboBox, PlotStyleEditorConfigWidget


class PlotStyleTests(TestCase):
    @classmethod
    def setUpClass(cls) -> None:

        cls.app = start_app2(cleanup=True)


    def test_case1(self):
        self.assertTrue(True)


