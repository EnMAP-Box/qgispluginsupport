import unittest

from qps.testing import TestCase, TestObjects, start_app
from qps.vectorlayertools import VectorLayerTools

start_app()


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
        assert tools.startEditing(lyr)

        self.assertTrue(self.cntEdits == 1)
        # tools.addFeature(lyr, None, f0.geometry(), f0)
        assert tools.stopEditing(lyr, True)
        assert tools.stopEditing(lyr, False)
        assert tools.saveEdits(lyr)
        tools.commitError(lyr)


if __name__ == "__main__":
    unittest.main(buffer=False)
