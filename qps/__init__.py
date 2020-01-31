import sys, importlib, site, os, pathlib
from qgis.core import QgsApplication
from qgis.gui import QgisInterface
__version__ = '0.2'

def initResources():
    """
    Initializes compiled Qt resources
    """
    import importlib.util
    for r, dirs, files in os.walk(pathlib.Path(__file__).parent):
        root = pathlib.Path(r)
        for f in [f for f in files if f.endswith('_rc.py')]:
            path = root / f
            name = f[:-3]
            spec = importlib.util.spec_from_file_location(name, path)
            rcModule = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(rcModule)
            rcModule.qInitResources()


def registerEditorWidgets():
    """
    Call this function to register QgsEditorwidgetFactories to the QgsEditorWidgetRegistry
    It is required that a QgsApplication has been instantiated.
    """
    assert isinstance(QgsApplication.instance(), QgsApplication), 'QgsApplication has not been instantiated'

    try:
        from .speclib.spectrallibraries import registerSpectralProfileEditorWidget
        registerSpectralProfileEditorWidget()
    except Exception as ex:
        print('Failed to call qps.speclib.spectrallibraries.registerSpectralProfileEditorWidget()', file=sys.stderr)
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

    initResources()
    registerEditorWidgets()