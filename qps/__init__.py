import sys
try:
    import qps.qpsresources
    qpsresources.qInitResources()
except Exception as ex:

    print(ex, file=sys.stderr)
    print('It might be required to compile the qps/resources.py first', file=sys.stderr)



def registerEditorWidgets():

    import qps.speclib
    qps.speclib.registerSpectralProfileEditorWidget()

    import qps.classification.classificationscheme
    qps.classification.classificationscheme.registerClassificationSchemeEditorWidget()

    import qps.plotstyling.plotstyling
    qps.plotstyling.plotstyling.registerPlotStyleEditorWidget()