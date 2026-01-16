from qgis.PyQt.QtGui import QPalette, QPen

from .spectrallibraryplotitems import SpectralProfilePlotItem, SpectralProfilePlotDataItem
from ...plotstyling.plotstyling import PlotStyle
from ...pyqtgraph.pyqtgraph import PlotWidget


class SpectralProfilePlotWidget(PlotWidget):
    """A widget to plot a single spectral profile"""

    def __init__(self, *args, profile: dict = None, **kwds):

        plotItem = SpectralProfilePlotItem()

        super().__init__(*args, plotItem=plotItem, **kwds)

        self.mPDI = SpectralProfilePlotDataItem()
        self.addItem(self.mPDI)
        self.mPlotStyle = PlotStyle()
        fg = self.palette().color(QPalette.ColorRole.WindowText)
        bg = self.palette().color(QPalette.ColorRole.Window)
        ax_pen = self.plotItem.axes['bottom']['item'].pen()
        ax_pen.setColor(fg)
        self.plotItem.axes['bottom']['item'].setPen(ax_pen)
        self.plotItem.axes['left']['item'].setPen(ax_pen)
        self.setBackground(None)
        self.mPlotStyle.setMarkerColor(fg)
        self.mPlotStyle.setLinePen(QPen(fg))
        self.mPlotStyle.setLineWidth(0)
        if profile:
            self.setProfile(profile)

    def setPlotStyle(self, style: PlotStyle):
        self.mPlotStyle = style
        if self.mPDI:
            self.mPDI.setPlotStyle(style)

    def setProfile(self, data: dict):
        s = ""

        self.mPDI.setProfileData(data, self.mPlotStyle)
