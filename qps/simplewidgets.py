import typing
from PyQt5.QtCore import QObject, QRect, QSize, QPoint
from PyQt5.QtWidgets import QSizePolicy

from qgis.PyQt.QtCore import pyqtSignal, Qt

from qgis.PyQt.QtWidgets import QWidget, QAbstractSpinBox, QSpinBox, QDoubleSpinBox, \
    QHBoxLayout, QVBoxLayout, QSlider, QLayout, QLayoutItem, QStyle


class FlowLayout(QLayout):
    """
    A FlowLayout, as descrbied in  https://doc.qt.io/qt-5/qtwidgets-layouts-flowlayout-example.html
    """

    def __init__(self, parent: QWidget = None, margin: int = -1, hSpacing: int = -1, vSpacing: int = -1):

        super().__init__(parent)

        self.m_hSpace = hSpacing
        self.m_vSpace = vSpacing
        self.m_itemlist: typing.List[QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)

    def setSpacing(self, space: int) -> None:
        self.m_vSpace = space
        self.m_vSpace = space

    def addItem(self, item: QLayoutItem):
        assert isinstance(item, QLayoutItem)

        self.m_itemlist.append(item)

    def horizontalSpacing(self) -> int:
        if self.m_hSpace >= 0:
            return self.m_hSpace
        else:
            return self.smartSpacing(QStyle.PM_LayoutHorizontalSpacing)

    def verticalSpacing(self) -> int:
        if self.m_vSpace >= 0:
            return self.m_vSpace
        else:
            return self.smartSpacing(QStyle.PM_LayoutVerticalSpacing)

    def count(self) -> int:
        return len(self.m_itemlist)

    def itemAt(self, index: int) -> QLayoutItem:
        if 0 <= index < len(self.m_itemlist):
            return self.m_itemlist[index]
        return None

    def takeAt(self, index: int) -> QLayoutItem:
        if 0 <= index < len(self.m_itemlist):
            return self.m_itemlist.pop(index)
        return None

    def expandingDirections(self) -> Qt.Orientations:
        return Qt.Horizontal | Qt.Vertical

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self.doLayout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QRect):
        super().setGeometry(rect)
        self.doLayout(rect, False)

    def sizeHint(self) -> QSize:
        return self.minimumSize()

    def minimumSize(self) -> QSize:
        size = QSize()

        for item in self.m_itemlist:
            size.expandedTo(item.minimumSize())

        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def doLayout(self, rect: QRect, testOnly: bool) -> int:
        left, top, right, bottom = self.getContentsMargins()
        effectiveRect: QRect = rect.adjusted(+left, +top, -right, -bottom)
        x: int = effectiveRect.x()
        y: int = effectiveRect.y()
        lineHeight = 0

        for item in self.m_itemlist:
            wid = item.widget()
            spaceX = self.horizontalSpacing()
            if spaceX == -1:
                spaceX = wid.style().layoutSpacing(QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Horizontal)
            spaceY = self.verticalSpacing()
            if spaceY == -1:
                spaceY = wid.style().layoutSpacing(QSizePolicy.PushButton, QSizePolicy.PushButton, Qt.Vertical)

            nextX = x + item.sizeHint().width() + spaceX
            if (nextX - spaceX > effectiveRect.right()) and lineHeight > 0:
                x = effectiveRect.x()
                y = y + lineHeight + spaceY
                nextX = x + item.sizeHint().width() + spaceX
                lineHeight = 0

            if not testOnly:
                item.setGeometry(QRect(QPoint(x, y), item.sizeHint()))

            x = nextX
            lineHeight = max(lineHeight, item.sizeHint().height())
        return y + lineHeight - rect.y() + bottom

    def smartSpacing(self, pm: QStyle.PixelMetric):
        parent = self.parent()
        if not isinstance(parent, QObject):
            return -1

        if isinstance(parent, QWidget):
            return parent.style().pixelMetric(pm, None, parent)
        elif isinstance(parent, QLayout):
            return parent.spacing()


class SliderSpinBox(QWidget):
    sigValueChanged = pyqtSignal(int)

    def __init__(self, *args,
                 spinbox: QAbstractSpinBox = None,
                 spinbox_position: Qt.Alignment = Qt.AlignLeft,
                 **kwds):

        if not isinstance(spinbox, QAbstractSpinBox):
            spinbox = QSpinBox()
        assert isinstance(spinbox, QAbstractSpinBox)
        assert isinstance(spinbox_position, Qt.AlignmentFlag)

        super().__init__(*args, **kwds)

        self.spinbox: QAbstractSpinBox = spinbox
        self.slider: QSlider = QSlider(Qt.Horizontal)
        self.slider.valueChanged.connect(self.onSliderValueChanged)
        self.spinbox.valueChanged.connect(self.onSpinboxValueChanged)

        if spinbox_position in [Qt.AlignLeft, Qt.AlignRight]:
            l = QHBoxLayout()
        elif spinbox_position in [Qt.AlignTop, Qt.AlignBottom]:
            l = QVBoxLayout()
        else:
            raise NotImplementedError()

        if spinbox_position in [Qt.AlignLeft, Qt.AlignTop]:
            l.addWidget(self.spinbox)
            l.addWidget(self.slider)
        else:
            l.addWidget(self.slider)
            l.addWidget(self.spinbox)

        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(2)

        self.setLayout(l)

    def onSliderValueChanged(self, value):
        v = self.slider2spinboxvalue(value)
        self.spinbox.setValue(v)

    def onSpinboxValueChanged(self, value):
        v = self.spinbox2slidervalue(value)
        if v != self.slider.value():
            self.slider.setValue(v)

        self.sigValueChanged.emit(value)

    def setSingleStep(self, value):
        self.spinbox.setSingleStep(value)
        self.slider.setSingleStep(value)
        self.slider.setPageStep(value * 10)

    def singleStep(self):
        return self.spinbox.singleStep()

    def setMinimum(self, value):
        self.spinbox.setMinimum(value)
        self.slider.setMinimum(self.spinbox2slidervalue(value))

    def spinbox2slidervalue(self, value):
        return value

    def slider2spinboxvalue(self, value):
        return value

    def setMaximum(self, value):
        self.spinbox.setMaximum(value)
        self.slider.setMaximum(self.spinbox2slidervalue(value))

    def maximum(self) -> int:
        return self.spinbox.maximum()

    def minimum(self) -> int:
        return self.spinbox.minimum()

    def setValue(self, value: float):
        self.spinbox.setValue(value)

    def value(self) -> float:
        return self.spinbox.value()

    def setRange(self, vmin, vmax):
        vmin = min(vmin, vmax)
        vmax = max(vmin, vmax)
        assert vmin <= vmax

        self.setMinimum(vmin)
        self.setMaximum(vmax)


class DoubleSliderSpinBox(SliderSpinBox):
    sigValueChanged = pyqtSignal(float)

    def __init__(self, *args, **kwds):
        spinbox = QDoubleSpinBox()
        super().__init__(*args, spinbox=spinbox, **kwds)

        self.spinbox: QDoubleSpinBox
        assert isinstance(self.spinbox, QDoubleSpinBox)
        self.setDecimals(2)
        self.setMinimum(0)
        self.setMaximum(1)
        self.setSingleStep(0.1)

    def spinbox2slidervalue(self, value: float) -> int:
        v = int(round(10 ** self.decimals() * value))
        return v

    def slider2spinboxvalue(self, value: int) -> float:
        v = value / (10 ** self.decimals())
        return v

    def setDecimals(self, value: int):
        self.spinbox.setDecimals(value)
        self.setSingleStep(self.spinbox.singleStep())

    def decimals(self) -> int:
        return self.spinbox.decimals()

    def setSingleStep(self, value):
        self.spinbox.setSingleStep(value)
        m = int(10 ** self.decimals() * value)
        self.slider.setSingleStep(m)
        self.slider.setPageStep(m * 10)
