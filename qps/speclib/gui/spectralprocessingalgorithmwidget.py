from typing import List

from PyQt6.QtWidgets import QDialog
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QCheckBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
)
from qgis.core import QgsProcessingAlgorithm, QgsVectorLayer
from qgis.gui import QgsPanelWidget

from .spectralprocessingalgorithmmodel import SpectralProcessingAlgorithmModel
from .spectralprocessingcontextgenerator import SpectralProcessingContextGenerator
from .spectralprocessingparameterswidget import SpectralProcessingParametersWidget
from ...reimplementation.processingalgorithmdialog import ProcessingAlgorithmDialog
from ...reimplementation.processingalgorithmwidget import ProcessingAlgorithmWidget


class SpectralProcessingAlgorithmWidget(ProcessingAlgorithmWidget):

    def __init__(self, speclib, *args, algorithm=None, **kwds):
        if not isinstance(speclib, QgsVectorLayer):
            raise TypeError('speclib must be a QgsVectorLayer')

        super().__init__(algorithm, *args, **kwds)

        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        # QgsProcessingContextGenerator.__init__(self)
        self.mWidgetName = 'Spectral Processing Widget'
        self.setWindowTitle(self.mWidgetName)
        self.setWindowIcon(QIcon(r':/qps/ui/icons/profile_processing.svg'))
        self.btnAlgorithm: QPushButton = QPushButton('Algorithm')
        self.btnAlgorithm.setIcon(QIcon(':/images/themes/default/processingAlgorithm.svg'))
        self.btnAlgorithm.clicked.connect(self.setAlgorithmFromDialog)

        self.mTemporaryRaster: List[str] = []
        self.tbAlgorithmName: QLineEdit = QLineEdit()
        self.tbAlgorithmName.setPlaceholderText('Select a raster processing algorithm / model')
        self.tbAlgorithmName.setReadOnly(True)
        self.tbAlgorithmName.setAutoFillBackground(True)
        self.tbAlgorithmName.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))

        self.cbSelectedFeaturesOnly = QCheckBox('Only process selected features')

        self.mTopGrid = QGridLayout()
        self.mTopGrid.addWidget(self.btnAlgorithm, 0, 0)
        self.mTopGrid.addWidget(self.tbAlgorithmName, 0, 1)
        self.mTopGrid.addWidget(self.cbSelectedFeaturesOnly, 1, 0, 1, 2)

        # self.btnAlgorithm.clicked.connect(self.actionSetAlgorithm.trigger)
        self.layout().insertLayout(0, self.mTopGrid)
        self.mProcessingAlgorithmModel: SpectralProcessingAlgorithmModel = SpectralProcessingAlgorithmModel()

        self.mContextGenerator = SpectralProcessingContextGenerator(speclib)

        self.mSpeclib = speclib

        self._parameters_panel = self.createParametersPanel(
            self.inPlace(), self.mSpeclib, self.messageBar()
        )
        self.setMainWidget(self._parameters_panel)

    def createParametersPanel(self, inPlaceMode, activeLayer, messageBar):
        a = self.algorithm()
        if isinstance(a, QgsProcessingAlgorithm) and isinstance(self.speclib(), QgsVectorLayer):
            widget = SpectralProcessingParametersWidget(
                a, inPlaceMode, activeLayer, messageBar, speclib=self.speclib())
            widget.registerProcessingContextGenerator(self.mContextGenerator)
            widget.registerWidgetContextGenerator(self.mContextGenerator)
            widget.registerProcessingParametersGenerator(self.mContextGenerator)
            widget.initWidgets()
            return widget
        else:
            w = QgsPanelWidget()
            l = QHBoxLayout()
            label = QLabel('Select an algorithm')
            l.addWidget(label)
            w.setLayout(l)
            return w

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def setAlgorithmFromDialog(self):

        d = ProcessingAlgorithmDialog(parent=self)
        d.setAlgorithmModel(self.mProcessingAlgorithmModel)

        if d.exec() == QDialog.DialogCode.Accepted:
            alg = d.algorithm()
            if isinstance(alg, QgsProcessingAlgorithm):
                self.setAlgorithm(alg)

    def setAlgorithm(self, algorithm: QgsProcessingAlgorithm | None):
        if algorithm != self.algorithm():
            super().setAlgorithm(algorithm)
            self._parameters_panel = self.createParametersPanel(
                self.inPlace(), self.mSpeclib, self.messageBar()
            )
            self.setMainWidget(self._parameters_panel)

            self.updateGui()

    def updateGui(self):
        """
        Updates GUI widgets
        """
        sl = self.speclib()
        if isinstance(sl, QgsVectorLayer):
            n = sl.selectedFeatureCount()
            self.cbSelectedFeaturesOnly.setEnabled(n > 0)
            self.cbSelectedFeaturesOnly.setText(f'Only process {n} selected features')

        self.tbAlgorithmName: QLineEdit

        alg: QgsProcessingAlgorithm = self.algorithm()
        hasAlg = isinstance(alg, QgsProcessingAlgorithm)
        if hasAlg:
            self.tbAlgorithmName.setStyleSheet('')
            css = ''
            # info = f'<b>{alg.displayName()}</b> "{alg.id()}"'
            info = f'{alg.displayName()} "{alg.id()}"'
            tooltip = f'Algorithm Name: {alg.name()}<br>Algorithm ID: {alg.id()}'
        else:
            css = 'color:"red";'
            info = tooltip = self.tbAlgorithmName.placeholderText()
        self.tbAlgorithmName.setStyleSheet(css)
        self.tbAlgorithmName.setText(info)
        self.tbAlgorithmName.setToolTip(tooltip)
        self.setWindowTitle(self.mWidgetName)
