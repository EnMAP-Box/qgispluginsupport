# -*- coding: utf-8 -*-
"""Unit tests to test issues in the QGIS API

"""
__author__ = 'Benjamin Jakimow'
__date__ = '2019/01/21'
# This will get replaced with a git SHA1 when you do a git archive
__revision__ = '$Format:%H$'

from qgis.core import *
from qgis.gui import *
from qgis.PyQt.QtCore import *
from qgis.PyQt.QtGui import *
from qgis.testing import start_app, unittest

start_app()


class TestQgsFeature(unittest.TestCase):

    def test_QgsMapMouseEvent(self):
        canvas = QgsMapCanvas()
        canvas.setFixedSize(300, 300)

        pos = QPointF(0.5 * canvas.width(), 0.5 * canvas.height())
        # this works
        mouseEvent = QMouseEvent(QEvent.MouseButtonPress, pos, Qt.LeftButton, Qt.LeftButton, Qt.NoModifier)


        qgsMouseEvent1 = QgsMapMouseEvent(canvas, mouseEvent)
        self.assertIsInstance(qgsMouseEvent1, QgsMapMouseEvent)

        # fails
        qgsMouseEvent2 = QgsMapMouseEvent(
            canvas,
            QEvent.MouseButtonPress,
            QPointF(0.5 * canvas.width(), 0.5 * canvas.height()).toPoint(),
            Qt.LeftButton,
            Qt.LeftButton,
            Qt.NoModifier)
        self.assertIsInstance(qgsMouseEvent2, QgsMapMouseEvent)

if __name__ == '__main__':
    unittest.main()
