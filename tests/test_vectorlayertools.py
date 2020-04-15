
import unittest
from qps.testing import TestObjects, TestCase
from qps.vectorlayertools import VectorLayerTools

class TestCasesVectorLayerTools(TestCase):


    def test_VectorLayerTools(self):
        lyr0 = TestObjects.createVectorLayer()
        lyr = TestObjects.createVectorLayer()

        f0 = lyr0.getFeature(0)
        tools = VectorLayerTools()

        self.cntEdits = 0
        messages = []
        def onEditingStarted():
            self.cntEdits += 1
        def onMessage(*args):
            messages.append(args)

        tools.sigEditingStarted.connect(onEditingStarted)
        tools.sigMessage.connect(onMessage)
        tools.startEditing(lyr)

        self.assertTrue(self.cntEdits == 1)
        #tools.addFeature(lyr, None, f0.geometry(), f0)
        tools.stopEditing(lyr, True)
        tools.stopEditing(lyr, False)
        tools.commitError(lyr)
        tools.saveEdits(lyr)
        tools.commitError(lyr)


if __name__ == "__main__":
    import xmlrunner
    unittest.main(testRunner=xmlrunner.XMLTestRunner(output='test-reports'), buffer=False)


