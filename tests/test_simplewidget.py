import unittest

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import QGridLayout, QGroupBox, QPushButton, QWidget
from qgis.PyQt.QtWidgets import QSizePolicy
from qgis.gui import QgsSpinBox
from qps.simplewidgets import DoubleSliderSpinBox, FlowLayout, SliderSpinBox, ResizableImageLabel
from qps.testing import TestCase, start_app
from scripts.create_runtests import DIR_REPO

start_app()


class SimpleWidgetTests(TestCase):

    def test_resizable_qlabel(self):

        path_logo = DIR_REPO / 'qps/pyqtgraph/tests/images/roi/polylineroi/closed_drag_new_handle.png'
        label = ResizableImageLabel()
        label.setWindowTitle(label.__class__.__name__)
        label.setPixmap(QPixmap(path_logo.as_posix()))
        label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        label.setAlignment(Qt.AlignTop)
        label.setMinimumSize(50, 50)

        self.showGui(label)

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
