import os
import pathlib
import typing
import re

from PyQt5.QtCore import pyqtSignal, QRegExp, QUrl
from PyQt5.QtGui import QIcon, QRegExpValidator
from PyQt5.QtWidgets import QWidget, QMenu, QDialog, QFormLayout, QComboBox, QStackedWidget, QDialogButtonBox, \
    QLineEdit, QCheckBox

from qgis.core import QgsVectorLayer, QgsFeature, QgsFields, QgsExpressionContextGenerator, QgsProperty, QgsFileUtils, \
    QgsRemappingProxyFeatureSink, QgsRemappingSinkDefinition, QgsCoordinateReferenceSystem, QgsExpressionContextScope

from qgis.gui import QgsFileWidget, QgsFieldMappingWidget, QgsFieldMappingModel
from qgis.core import QgsField, QgsExpression, QgsExpressionContext

from qgis.core import QgsProcessingFeedback
from . import is_spectral_library
from .. import speclibUiPath
from ...utils import loadUi


class SpectralLibraryIOWidget(QWidget):

    def __init__(self, *args, **kwds):
        super(SpectralLibraryIOWidget, self).__init__(*args, **kwds)
        self.mSpeclib: QgsVectorLayer = None
        l = QFormLayout()
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(7)
        self.setLayout(l)

    def spectralLibraryIO(self) -> 'SpectralLibraryIO':
        raise NotImplementedError()

    def formatName(self) -> str:
        return self.spectralLibraryIO().formatName()

    def formatTooltip(self) -> str:
        return self.formatName()

    def setSpeclib(self, speclib: QgsVectorLayer):
        """
        Sets the spectral library to make IO operations with
        :param speclib:
        """
        assert is_spectral_library(speclib)
        self.mSpeclib = speclib

    def speclib(self) -> QgsVectorLayer:
        """
        Returns the spectral library to make IO operations with
        :return: QgsVectorLayer
        """
        return self.mSpeclib


class SpectralLibraryExportWidget(SpectralLibraryIOWidget):
    """
    Abstract Interface of an Widget to export / write a spectral library
    """

    def __init__(self, *args, **kwds):
        super(SpectralLibraryExportWidget, self).__init__(*args, **kwds)
        self.setLayout(QFormLayout())

    def supportsMultipleProfileFields(self) -> bool:
        """
        Returns True if the export format can write multiple profile fields.
        In this case multiple profile fields can be selected for export-
        :return: bool
        """
        return False

    def supportsMultipleSpectralSettings(self) -> bool:
        """
        Returns True if the export format can write profiles with varying spectral settings, e.g.
        different wavelength vectors.
        :return: bool
        """
        return False

    def supportsLayerName(self) -> bool:
        """
        Returns True if the export format can make use of a layer-name
        :return: bool
        """
        return False

    def filter(self) -> str:
        """
        Returns a filter string like "Images (*.png *.xpm *.jpg);;Text files (*.txt);;XML files (*.xml)"
        :return: str
        """
        raise NotImplementedError()

    def exportSettings(self, settings: dict) -> dict:
        """
        Returns a settings dictionary with all settings required to export the library within .writeProfiles
        :param settings:
        :return:
        """
        return settings


class SpectralLibraryImportWidget(SpectralLibraryIOWidget, QgsExpressionContextGenerator):
    sigSourceChanged = pyqtSignal()

    def __init__(self, *args, **kwds):
        super(SpectralLibraryImportWidget, self).__init__(*args, **kwds)
        QgsExpressionContextGenerator.__init__(self)
        self.mSource: str = None

    def setSource(self, source: str):
        """
        Applies changes related to the new source.
        Needs to emit the sigSourceChanged afterwards.
        """
        raise NotImplementedError

    def source(self) -> str:
        """
        Returns the source string
        :return: str
        """
        return self.mSource

    def sourceCrs(self) -> QgsCoordinateReferenceSystem:
        """
        The coordinate reference system in which source coordinates are delivered.
        Defaults to EPSG:4326 lat/lon coordinates
        """
        return QgsCoordinateReferenceSystem('EPSG:4326')

    def filter(self) -> str:
        """
        Returns a filter string like "Images (*.png *.xpm *.jpg);;Text files (*.txt);;XML files (*.xml)"
        with file types that can be imported
        :return: str
        """
        raise NotImplementedError()

    def createExpressionContext(self) -> QgsExpressionContext:
        return QgsExpressionContext()

    def sourceFields(self) -> QgsFields:
        raise NotImplementedError()

    def supportsMultipleFiles(self) -> bool:
        """
        Returns True if profiles can be read from multiple files.
        :return: bool
        """
        return False

    def importSettings(self, settings: dict) -> dict:
        """
        Returns the settings required to import the library
        :param settings:
        :return:
        """
        return settings


class SpectralLibraryIO(object):
    """
    Abstract class interface to define I/O operations for spectral libraries
    """
    SPECTRAL_LIBRARY_IO_REGISTRY: typing.Dict[str, typing.Callable] = dict()

    @staticmethod
    def registerSpectralLibraryIO(speclibIO: typing.Union[
        'SpectralLibraryIO',
        typing.List['SpectralLibraryIO']]):

        if isinstance(speclibIO, list):
            for io in speclibIO:
                SpectralLibraryIO.registerSpectralLibraryIO(io)
            return

        assert isinstance(speclibIO, SpectralLibraryIO)
        name = speclibIO.__class__.__name__
        if name not in SpectralLibraryIO.SPECTRAL_LIBRARY_IO_REGISTRY.keys():
            SpectralLibraryIO.SPECTRAL_LIBRARY_IO_REGISTRY[name] = speclibIO

    @staticmethod
    def spectralLibraryIOs() -> typing.List['SpectralLibraryIO']:
        return list(SpectralLibraryIO.SPECTRAL_LIBRARY_IO_REGISTRY.values())

    @staticmethod
    def spectralLibraryIOInstances(formatName: str) -> 'SpectralLibraryIO':
        if isinstance(formatName, type):
            formatName = formatName.__name__

        return SpectralLibraryIO.SPECTRAL_LIBRARY_IO_REGISTRY[formatName]

    def icon(self) -> QIcon:
        return QIcon()

    def formatName(self) -> str:
        """
        Returns a human-readible name of the Spectral Library Format
        :return: str
        """
        raise NotImplementedError()

    def createImportWidget(self) -> SpectralLibraryImportWidget:
        """
        Returns a widget to specific an import operation
        :return: SpectralLibraryImportWidget
        """
        return None

    def createExportWidget(self) -> SpectralLibraryExportWidget:
        """
        Returns a widget to specify an export opertation, if supported
        :return: SpectralLibraryExportWidget
        """
        return None

    @classmethod
    def importProfiles(cls,
                       path: str,
                       importSettings: dict,
                       feedback: QgsProcessingFeedback) -> typing.List[QgsFeature]:
        """
        Import the profiles based on the source specified in 'path' and further settings in 'importSettings'
        :param path: str
        :param fields: QgsFields
        :param importSettings: dict
        :param feedback:
        :return: list of QgsFeatures
        """
        raise NotImplementedError()

    @classmethod
    def exportProfiles(cls,
                       path: str,
                       exportSettings: dict,
                       profiles: typing.List[QgsFeature],
                       feedback: QgsProcessingFeedback) -> typing.List[str]:
        """
        Writes the files and returns a list of written files paths that can be used to import the profile
        :param path:
        :type path:
        :param exportSettings:
        :param profiles:
        :param feedback:
        :return:
        """
        raise NotImplementedError()

    @staticmethod
    def readProfilesFromUri(
            uri: typing.Union[QUrl, str, pathlib.Path],
            feedback: QgsProcessingFeedback = None) -> typing.List[QgsFeature]:

        if isinstance(uri, QUrl):
            uri = uri.toString(QUrl.PreferLocalFile | QUrl.RemoveQuery)

        elif isinstance(uri, pathlib.Path):
            uri = uri.as_posix()

        if not isinstance(uri, str):
            return []

        global SpectralLibraryIO

        ext = os.path.splitext(uri)[1]

        matched_formats: typing.List[SpectralLibraryImportWidget] = []
        for IO in SpectralLibraryIO.spectralLibraryIOs():
            format = IO.createImportWidget()
            if isinstance(format, SpectralLibraryImportWidget):
                for e in QgsFileUtils.extensionsFromFilter(format.filter()):
                    if ext.endswith(e):
                        matched_formats.append(format)
                        break

        for format in matched_formats:
            format.setSource(uri)
            fields = QgsFields(format.sourceFields())
            if fields.count() == 0:
                continue
            settings = format.importSettings({})
            importedProfiles = IO.importProfiles(uri, settings, feedback=feedback)
            if len(importedProfiles) > 0:
                return importedProfiles

        return []

    @staticmethod
    def readSpeclibFromUri(uri, feedback: QgsProcessingFeedback = None) -> 'SpectralLibrary':
        """
        Tries to open a source uri as SpectralLibrary
        :param uri: str
        :param feedback: QgsProcessingFeedback
        :return: SpectralLibrary
        """
        speclib = None
        if isinstance(uri, QUrl):
            uri = uri.toString(QUrl.PreferLocalFile | QUrl.RemoveQuery)
        elif isinstance(uri, pathlib.Path):
            uri = uri.as_posix()
        assert isinstance(uri, str)
        # 1. Try to open directly as vector layer
        try:
            from .spectrallibrary import SpectralLibrary
            speclib = SpectralLibrary(uri)
        except:
            pass

        # 2. Search for suited IO options
        if not isinstance(speclib, QgsVectorLayer):

            profiles = SpectralLibraryIO.readProfilesFromUri(uri)
            if len(profiles) > 0:
                from .spectrallibrary import SpectralLibrary
                referenceProfile = profiles[0]

                speclib = SpectralLibrary(fields=referenceProfile.fields())
                speclib.startEditing()
                speclib.beginEditCommand('Add profiles')
                speclib.addFeatures(profiles)
                speclib.endEditCommand()
                speclib.commitChanges()

        return speclib


class SpectralLibraryImportDialog(QDialog):

    @staticmethod
    def importProfiles(speclib: QgsVectorLayer,
                       defaultRoot: typing.Union[str, pathlib.Path] = None,
                       parent: QWidget = None):
        assert isinstance(speclib, QgsVectorLayer) and speclib.isValid()

        dialog = SpectralLibraryImportDialog(parent=parent, speclib=speclib, defaultRoot=defaultRoot)

        if dialog.exec_() == QDialog.Accepted:

            source = dialog.source()
            propertyMap = dialog.fieldPropertyMap()
            format = dialog.currentImportWidget()
            if not isinstance(format, SpectralLibraryImportWidget):
                return False
            settings = format.importSettings({})
            io: SpectralLibraryIO = format.spectralLibraryIO()
            speclib: QgsVectorLayer = dialog.speclib()

            feedback = QgsProcessingFeedback()
            profiles = io.importProfiles(source, settings, feedback)
            profiles = list(profiles)

            sinkDefinition = QgsRemappingSinkDefinition()
            sinkDefinition.setDestinationFields(speclib.fields())
            sinkDefinition.setSourceCrs(format.sourceCrs())
            sinkDefinition.setDestinationWkbType(speclib.wkbType())
            sinkDefinition.setFieldMap(propertyMap)

            context = QgsExpressionContext()
            context.setFields(profiles[0].fields())
            context.setFeedback(feedback)

            scope = QgsExpressionContextScope()
            scope.setFields(profiles[0].fields())
            context.appendScope(scope)

            sink = QgsRemappingProxyFeatureSink(sinkDefinition, speclib)
            sink.setExpressionContext(context)
            stopEditing = speclib.startEditing()
            speclib.beginEditCommand('Import profiles')
            success = sink.addFeatures(profiles)
            if not success:
                print(f'Failed to import profiles: {sink.lastError()}')
            speclib.endEditCommand()
            speclib.commitChanges(stopEditing=stopEditing)
            return success
        else:
            return False

    def __init__(self,
                 *args,
                 speclib: QgsVectorLayer = None,
                 defaultRoot: typing.Union[str, pathlib.Path] = None,
                 **kwds):

        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryimportdialog.ui'), self)
        self.setWindowIcon(QIcon(r':/qps/ui/icons/speclib_add.svg'))
        self.cbFormat: QComboBox
        self.fileWidget: QgsFileWidget
        self.fieldMappingWidget: QgsFieldMappingWidget
        self.buttonBox: QDialogButtonBox
        self.cbFormat.currentIndexChanged.connect(self.setImportWidget)

        self.fileWidget.fileChanged.connect(self.onFileChanged)

        if defaultRoot:
            self.fileWidget.setDefaultRoot(pathlib.Path(defaultRoot).as_posix())

        self.mSpeclib: QgsVectorLayer = None

        self.mFIELD_PROPERTY_MAPS: typing.Dict[str, typing.Dict[str, QgsProperty]] = dict()

        first_format = None
        for io in SpectralLibraryIO.spectralLibraryIOs():
            assert isinstance(io, SpectralLibraryIO)
            widget = io.createImportWidget()
            if isinstance(widget, SpectralLibraryImportWidget):
                name = widget.formatName()
                assert isinstance(name, str)
                widget.sigSourceChanged.connect(self.onSourceFieldsChanged)
                self.stackedWidgetFormatOptions.addWidget(widget)
                self.cbFormat.addItem(name, widget)
                self.cbFormat: QComboBox
            if first_format is None:
                first_format = widget

        if isinstance(speclib, QgsVectorLayer):
            self.setSpeclib(speclib)

        if first_format:
            self.setImportWidget(first_format)

    def onFileChanged(self, *args):

        w = self.currentImportWidget()
        if isinstance(w, SpectralLibraryImportWidget):
            w.setSource(self.source())
            self.onSourceFieldsChanged()

    def fieldPropertyMap(self):
        return self.fieldMappingWidget.fieldPropertyMap()

    def findMatchingFormat(self) -> bool:
        source = self.source()
        extension = os.path.splitext(source)[1][1:].lower()
        for format in self.importWidgets():
            filter = format.filter()
            formatExtensions = QgsFileUtils.extensionsFromFilter(filter)
            if extension in formatExtensions:
                self.setImportWidget(format)
                return True
        return False

    def setSource(self, source: typing.Union[str, pathlib.Path]):
        if isinstance(source, pathlib.Path):
            source = source.as_posix()
        self.fileWidget.setFilePath(source)

    def source(self) -> str:
        return self.fileWidget.filePath()

    def onSourceFieldsChanged(self):
        w = self.currentImportWidget()
        if isinstance(w, SpectralLibraryImportWidget):
            oldMap = self.fieldPropertyMap()
            self.fieldMappingWidget.setFieldPropertyMap({})
            self.fieldMappingWidget.setSourceFields(w.sourceFields())
            # self.fieldMappingWidget.registerExpressionContextGenerator(w)
            s = ""

    def setImportWidget(self, import_format: typing.Union[int, str, SpectralLibraryImportWidget]):
        self.cbFormat: QComboBox
        import_widgets = self.importWidgets()
        last_widget = self.currentImportWidget()
        if isinstance(last_widget, SpectralLibraryImportWidget):
            self.mFIELD_PROPERTY_MAPS[last_widget.formatName()] = self.fieldMappingWidget.fieldPropertyMap()

        if isinstance(import_format, SpectralLibraryImportWidget):
            for i, w in enumerate(import_widgets):
                w: SpectralLibraryImportWidget
                if w.formatName() == import_format.formatName():
                    self.cbFormat.setCurrentIndex(i)
                    return

        elif isinstance(import_format, str):
            for i, w in enumerate(import_widgets):
                w: SpectralLibraryImportWidget
                if w.formatName() == import_format:
                    self.cbFormat.setCurrentIndex(i)
                    return

        assert isinstance(import_format, int)
        if import_format != self.cbFormat.currentIndex():
            self.cbFormat.setCurrentIndex(import_format)
            return

        import_widget: SpectralLibraryImportWidget = import_widgets[import_format]

        assert isinstance(import_widget, SpectralLibraryImportWidget)
        assert import_widget in import_widgets

        self.fileWidget.setFilter(import_widget.filter())

        if import_widget.supportsMultipleFiles():
            self.fileWidget.setStorageMode(QgsFileWidget.GetMultipleFiles)
        else:
            self.fileWidget.setStorageMode(QgsFileWidget.GetFile)

        self.stackedWidgetFormatOptions.setCurrentWidget(import_widget)
        self.gbFormatOptions.setVisible(import_widget.findChild(QWidget) is not None)
        import_widget.setSource(self.source())
        self.onSourceFieldsChanged()

    def importWidgets(self) -> typing.List[SpectralLibraryImportWidget]:
        self.stackedWidgetFormatOptions: QStackedWidget
        return [self.stackedWidgetFormatOptions.widget(i)
                for i in range(self.stackedWidgetFormatOptions.count())
                if isinstance(self.stackedWidgetFormatOptions.widget(i), SpectralLibraryImportWidget)]

    def currentImportWidget(self) -> SpectralLibraryImportWidget:
        return self.stackedWidgetFormatOptions.currentWidget()

    def setSpeclib(self, speclib: QgsVectorLayer):
        self.fieldMappingWidget.setDestinationFields(speclib.fields())
        for w in self.importWidgets():
            w.setSpeclib(speclib)
        self.initFieldMapping()
        self.mSpeclib = speclib

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def initFieldMapping(self):
        pass

    def fieldPropertyMap(self):
        return self.fieldMappingWidget.fieldPropertyMap()


class SpectralLibraryExportDialog(QDialog):

    @staticmethod
    def exportProfiles(speclib: QgsVectorLayer, parent: QWidget = None) -> typing.List[str]:

        dialog = SpectralLibraryExportDialog(parent=parent, speclib=speclib)

        if dialog.exec_() == QDialog.Accepted:
            w: SpectralLibraryExportWidget = dialog.currentExportWidget()
            io: SpectralLibraryIO = dialog.exportIO()
            settings = dialog.exportSettings()
            if isinstance(io, SpectralLibraryIO):
                feedback = QgsProcessingFeedback()
                path = dialog.exportPath()
                if dialog.saveSelectedFeaturesOnly():
                    profiles = speclib.getSelectedFeatures()
                else:
                    profiles = speclib.getFeatures()

                return io.exportProfiles(path, settings, profiles, feedback)
        return []

    def __init__(self, *args, speclib: QgsVectorLayer = None, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('spectrallibraryexportdialog.ui'), self)
        self.setWindowIcon(QIcon(':/qps/ui/icons/speclib_save.svg'))

        self.cbFormat: QComboBox
        self.cbSaveSelectedOnly: QCheckBox
        self.fileWidget: QgsFileWidget
        self.tbLayerName: QLineEdit

        self.mLayerNameValidator = QRegExpValidator(QRegExp('[A-Za-z0-9_]+'))
        self.tbLayerName.setValidator(self.mLayerNameValidator)

        self.cbFormat.currentIndexChanged.connect(self.setExportWidget)

        self.mSpeclib: QgsVectorLayer = None
        for io in SpectralLibraryIO.spectralLibraryIOs():
            assert isinstance(io, SpectralLibraryIO)
            widget = io.createExportWidget()
            if isinstance(widget, SpectralLibraryExportWidget):
                name = widget.formatName()
                self.cbFormat: QComboBox
                self.stackedWidgetFormatOptions.addWidget(widget)
                self.cbFormat.addItem(name)

        if isinstance(speclib, QgsVectorLayer):
            self.setSpeclib(speclib)

        self.fileWidget.fileChanged.connect(self.validateInputs)
        self.validateInputs()

    def validateInputs(self):
        path = self.exportPath().strip()
        settings = self.exportSettings()

        is_valid = path != '' and isinstance(settings, dict)
        self.buttonBox.button(QDialogButtonBox.Ok).setEnabled(is_valid)

    def exportIO(self) -> SpectralLibraryIO:
        return self.currentExportWidget().spectralLibraryIO()

    def setExportPath(self, path: str):
        assert isinstance(path, str)
        self.fileWidget.setFilePath(path)

    def exportPath(self) -> str:
        return self.fileWidget.filePath()

    def exportSettings(self) -> dict:
        settings = dict()
        w = self.currentExportWidget()
        if not isinstance(w, SpectralLibraryExportWidget):
            return None

        if w.supportsLayerName():
            settings['layer_name'] = self.tbLayerName.text()

        return w.exportSettings(settings)

    def exportWidgets(self) -> typing.List[SpectralLibraryExportWidget]:
        self.stackedWidgetFormatOptions: QStackedWidget
        return [self.stackedWidgetFormatOptions.widget(i)
                for i in range(self.stackedWidgetFormatOptions.count())
                if isinstance(self.stackedWidgetFormatOptions.widget(i), SpectralLibraryExportWidget)]

    def saveSelectedFeaturesOnly(self) -> bool:
        return self.cbSaveSelectedOnly.isChecked()

    def currentExportWidget(self) -> SpectralLibraryExportWidget:
        return self.stackedWidgetFormatOptions.currentWidget()

    def setExportWidget(self, widget: typing.Union[int, str, SpectralLibraryExportWidget]):
        last_widget = self.currentExportWidget()
        if isinstance(last_widget, SpectralLibraryExportWidget):
            s = ""

        export_widgets = self.exportWidgets()
        export_widget: SpectralLibraryExportWidget = None
        if isinstance(widget, SpectralLibraryExportWidget):
            export_widget = widget
        elif isinstance(widget, int):
            export_widget = export_widgets[widget]
        elif isinstance(widget, str):
            for w in export_widgets:
                if w.formatName() == widget:
                    export_widget = w
                    break
        assert isinstance(export_widget, SpectralLibraryExportWidget)

        self.fileWidget.setFilter(export_widget.filter())
        self.stackedWidgetFormatOptions.setCurrentWidget(export_widget)
        b = export_widget.supportsLayerName()
        self.tbLayerName.setEnabled(b)
        self.labelLayerName.setEnabled(b)

        self.gbFormatOptions.setVisible(export_widget.findChild(QWidget) is not None)

    def setSpeclib(self, speclib: QgsVectorLayer):

        if isinstance(self.mSpeclib, QgsVectorLayer):
            self.mSpeclib.selectionChanged.disconnect(self.onSelectionChanged)

        self.mSpeclib = speclib
        self.mSpeclib.selectionChanged.connect(self.onSelectionChanged)
        # if self.tbLayerName.text() == '':
        #     self.tbLayerName.setText(re.sub(r'[^0-9a-zA-Z_]', '_', speclib.name()))
        for w in self.exportWidgets():
            w.setSpeclib(speclib)

        self.onSelectionChanged()

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib

    def onSelectionChanged(self):
        speclib = self.speclib()
        if isinstance(speclib, QgsVectorLayer):
            self.cbSaveSelectedOnly.setEnabled(speclib.selectedFeatureCount() > 0)


def initSpectralLibraryIOs():
    from ..io.geopackage import GeoPackageSpectralLibraryIO
    from ..io.envi import EnviSpectralLibraryIO

    speclibIOs = [
        GeoPackageSpectralLibraryIO(),
        EnviSpectralLibraryIO()
    ]

    for speclibIO in speclibIOs:
        SpectralLibraryIO.registerSpectralLibraryIO(speclibIO)
