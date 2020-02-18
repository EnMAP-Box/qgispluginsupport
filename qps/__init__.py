import sys, importlib, site, os, pathlib
from qgis.core import QgsApplication
from qgis.gui import QgisInterface
__version__ = '0.3'

DIR_UI_FILES = pathlib.Path(__file__).parent / 'ui'
DIR_ICONS = DIR_UI_FILES / 'icons'
QPS_RESOURCE_FILE = pathlib.Path(__file__).parent / 'qpsresources_rc.py'

def registerEditorWidgets():
    """
    Call this function to register QgsEditorwidgetFactories to the QgsEditorWidgetRegistry
    It is required that a QgsApplication has been instantiated.
    """
    assert isinstance(QgsApplication.instance(), QgsApplication), 'QgsApplication has not been instantiated'

    try:
        from .speclib.gui import registerSpectralProfileEditorWidget
        registerSpectralProfileEditorWidget()
    except Exception as ex:
        print('Failed to call qps.speclib.core.registerSpectralProfileEditorWidget()', file=sys.stderr)
        print(ex, file=sys.stderr)

    try:
        from .speclib.qgsfunctions import registerQgsExpressionFunctions
        registerQgsExpressionFunctions()
    except Exception as ex:
        print('Failed to call qps.speclib.qgsfunctions.registerQgsExpressionFunctions()', file=sys.stderr)
        print(ex, file=sys.stderr)

    try:
        from .classification.classificationscheme import registerClassificationSchemeEditorWidget
        registerClassificationSchemeEditorWidget()
    except Exception as ex:
        print('Failed to call qps.classification.classificationscheme.registerClassificationSchemeEditorWidget()',
              file=sys.stderr)
        print(ex, file=sys.stderr)

    try:
        from .plotstyling.plotstyling import registerPlotStyleEditorWidget
        registerPlotStyleEditorWidget()
    except Exception as ex:
        print('Failed to call qps.plotstyling.plotstyling.registerPlotStyleEditorWidget()', file=sys.stderr)
        print(ex, file=sys.stderr)



def initAll():

    from .testing import initResourceFile
    initResourceFile(QPS_RESOURCE_FILE)
    registerEditorWidgets()