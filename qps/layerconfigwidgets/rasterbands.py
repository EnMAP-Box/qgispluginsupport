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
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import pathlib
import typing

import numpy as np
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QPushButton
from qgis.PyQt.QtWidgets import QSlider, QWidget, QStackedWidget, QLabel
from qgis.core import QgsRasterLayer, QgsMapLayer, \
    QgsRasterRenderer, \
    QgsSingleBandGrayRenderer, \
    QgsSingleBandColorDataRenderer, \
    QgsSingleBandPseudoColorRenderer, \
    QgsMultiBandColorRenderer, \
    QgsPalettedRasterRenderer
from qgis.gui import QgsMapCanvas, QgsMapLayerConfigWidget, QgsMapLayerConfigWidgetFactory, QgsRasterBandComboBox
from qgis.gui import QgsRasterLayerProperties
from ..layerconfigwidgets.core import QpsMapLayerConfigWidget
from ..simplewidgets import FlowLayout
from ..utils import loadUi, parseWavelength, UnitLookup, parseFWHM, LUT_WAVELENGTH, WAVELENGTH_DESCRIPTION, \
    SignalBlocker, printCaller, rendererXML


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

        WL, WLU = parseWavelength(layer)
        FWHM = parseFWHM(layer)

        offset = 1 if self.isShowingNotSetOption() else 0
        for b in range(layer.bandCount()):
            idx = b + offset
            bandName = self.itemText(idx)
            tooltip = bandName
            if WLU and WLU not in bandName:
                bandName += ' [{} {}]'.format(WL[b], WLU)
                tooltip += ' {} {}'.format(WL[b], WLU)
                if isinstance(FWHM, np.ndarray):
                    tooltip += ' {}'.format(FWHM[b])

            self.setItemText(idx, bandName)
            self.setItemData(idx, tooltip, Qt.ToolTipRole)


class BandCombination(object):
    """
    Describes a band combination
    """

    def __init__(self,
                 band_keys: typing.Union[str, tuple],
                 name: str = None,
                 tooltip: str = None,
                 icon: QIcon = None):

        if isinstance(band_keys, str):
            band_keys = (band_keys,)
        assert isinstance(band_keys, tuple)
        assert len(band_keys) > 0
        for b in band_keys:
            assert b in LUT_WAVELENGTH.keys(), f'Unknown wavelength key: {b}'

        self.mBand_keys = band_keys
        self.mName = name
        self.mTooltip = tooltip
        self.mIcon = QIcon(icon)

    def bandKeys(self) -> tuple:
        return self.mBand_keys

    def icon(self) -> QIcon:
        return self.mIcon

    def name(self) -> str:
        if self.mName is None:
            return '-'.join(self.mBand_keys)
        else:
            return self.mName

    def tooltip(self, wl_nm) -> str:
        tt = self.mTooltip if self.mTooltip else ''
        if len(self.mBand_keys) == 1:
            return 'Selects the band closest to\n{}'.format(WAVELENGTH_DESCRIPTION[self.mBand_keys[0]])
        else:
            tt += '\nSelects the bands closest to:'
            for i, b in enumerate(self.mBand_keys):
                tt += '\n' + WAVELENGTH_DESCRIPTION[b]
        return tt.strip()

    def nBands(self) -> int:
        return len(self.mBand_keys)


BAND_COMBINATIONS: typing.List[BandCombination] = []
# single-band renders
BAND_COMBINATIONS += [BandCombination(b) for b in LUT_WAVELENGTH.keys()]
# 3-band renderers (Order: R-G-B color channel)
BAND_COMBINATIONS += [
    BandCombination(('R', 'G', 'B'), name='True Color'),
    BandCombination(('NIR', 'R', 'G'), name='Colored IR'),
    BandCombination(('SWIR', 'NIR', 'R')),
    BandCombination(('NIR', 'SWIR', 'R'))
]

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

        super(RasterBandConfigWidget, self).__init__(layer, canvas, parent=parent)
        pathUi = pathlib.Path(__file__).parents[1] / 'ui' / 'rasterbandconfigwidget.ui'
        loadUi(pathUi, self)

        assert isinstance(layer, QgsRasterLayer)
        self.mCanvas = canvas
        self.mLayer = layer
        self.mRendererXMLString: str = None
        self.mLayer.rendererChanged.connect(self.syncToLayer)
        assert isinstance(self.cbSingleBand, QgsRasterBandComboBox)

        self.cbSingleBand.setLayer(self.mLayer)
        self.cbMultiBandRed.setLayer(self.mLayer)
        self.cbMultiBandGreen.setLayer(self.mLayer)
        self.cbMultiBandBlue.setLayer(self.mLayer)

        self.cbSingleBand.bandChanged.connect(self.onBandWidgetChanged)
        self.cbMultiBandRed.bandChanged.connect(self.onBandWidgetChanged)
        self.cbMultiBandGreen.bandChanged.connect(self.onBandWidgetChanged)
        self.cbMultiBandBlue.bandChanged.connect(self.onBandWidgetChanged)

        self.mChangedBufferMS = 500
        self.mChangedTimer = QTimer()
        self.mChangedTimer.timeout.connect(self.onWidgetChanged)

        assert isinstance(self.sliderSingleBand, QSlider)
        self.sliderSingleBand.setRange(1, self.mLayer.bandCount())
        self.sliderMultiBandRed.setRange(1, self.mLayer.bandCount())
        self.sliderMultiBandGreen.setRange(1, self.mLayer.bandCount())
        self.sliderMultiBandBlue.setRange(1, self.mLayer.bandCount())

        mWL, mWLUnit = parseWavelength(self.mLayer)
        if isinstance(mWL, list):
            mWL = np.asarray(mWL)

        if UnitLookup.isMetricUnit(mWLUnit):
            mWLUnit = UnitLookup.baseUnit(mWLUnit)
            # convert internally to nanometers
            if mWLUnit != 'nm':
                try:
                    mWL = UnitLookup.convertMetricUnit(mWL, mWLUnit, 'nm')
                    mWLUnit = 'nm'
                except Exception:
                    mWL = None
                    mWLUnit = None

        self.mWL = mWL
        self.mWLUnit = mWLUnit

        hasWL = UnitLookup.isMetricUnit(self.mWLUnit)
        self.gbMultiBandWavelength.setEnabled(hasWL)
        self.gbSingleBandWavelength.setEnabled(hasWL)

        def createButton(bandCombi: BandCombination) -> QPushButton:
            btn = QPushButton()
            # btn.setAutoRaise(False)
            btn.setText(bandCombi.name())
            btn.setIcon(bandCombi.icon())
            btn.setToolTip(bandCombi.tooltip(self.mWL))
            btn.clicked.connect(lambda *args, b=bandCombi: self.setWL(b.bandKeys()))
            return btn

        lSingle = FlowLayout()
        lMulti = FlowLayout()

        for bc in BAND_COMBINATIONS:
            if bc.nBands() == 1:
                lSingle.addWidget(createButton(bc))

            if bc.nBands() == 3:
                lMulti.addWidget(createButton(bc))

        self.gbSingleBandWavelength.setLayout(lSingle)
        assert self.gbSingleBandWavelength.layout() == lSingle
        self.gbMultiBandWavelength.setLayout(lMulti)
        lSingle.setContentsMargins(0, 0, 0, 0)
        lSingle.setSpacing(0)
        lSingle.setContentsMargins(0, 0, 0, 0)
        lSingle.setSpacing(0)

        self.mLytMulti = lMulti
        self.mLytSingle = lSingle

        self.syncToLayer()

        self.setPanelTitle('Band Selection')

    def onBandWidgetChanged(self, *args):
        self.mChangedTimer.start(self.mChangedBufferMS)

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
            newRenderer.setGrayBand(self.cbSingleBand.currentBand())

        elif isinstance(oldRenderer, QgsSingleBandPseudoColorRenderer):
            newRenderer: QgsSingleBandGrayRenderer = oldRenderer.clone()
            newRenderer.setBand(self.cbSingleBand.currentBand())

        elif isinstance(newRenderer, QgsPalettedRasterRenderer):
            newRenderer = QgsPalettedRasterRenderer(oldRenderer.input(), self.cbSingleBand.currentBand(),
                                                    oldRenderer.classes())
            s = ""  # setBand ?
        elif isinstance(oldRenderer, QgsSingleBandColorDataRenderer):
            newRenderer = QgsSingleBandColorDataRenderer(oldRenderer.input(), self.cbSingleBand.currentBand())

        elif isinstance(oldRenderer, QgsMultiBandColorRenderer):
            newRenderer: QgsMultiBandColorRenderer = oldRenderer.clone()
            newRenderer.setRedBand(self.cbMultiBandRed.currentBand())
            newRenderer.setGreenBand(self.cbMultiBandGreen.currentBand())
            newRenderer.setBlueBand(self.cbMultiBandBlue.currentBand())

        else:
            newRenderer = oldRenderer.clone()

        newRenderer.setInput(oldRenderer.input())
        self.mRendererXMLString = rendererXML(newRenderer).toString()
        return newRenderer

    def rendererName(self, renderer: typing.Union[str, QgsRasterRenderer]) -> str:
        if isinstance(renderer, QgsRasterRenderer):
            renderer = renderer.type()
        assert isinstance(renderer, str)
        return RENDER_TYPE2NAME.get(renderer, renderer)

    def blockableWidgets(self) -> typing.List[QWidget]:

        return [self.cbSingleBand,
                self.cbMultiBandRed,
                self.cbMultiBandGreen,
                self.cbMultiBandBlue,
                self.sliderSingleBand,
                self.sliderMultiBandRed,
                self.sliderMultiBandGreen,
                self.sliderMultiBandBlue
                ]

    def setRenderer(self, renderer: QgsRasterRenderer):
        if not isinstance(renderer, QgsRasterRenderer):
            return

        if rendererXML(renderer).toString() != self.mRendererXMLString:
            printCaller(prefix=id(self))

            w: QStackedWidget = self.renderBandWidget
            assert isinstance(self.labelRenderType, QLabel)
            assert isinstance(w, QStackedWidget)

            self.labelRenderType.setText(self.rendererName(renderer))
            bands = renderer.usesBands()
            with SignalBlocker(*self.blockableWidgets()):

                if len(bands) == 1:
                    w.setCurrentWidget(self.pageSingleBand)
                    self.cbSingleBand.setBand(bands[0])
                    self.sliderSingleBand.setValue(bands[0])
                elif len(bands) == 3:
                    w.setCurrentWidget(self.pageMultiBand)
                    self.cbMultiBandRed.setBand(bands[0])
                    self.cbMultiBandGreen.setBand(bands[1])
                    self.cbMultiBandBlue.setBand(bands[2])
                    self.sliderMultiBandRed.setValue(bands[0])
                    self.sliderMultiBandGreen.setValue(bands[1])
                    self.sliderMultiBandBlue.setValue(bands[2])

                else:
                    w.setCurrentWidget(self.pageUnknown)

    def shouldTriggerLayerRepaint(self) -> bool:
        return True

    def apply(self):
        printCaller(suffix='apply called')
        newRenderer = self.renderer()
        if rendererXML(self.mLayer.renderer()).toString() == self.mRendererXMLString:
            # no need to replace the renderer
            return

        if isinstance(newRenderer, QgsRasterRenderer) and isinstance(self.mLayer, QgsRasterLayer):
            newRenderer.setInput(self.mLayer.dataProvider())
            printCaller(prefix=id(self))
            with SignalBlocker(self.mLayer) as blocker:
                # update on renderer will be triggered by other widgets that react on styleChanged signal
                self.mLayer.setRenderer(newRenderer)
            self.mLayer.styleManager().currentStyleChanged.emit('')
            # self.mLayer.emitStyleChanged()
            # self.widgetChanged.emit()

    def wlBand(self, wlKey: str) -> int:
        """
        Returns the band number for a wavelength
        :param wlKey:
        :type wlKey:
        :return:
        :rtype:
        """
        from ..utils import LUT_WAVELENGTH
        if isinstance(self.mWL, np.ndarray):
            targetWL = float(LUT_WAVELENGTH[wlKey])
            return int(np.argmin(np.abs(self.mWL - targetWL))) + 1
        else:
            return None

    def setWL(self, wlRegions: tuple):
        renderer = self.renderer().clone()
        with SignalBlocker(*self.blockableWidgets()) as blocker:
            if isinstance(renderer, (QgsSingleBandGrayRenderer, QgsSingleBandPseudoColorRenderer,
                                     QgsSingleBandColorDataRenderer)):
                band = self.wlBand(wlRegions[0])
                self.cbSingleBand.setBand(band)
                self.sliderSingleBand.setValue(band)

            elif isinstance(renderer, QgsMultiBandColorRenderer):
                bR = self.wlBand(wlRegions[0])
                bG = self.wlBand(wlRegions[1])
                bB = self.wlBand(wlRegions[2])

                self.cbMultiBandRed.setBand(bR)
                self.cbMultiBandGreen.setBand(bG)
                self.cbMultiBandBlue.setBand(bB)

                self.sliderMultiBandRed.setValue(bR)
                self.sliderMultiBandGreen.setValue(bG)
                self.sliderMultiBandBlue.setValue(bB)

        self.onBandWidgetChanged()


class RasterBandConfigWidgetBlocker(object):

    def __init__(self, w: RasterBandConfigWidget):
        assert isinstance(w, RasterBandConfigWidget)
        self.w = w


class RasterBandConfigWidgetFactory(QgsMapLayerConfigWidgetFactory):

    def __init__(self):
        super(RasterBandConfigWidgetFactory, self).__init__('Raster Band',
                                                            QIcon(':/qps/ui/icons/rasterband_select.svg'))
        s = ""

    def supportsLayer(self, layer):
        if isinstance(layer, QgsRasterLayer):
            return True

        return False

    def layerPropertiesPagePositionHint(self) -> str:
        return 'mOptsPage_Transparency'

    def supportLayerPropertiesDialog(self):
        return True

    def supportsStyleDock(self):
        return True

    def icon(self) -> QIcon:
        return QIcon(':/qps/ui/icons/rasterband_select.svg')

    def title(self) -> str:
        return 'Raster Band'

    def createWidget(self, layer: QgsMapLayer, canvas: QgsMapCanvas, dockWidget: bool = True,
                     parent=None) -> QgsMapLayerConfigWidget:
        w = RasterBandConfigWidget(layer, canvas, parent=parent)
        # if isinstance(parent, QgsRasterLayerProperties):
        #    w.widgetChanged.connect(parent.syncToLayer)
        w.setWindowTitle(self.title())
        w.setWindowIcon(self.icon())
        return w
