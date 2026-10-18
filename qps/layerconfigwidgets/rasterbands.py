"""
***************************************************************************
    layerconfigwidget/rasterbands.py
        - A QgsMapLayerConfigWidget to select and change bands of QgsRasterRenderers
    -----------------------------------------------------------------------
    begin                : 2020-02-24
    copyright            : (C) 2020 Benjamin Jakimow
    email                : benjamin.jakimow@geo.hu-berlin.de

***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <https://www.gnu.org/licenses/>.
***************************************************************************
"""
from pathlib import Path
from typing import List, Union, Optional, Dict, Tuple

from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QSlider, QStackedWidget, QWidget
from qgis.PyQt.QtWidgets import QToolButton, QComboBox
from qgis.core import Qgis, QgsMapLayer, QgsMultiBandColorRenderer, QgsPalettedRasterRenderer, QgsRasterLayer, \
    QgsRasterRenderer, QgsSingleBandColorDataRenderer, QgsSingleBandGrayRenderer, QgsSingleBandPseudoColorRenderer
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidget, QgsMapLayerConfigWidgetFactory, QgsRasterBandComboBox

from ..layerconfigwidgets.core import QpsMapLayerConfigWidget
from ..qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ..unitmodel import UnitLookup
from ..utils import loadUi, printCaller, rendererXML, SignalBlocker, \
    has_spyndex, band_descriptions, band_index, band_values


class RasterBandComboBox(QgsRasterBandComboBox):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mWL = self.mWLU = self.mFWHM = None

    def setLayer(self, layer):
        """
        Re-Implements void QgsRasterBandComboBox::setLayer( QgsMapLayer *layer ) with own band-name logic

        :param layer:
        :type layer: qgis.core.QgsRasterLayer
        :return:
        :rtype: None
        """
        super().setLayer(layer)

        if not (isinstance(layer, QgsRasterLayer) and layer.isValid()):
            return

        prop = QgsRasterLayerSpectralProperties.fromRasterLayer(layer)
        WL = prop.wavelengths()
        WLU = prop.wavelengthUnits()
        FWHM = prop.fwhm()

        offset = 1 if self.isShowingNotSetOption() else 0
        for b in range(layer.bandCount()):
            idx = b + offset
            bandName = self.itemText(idx)
            tooltip = bandName
            if WLU[b] and WLU[b] not in bandName:
                bandName += ' [{} {}]'.format(WL[b], WLU[b])
                tooltip += ' {} {}'.format(WL[b], WLU[b])
                if FWHM[b]:
                    tooltip += ' {}'.format(FWHM[b])

            self.setItemText(idx, bandName)
            self.setItemData(idx, tooltip, Qt.ItemDataRole.ToolTipRole)


def standard_band_combinations() -> Dict[str, Tuple[str, str, str]]:
    # rgb visualizations adopted from:
    # https://github.com/sandroklippel/qgis_gee_data_catalog/blob/master/datasets.py

    mapping = {
        'Natural color': ('R', 'G', 'B'),
        'False color': ('R', 'N', 'G'),
        'Color infrared': ('N', 'R', 'G'),
        'Shortwave infrared 1': ('S2', 'N', 'R'),
        'Shortwave infrared 2': ('S2', 'RE4', 'R'),
        'Shortwave infrared 3': ('S2', 'RE4', 'B'),
        'Agriculture 1': ('S1', 'N', 'B'),
        'Agriculture 2': ('S1', 'RE4', 'B'),
        'Atmospheric penetration / Soil': ('S2', 'S1', 'RE4'),
        'Geology': ('S2', 'S1', 'B'),
        'Bathymetric': ('R', 'G', 'A'),
        'False color urban': ('S2', 'S1', 'R'),
        'Healthy vegetation': ('N', 'S1', 'B'),
        'Vegetation analysis 1': ('N', 'S1', 'R'),
        'Vegetation analysis 2': ('S1', 'N', 'R'),
        'Forestry / Recent harvest areas': ('S2', 'N', 'G')
    }

    return mapping


RENDER_TYPE2NAME = {
    'multibandcolor': 'Multiband color',
    'paletted': 'Paletted/Unique values',
    'contour': 'Contours',
    'hillshade': 'Hillshade',
    'singlebandpseudocolor': 'Singleband pseudocolor',
    'singlebandgray': 'Singleband gray',
}


class RasterBandConfigWidget(QpsMapLayerConfigWidget):

    def __init__(self, layer: QgsRasterLayer, canvas: QgsMapCanvas, parent: QWidget = None):

        super().__init__(layer, canvas, parent=parent)
        pathUi = Path(__file__).parents[1] / 'ui' / 'rasterbandconfigwidget.ui'
        loadUi(pathUi, self)

        self.mCanvas = canvas
        self.mLayer = layer
        self.mRendererXMLString: Optional[str] = None
        self.mLayer.rendererChanged.connect(self.syncToLayer)
        if not isinstance(self.cbS, QgsRasterBandComboBox):
            raise AssertionError('self.cbS is not a QgsRasterBandComboBox')

        self.cbS.setLayer(self.mLayer)
        self.cbR.setLayer(self.mLayer)
        self.cbG.setLayer(self.mLayer)
        self.cbB.setLayer(self.mLayer)

        self.cbS.bandChanged.connect(self.onBandWidgetChanged)
        self.cbR.bandChanged.connect(self.onBandWidgetChanged)
        self.cbG.bandChanged.connect(self.onBandWidgetChanged)
        self.cbB.bandChanged.connect(self.onBandWidgetChanged)

        self.cbBandCombinations: QComboBox
        self.cbBandCombinations.currentIndexChanged.connect(self.onBandCombinationChanged)

        self.mChangedBufferMS = 500
        self.mChangedTimer = QTimer()
        self.mChangedTimer.timeout.connect(self.onWidgetChanged)

        self.sliderS: QSlider
        self.sliderS.setRange(1, self.mLayer.bandCount())
        self.sliderR.setRange(1, self.mLayer.bandCount())
        self.sliderG.setRange(1, self.mLayer.bandCount())
        self.sliderB.setRange(1, self.mLayer.bandCount())

        self.mBandWL = []
        self.mBandNames = []
        self.mRGBShortcuts = []

        self.mBandButtons_R = []
        self.mBandButtons_G = []
        self.mBandButtons_B = []
        self.mBandButtons_S = []

        self.CB2LABEL = {
            self.cbR: self.labelWLR,
            self.cbG: self.labelWLG,
            self.cbB: self.labelWLB,
            self.cbS: self.labelWLS,
        }
        self.createBandShortcuts(self.mLayer)

        self.syncToLayer()

        self.setPanelTitle('Band Selection')

    def createBandShortcuts(self, layer: QgsRasterLayer):

        # clear band combo boxes
        for (layout, button_list) in [
            (self.layoutR, self.mBandButtons_R),
            (self.layoutG, self.mBandButtons_G),
            (self.layoutB, self.mBandButtons_B),
            (self.layoutS, self.mBandButtons_S),
        ]:
            button_list.clear()
            while layout.count() > 0:
                layout.takeAt(0)

        self.cbBandCombinations.clear()

        if not has_spyndex:
            return

        sp = QgsRasterLayerSpectralProperties.fromRasterLayer(layer)
        mWL = sp.wavelengths()
        mWLUnit = sp.wavelengthUnits()[0]

        if UnitLookup.isMetricUnit(mWLUnit):
            # if possible, convert to nanometers
            mWLUnit = UnitLookup.baseUnit(mWLUnit)
            try:
                mWL = UnitLookup.convertLengthUnit(mWL, mWLUnit, 'nm')
                mWLUnit = 'nm'
            except Exception:
                mWL = None
                mWLUnit = None

        self.mBandWL.clear()
        self.mBandWL.extend(mWL)
        self.mBandWLUnit = mWLUnit

        from spyndex.axioms import Band

        def createButton(band: Band, cb: QgsRasterBandComboBox) -> QToolButton:
            btn = QToolButton()
            btn.setText(band.short_name)
            tt = f'{band.long_name}<br>{band.min_wavelength} nm - {band.max_wavelength} nm'
            btn.setToolTip(tt)
            b_idx = band_index(band.short_name, mWL, mWLUnit)
            btn.clicked.connect(lambda *args, _cb=cb, _idx=b_idx: _cb.setCurrentIndex(_idx))
            return btn

        b_descriptions = band_descriptions(mWL)
        for b in b_descriptions:
            for (layout, button_list, cb) in [
                (self.layoutR, self.mBandButtons_R, self.cbR),
                (self.layoutG, self.mBandButtons_G, self.cbG),
                (self.layoutB, self.mBandButtons_B, self.cbB),
                (self.layoutS, self.mBandButtons_S, self.cbS),
            ]:
                btn = createButton(b, cb)
                # btn.setAutoRaise(True)
                button_list.append(btn)
                layout.addWidget(btn)

        for layout in [self.layoutR, self.layoutG, self.layoutB, self.layoutS]:
            layout.addStretch()

        # fill band combinations
        combinations = []
        available_bands = [b.short_name for b in b_descriptions]
        for name, rgb in standard_band_combinations().items():
            covers_all_bands = True
            for c in rgb:
                if c not in available_bands:
                    covers_all_bands = False
                    break
            if covers_all_bands:
                combinations.append((name, rgb))

        for (name, rgb) in combinations:
            self.cbBandCombinations.addItem(name, userData=rgb)

    def onBandWidgetChanged(self, *args):
        self.mChangedTimer.start(self.mChangedBufferMS)
        sender = self.sender()
        if isinstance(sender, QgsRasterBandComboBox):
            self.updateWavelengthLabel(sender)

    def updateWavelengthLabel(self, cb: QgsRasterBandComboBox):

        if cb in self.CB2LABEL:
            label = self.CB2LABEL[cb]
            i = cb.currentIndex()
            if 0 <= i < len(self.mBandWL):
                wl = self.mBandWL[i]
                label.setText(f'{wl} {self.mBandWLUnit}')

    def onBandCombinationChanged(self):

        rgb = self.cbBandCombinations.currentData(Qt.ItemDataRole.UserRole)

        rgb_indices = band_values(
            rgb, self.mBandWL, [0 for w in self.mBandWL],
            wavelength_unit=self.mBandWLUnit,
            return_band_indices=True
        )
        rgb_indices = {k: v for k, v in rgb_indices.items() if isinstance(v, int)}
        if len(rgb_indices) == 3:
            self.cbR.setCurrentIndex(rgb_indices[rgb[0]])
            self.cbG.setCurrentIndex(rgb_indices[rgb[1]])
            self.cbB.setCurrentIndex(rgb_indices[rgb[2]])

    def onWidgetChanged(self, *args):
        printCaller(prefix=id(self))
        self.mChangedTimer.stop()
        # create a new renderer

        if self.dockMode():
            self.widgetChanged.emit()
        else:
            # QgsRasterLayerProperties dialog. will call apply() manually
            pass

    def icon(self) -> QIcon:
        return QIcon(':/qps/ui/icons/rasterband_select.svg')

    def syncToLayer(self, *args):
        super().syncToLayer(*args)
        renderer = self.mLayer.renderer().clone()
        self.setRenderer(renderer)

    def renderer(self) -> QgsRasterRenderer:
        printCaller(prefix=id(self))
        oldRenderer = self.mLayer.renderer()
        newRenderer: QgsRasterRenderer = None

        if isinstance(oldRenderer, QgsSingleBandGrayRenderer):
            newRenderer: QgsSingleBandGrayRenderer = oldRenderer.clone()
            newRenderer.setGrayBand(self.cbS.currentBand())

        elif isinstance(oldRenderer, QgsSingleBandPseudoColorRenderer):
            newRenderer: QgsSingleBandGrayRenderer = oldRenderer.clone()
            newRenderer.setBand(self.cbS.currentBand())

        elif isinstance(newRenderer, QgsPalettedRasterRenderer):
            newRenderer = QgsPalettedRasterRenderer(oldRenderer.input(), self.cbS.currentBand(),
                                                    oldRenderer.classes())
            # setBand ?
        elif isinstance(oldRenderer, QgsSingleBandColorDataRenderer):
            newRenderer = QgsSingleBandColorDataRenderer(oldRenderer.input(), self.cbS.currentBand())

        elif isinstance(oldRenderer, QgsMultiBandColorRenderer):
            newRenderer: QgsMultiBandColorRenderer = oldRenderer.clone()
            newRenderer.setRedBand(self.cbR.currentBand())
            newRenderer.setGreenBand(self.cbG.currentBand())
            newRenderer.setBlueBand(self.cbB.currentBand())

        else:
            newRenderer = oldRenderer.clone()

        newRenderer.setInput(oldRenderer.input())
        self.mRendererXMLString = rendererXML(newRenderer).toString()

        self.updateWavelengthLabels()

        return newRenderer

    def updateWavelengthLabels(self):
        for cb in self.CB2LABEL.keys():
            self.updateWavelengthLabel(cb)

    def rendererName(self, renderer: Union[str, QgsRasterRenderer]) -> str:
        if isinstance(renderer, QgsRasterRenderer):
            renderer = renderer.type()
        else:
            renderer = str(renderer)
        return RENDER_TYPE2NAME.get(renderer, renderer)

    def blockableWidgets(self) -> List[QWidget]:

        return [self.cbS,
                self.cbR,
                self.cbG,
                self.cbB,
                self.sliderS,
                self.sliderR,
                self.sliderG,
                self.sliderB
                ]

    def setRenderer(self, renderer: QgsRasterRenderer):
        if not isinstance(renderer, QgsRasterRenderer):
            return

        if rendererXML(renderer).toString() != self.mRendererXMLString:
            # printCaller(prefix=id(self))

            w: QStackedWidget = self.renderBandWidget

            self.labelRenderType.setText(self.rendererName(renderer))
            bands = renderer.usesBands()
            with SignalBlocker(*self.blockableWidgets()):

                if len(bands) == 1:
                    w.setCurrentWidget(self.pageSingleBand)
                    self.cbS.setBand(bands[0])
                    self.sliderS.setValue(bands[0])
                elif len(bands) == 3:
                    w.setCurrentWidget(self.pageMultiBand)
                    self.cbR.setBand(bands[0])
                    self.cbG.setBand(bands[1])
                    self.cbB.setBand(bands[2])
                    self.sliderR.setValue(bands[0])
                    self.sliderG.setValue(bands[1])
                    self.sliderB.setValue(bands[2])

                else:
                    w.setCurrentWidget(self.pageUnknown)
            self.updateWavelengthLabels()

    def shouldTriggerLayerRepaint(self) -> bool:
        return True

    def apply(self):
        # printCaller(suffix='apply called')
        newRenderer = self.renderer()
        if rendererXML(self.mLayer.renderer()).toString() == self.mRendererXMLString:
            # no need to replace the renderer
            return

        if isinstance(newRenderer, QgsRasterRenderer) and isinstance(self.mLayer, QgsRasterLayer):
            newRenderer.setInput(self.mLayer.dataProvider())
            printCaller(prefix=id(self))
            with SignalBlocker(self.mLayer) as _:
                # update on renderer will be triggered by other widgets that react on styleChanged signal
                self.mLayer.setRenderer(newRenderer)
            self.mLayer.styleManager().currentStyleChanged.emit('')
            # self.mLayer.emitStyleChanged()
            # self.widgetChanged.emit()


class RasterBandConfigWidgetBlocker(object):

    def __init__(self, w: RasterBandConfigWidget):
        self.w: RasterBandConfigWidget = w


class RasterBandConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self):
        super().__init__(
            'Raster Band',
            QIcon(':/qps/ui/icons/rasterband_select.svg')
        )

    def supportsLayer(self, layer):
        return isinstance(layer, QgsRasterLayer) and layer.isValid()

    def layerPropertiesPagePositionHint(self) -> str:
        return 'mOptsPage_Transparency'

    def supportLayerPropertiesDialog(self):
        # see https://bitbucket.org/hu-geomatics/enmap-box/issues/1392/singleband-pseudoclor-min-max-reset
        return True
        # requires QGIS 1e86672a
        return Qgis.versionInt() >= 32300

    def supportsStyleDock(self):
        return True

    def icon(self) -> QIcon:
        return QIcon(':/qps/ui/icons/rasterband_select.svg')

    def title(self) -> str:
        return 'Raster Band'

    def createWidget(
        self,
        layer: QgsMapLayer,
        canvas: QgsMapCanvas,
        dockWidget: bool = True,
        parent: QWidget | None = None
    ) -> QgsMapLayerConfigWidget:
        w = RasterBandConfigWidget(layer, canvas, parent=parent)
        # if isinstance(parent, QgsRasterLayerProperties):
        #    w.widgetChanged.connect(parent.syncToLayer)
        w.setWindowTitle(self.title())
        w.setWindowIcon(self.icon())
        return w
