import unittest


from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QPushButton, QGroupBox
from qgis.PyQt.QtWidgets import QWidget, QGridLayout
from qgis.gui import QgsSpinBox
from qps.simplewidgets import SliderSpinBox, DoubleSliderSpinBox, FlowLayout
from qps.testing import TestCase


class SimpleWidgetTests(TestCase):

    def test_FlowLayout(self):

        w = QGroupBox()
        flowLayout = FlowLayout()
        flowLayout.setSpacing(0)
        flowLayout.setContentsMargins(0, 0, 0, 0)
        for i in range(10):
            btn = QPushButton(f'Button {i + 1}')
            flowLayout.addWidget(btn)
        w.setLayout(flowLayout)
        self.assertIsInstance(w.layout(), FlowLayout)
        s = ""
        self.showGui(w)

    def test_SliderSpinBox(self):

        sb = SliderSpinBox()
        sbl = DoubleSliderSpinBox()

        gridLayout = QGridLayout()
        for row, a in enumerate([Qt.AlignLeft, Qt.AlignRight, Qt.AlignTop, Qt.AlignBottom]):
            for col, sb in enumerate([SliderSpinBox(spinbox=QgsSpinBox(), spinbox_position=a),
                                      SliderSpinBox(spinbox_position=a),
                                      DoubleSliderSpinBox(spinbox_position=a)]):
                sb.setValue(10)
                sb.setMinimum(-10)
                sb.setMaximum(100)
                gridLayout.addWidget(sb, row, col)

        w = QWidget()
        w.setLayout(gridLayout)
        self.showGui(w)


if __name__ == '__main__':
    unittest.main(buffer=False)
