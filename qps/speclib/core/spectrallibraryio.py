import os
import pathlib
import sys
import typing
import warnings

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtCore import pyqtSignal, QRegExp, QUrl
from qgis.PyQt.QtGui import QIcon, QRegExpValidator
from qgis.PyQt.QtWidgets import QWidget, QDialog, QFormLayout, \
    QComboBox, QStackedWidget, QDialogButtonBox, \
    QLineEdit, QCheckBox, QToolButton, QAction
from qgis.core import QgsProject, QgsVectorLayer, QgsFeature, QgsFields, \
    QgsExpressionContextGenerator, QgsProperty, QgsFileUtils, \
    QgsRemappingProxyFeatureSink, QgsRemappingSinkDefinition, \
    QgsCoordinateReferenceSystem, QgsExpressionContextScope, QgsProcessingFeedback, QgsField, \
    QgsExpressionContext, QgsFeatureIterator, QgsWkbTypes
from qgis.gui import QgsFileWidget, QgsFieldMappingWidget
from . import profile_field_list, profile_field_names
from .spectralprofile import groupBySpectralProperties
from .. import speclibUiPath, speclibSettings
from ...layerproperties import CopyAttributesDialog
from ...utils import loadUi

IMPORT_SETTINGS_KEY_REQUIRED_SOURCE_FIELDS = 'required_source_fields'


class SpectralLibraryIOWidget(QWidget):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        self.mSpeclib: QgsVectorLayer = None
        fl = QFormLayout()
        fl.setContentsMargins(0, 0, 0, 0)
        fl.setSpacing(7)
        self.setLayout(fl)

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
        # assert is_spectral_library(speclib)
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
        super().__init__(*args, **kwds)
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
        context = QgsExpressionContext()
        fields = self.sourceFields()
        if isinstance(fields, QgsFields):
            context.setFields(QgsFields(fields))
        return context

    def sourceFields(self) -> QgsFields:
        raise NotImplementedError()

    def supportsMultipleFiles(self) -> bool:
        """
        Returns True if profiles can be read from multiple files.
                False if profiles can be read from single files only and
                None if no files are read at all, e.g. because input is handled in the options widget
        :return: bool | None
        """
        return False

    def importSettings(self, settings: dict) -> dict:
        """
        Returns the settings dictionary that is used as import for SpectralLibraryIO.importProfiles(...).
        If called from SpectralLibraryImportDialog, settings will be pre-initialized with:
        * 'required_source_fields' = set of field names (str) that are expected to be in each returned QgsFeature.

        :param settings: dict
        :return: dict
        """
        return settings


class SpectralLibraryIO(QObject):
    """
    Abstract class interface to define I/O operations for spectral libraries
    """
    SPECTRAL_LIBRARY_IO_REGISTRY: typing.Dict[str, typing.Callable] = dict()

    IMPSET_FIELDS = 'fields'
    IMPSET_REQUIRED_FIELDS = 'required_fields'

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    @classmethod
    def copyEditorWidgetSetup(cls, path: typing.Union[str, pathlib.Path], fields: QgsFields):
        path = pathlib.Path(path).as_posix()
        lyr = QgsVectorLayer(path)

        if lyr.isValid():
            for name in fields.names():
                i = lyr.fields().lookupField(name)
                if i >= 0:
                    lyr.setEditorWidgetSetup(i, fields.field(name).editorWidgetSetup())
            msg, success = lyr.saveDefaultStyle()
            if not success:
                print(msg, file=sys.stderr)

    @classmethod
    def extractFilePath(cls, uri: typing.Union[str, pathlib.Path, QUrl]) -> pathlib.Path:

        if isinstance(uri, QUrl):
            uri = uri.toString(QUrl.PreferLocalFile | QUrl.RemoveQuery)
        return pathlib.Path(uri)

    @classmethod
    def extractWriterInfos(cls,
                           input: typing.Union[
                               QgsFeature,
                               QgsVectorLayer,
                               QgsFeatureIterator,
                               typing.List[QgsFeature]],
                           settings: dict = dict()) -> typing.Tuple[
        typing.List[QgsFeature],
        QgsFields,
        QgsCoordinateReferenceSystem,
        QgsWkbTypes.Type
    ]:

        crs = None
        wkbType = None
        fields = None
        if isinstance(input, QgsFeature):
            profiles = [input]
        elif isinstance(input, QgsVectorLayer):
            crs = input.crs()
            wkbType = input.wkbType()
            profiles = list(input.getFeatures())
        elif isinstance(input, QgsFeatureIterator):
            profiles = list(input)
        elif isinstance(input, list):
            profiles = input
        else:
            raise NotImplementedError()

        if crs is None:
            if 'crs' in settings.keys():
                crs = QgsCoordinateReferenceSystem(settings['crs'])
            else:
                crs = QgsCoordinateReferenceSystem()
        if wkbType is None:
            if len(profiles) > 0 and profiles[0].geometry():
                wkbType = profiles[0].geometry().wkbType()
            else:
                wkbType = settings.get('wkbType', QgsWkbTypes.NoGeometry)
        if len(profiles) > 0:
            fields = profiles[0].fields()

        return profiles, fields, crs, wkbType

    @staticmethod
    def registerSpectralLibraryIO(speclibIO: typing.Union['SpectralLibraryIO', typing.List['SpectralLibraryIO']]):

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
        Returns a human-readable name of the Spectral Library Format
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
                       importSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> typing.List[QgsFeature]:
        """
        Import the profiles based on the source specified by 'path' and further settings in 'importSettings'.
        Returns QgsFeatures
        Well-implemented SpectralLibraryIOs check if IMPORT_SETTINGS_KEY_REQUIRED_SOURCE_FIELDS exists in
        importSettings and optimize import speed by returning only fields in
        the set in importSettings[IMPORT_SETTINGS_KEY_REQUIRED_SOURCE_FIELDS]
        :param path: str
        :param importSettings: dict, optional
        :param feedback: QgsProcessingFeedback, optional
        :return: list of QgsFeatures
        """
        raise NotImplementedError()

    @classmethod
    def exportProfiles(cls,
                       path: typing.Union[str, pathlib.Path, QUrl],
                       profiles: typing.List[QgsFeature],
                       exportSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> typing.List[str]:
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
            feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> typing.List[QgsFeature]:

        if isinstance(uri, QUrl):
            uri = uri.toString(QUrl.PreferLocalFile | QUrl.RemoveQuery)

        elif isinstance(uri, pathlib.Path):
            uri = uri.as_posix()

        if not isinstance(uri, str):
            return []

        # global SpectralLibraryIO

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
            format: SpectralLibraryImportWidget
            IO: SpectralLibraryIO = format.spectralLibraryIO()
            format.setSource(uri)
            fields = QgsFields(format.sourceFields())
            if fields.count() == 0:
                continue
            settings = dict(fields=QgsFields(format.sourceFields()))
            settings = format.importSettings(settings)
            importedProfiles = IO.importProfiles(uri, settings, feedback=feedback)
            if len(importedProfiles) > 0:
                return importedProfiles

        return []

    @classmethod
    def writeToSource(cls,
                      profiles: typing.Union[
                               QgsFeature,
                               QgsVectorLayer,
                               QgsFeatureIterator,
                               typing.List[QgsFeature]],
                      uri: typing.Union[str, pathlib.Path, QUrl],
                      settings: dict = dict(),
                      feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> typing.List[str]:

        profiles, fields, crs, wkbType = cls.extractWriterInfos(profiles, settings)
        if len(profiles) == 0:
            return []
        pFields = profile_field_list(fields)

        if isinstance(uri, QUrl):
            uri = uri.toString(QUrl.PreferLocalFile | QUrl.RemoveQuery)
        uri = cls.extractFilePath(uri)
        uri_bn, uri_ext = os.path.splitext(uri.name)

        if not isinstance(settings, dict):
            settings = dict()

        matched_formats: typing.List[SpectralLibraryImportWidget] = []

        if len(SpectralLibraryIO.spectralLibraryIOs()) == 0:
            warnings.warn('No SpectralLibraryIO registered. Register SpectralLibraryIOs with '
                          'SpectralLibraryIO.registerSpectralLibraryIO(<IO>) first.')
            return []

        for IO in SpectralLibraryIO.spectralLibraryIOs():
            format = IO.createExportWidget()
            if isinstance(format, SpectralLibraryExportWidget):
                for e in QgsFileUtils.extensionsFromFilter(format.filter()):
                    if uri_ext.endswith(e):
                        matched_formats.append(format)
                        break

        if len(matched_formats) == 0:
            warnings.warn(f'No SpectralLibraryIO export format found for file type "*{uri_ext}"')
            return []

        for format in matched_formats:
            format: SpectralLibraryExportWidget
            IO: SpectralLibraryIO = format.spectralLibraryIO()

            # consider that not every format allows to
            # 1. write profiles from different fields
            # 2. profiles of different wavelength

            GROUPS: typing.Dict[str, typing.List[typing.List[QgsFeature]]] = dict()

            needs_field_separation = len(pFields) > 1 and not format.supportsMultipleProfileFields()
            needs_setting_groups = not format.supportsMultipleSpectralSettings()

            if not (needs_setting_groups or needs_field_separation):
                GROUPS[''] = [profiles]
            else:
                all_profiles = profiles

                if needs_setting_groups:
                    for field in pFields:
                        for setting, profiles in groupBySpectralProperties(all_profiles, profile_field=field).items():
                            grp_profiles = GROUPS.get(field.name(), [])
                            grp_profiles.append(profiles)
                            GROUPS[field.name()] = grp_profiles
                else:
                    # needs_field_separation:
                    for field in pFields:
                        GROUPS[field.name()] = [all_profiles]

            # iterate over profile fields
            files_created = []
            # iterate over profile groups

            nFields = 0

            for fieldName, profilesGroups in GROUPS.items():
                nFields += 1

                # use a separated file name for each field
                if len(pFields) > 1 and fieldName != '':
                    uri_field = f'{uri_bn}.{fieldName}'
                else:
                    uri_field = uri_bn

                for iGrp, profiles in enumerate(profilesGroups):

                    # use a separated file name for each profile group
                    if iGrp == 0:
                        path_dst = uri.parent / f'{uri_field}{uri_ext}'
                    else:
                        path_dst = uri.parent / f'{uri_field}.{iGrp}{uri_ext}'

                    dst_settings = dict()
                    if fieldName != '':
                        dst_settings['profile_field'] = fieldName
                    dst_settings.update(settings)
                    create_files = IO.exportProfiles(path_dst, profiles, exportSettings=dst_settings, feedback=feedback)
                    files_created.extend(create_files)
            return files_created
        return []

    @staticmethod
    def readSpeclibFromUri(uri, feedback: QgsProcessingFeedback = None) -> QgsVectorLayer:
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
            speclib = QgsVectorLayer(uri, os.path.basename(uri))
            if not speclib.isValid():
                speclib = None
        except Exception:
            s = ""
            pass

        # 2. Search for suited IO options
        if not isinstance(speclib, QgsVectorLayer):

            profiles = SpectralLibraryIO.readProfilesFromUri(uri)
            if len(profiles) > 0:
                from .spectrallibrary import SpectralLibraryUtils

                speclib = SpectralLibraryUtils.createSpectralLibrary(profile_fields=[])
                speclib.startEditing()
                SpectralLibraryUtils.addProfiles(speclib, profiles, addMissingFields=True)
                speclib.commitChanges()

        return speclib


class SpectralLibraryImportFeatureSink(QgsRemappingProxyFeatureSink):

    def __init__(self, sinkDefinition, speclib: QgsVectorLayer):
        super().__init__(sinkDefinition, speclib)
        self.mSpeclib = speclib
        self.mProfileFieldNames = profile_field_names(self.mSpeclib)
        self.mContext: QgsExpressionContext = None

    def setExpressionContext(self, context: QgsExpressionContext) -> None:
        super().setExpressionContext(context)
        self.mContext = context

    def remapFeature(self, feature: QgsFeature) -> typing.List[QgsFeature]:
        features = super().remapFeature(feature)

        return features


class ProfileProperty(QgsProperty, QObject):

    def __init__(self, targetField: QgsField, *args, **kwds):
        QObject.__init__(self)
        self.mField = targetField

    def value(self, *args, **kwds) -> typing.Tuple[typing.Any, bool]:
        v = super().value(*args, **kwds)

        s = ""
        return v

    def __repr__(self):
        return f'ProfileProperty {id(self)}'


class ContextGenerator(QgsExpressionContextGenerator):

    def __init__(self, dialog):
        super().__init__()

        self.mDialog: SpectralLibraryImportDialog = dialog

    def createExpressionContext(self) -> QgsExpressionContext:
        context = self.mDialog.formatExpressionContext()
        if not isinstance(context, QgsExpressionContext):
            context = QgsExpressionContext()
        return context


class SpectralLibraryImportDialog(QDialog, QgsExpressionContextGenerator):

    @staticmethod
    def importProfiles(speclib: QgsVectorLayer,
                       defaultRoot: typing.Union[str, pathlib.Path] = None,
                       parent: QWidget = None):
        assert isinstance(speclib, QgsVectorLayer) and speclib.isValid()

        dialog = SpectralLibraryImportDialog(parent=parent, speclib=speclib, defaultRoot=defaultRoot)

        if dialog.exec_() == QDialog.Accepted:

            source = dialog.source()

            format = dialog.currentImportWidget()

            if not isinstance(format, SpectralLibraryImportWidget):
                return False

            expressionContext = format.createExpressionContext()
            requiredSourceFields = set()
            propertyMap = dialog.fieldPropertyMap()

            for k, prop in propertyMap.items():
                prop: QgsProperty
                ref_fields = prop.referencedFields(expressionContext)
                requiredSourceFields.update(ref_fields)

            settings = dict()
            settings[IMPORT_SETTINGS_KEY_REQUIRED_SOURCE_FIELDS] = requiredSourceFields

            settings = format.importSettings(settings)
            io: SpectralLibraryIO = format.spectralLibraryIO()
            speclib: QgsVectorLayer = dialog.speclib()

            feedback = QgsProcessingFeedback()
            profiles = io.importProfiles(source, settings, feedback)
            profiles = list(profiles)
            if len(profiles) == 0:
                return False

            sinkDefinition = QgsRemappingSinkDefinition()
            sinkDefinition.setDestinationFields(speclib.fields())
            sinkDefinition.setSourceCrs(format.sourceCrs())
            sinkDefinition.setDestinationCrs(speclib.crs())
            sinkDefinition.setDestinationWkbType(speclib.wkbType())
            sinkDefinition.setFieldMap(propertyMap)

            context = QgsExpressionContext()
            context.setFields(profiles[0].fields())
            context.setFeedback(feedback)

            scope = QgsExpressionContextScope()
            scope.setFields(profiles[0].fields())
            context.appendScope(scope)

            # sink = QgsRemappingProxyFeatureSink(sinkDefinition, speclib)
            sink = SpectralLibraryImportFeatureSink(sinkDefinition, speclib)
            sink.setExpressionContext(context)
            sink.setTransformContext(QgsProject.instance().transformContext())

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

        self.btnAddMissingSourceFields: QToolButton
        self.actionAddMissingSourceFields: QAction
        self.actionAddMissingSourceFields.triggered.connect(self.onAddMissingSourceFields)
        self.btnAddMissingSourceFields.setDefaultAction(self.actionAddMissingSourceFields)

        self.cbFormat.currentIndexChanged.connect(self.setImportWidget)

        self.fileWidget.fileChanged.connect(self.onFileChanged)
        self.mContextGenerator = ContextGenerator(self)
        self.fieldMappingWidget.registerExpressionContextGenerator(self.mContextGenerator)

        if defaultRoot:
            r = pathlib.Path(defaultRoot)
            if r.is_dir():
                self.fileWidget.setDefaultRoot(r.as_posix())
            if r.is_file():
                self.fileWidget.setDefaultRoot(r.parent.as_posix())
                self.fileWidget.setFilePath(r.as_posix())

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

        settings = speclibSettings()
        default_root = settings.value('SpectralLibraryImportDialog/defaultRoot', None)
        if default_root:
            self.fileWidget.setDefaultRoot(default_root)
        first_format = settings.value('SpectralLibraryImportDialog/format', first_format)

        if first_format:
            self.setImportWidget(first_format)

    def exec_(self) -> int:
        r = super().exec_()
        if r == QDialog.Accepted:
            settings = speclibSettings()

            # save file path directory for next dialog start
            fw: QgsFileWidget = self.fileWidget
            filePath = fw.filePath()
            if fw.isMultiFiles(filePath):
                filePath = fw.splitFilePaths(filePath)[0]
            filePath = pathlib.Path(filePath)
            if filePath.is_file():
                filePath = filePath.parent
            settings.setValue('SpectralLibraryImportDialog/defaultRoot', filePath.as_posix())

            # save selected import format for next dialog start
            format = self.currentImportWidget()
            if isinstance(format, SpectralLibraryImportWidget):
                settings.setValue('SpectralLibraryImportDialog/format', format.formatName())

        return r

    def formatExpressionContext(self) -> QgsExpressionContext:
        format = self.currentImportWidget()
        if isinstance(format, SpectralLibraryImportWidget):
            return format.createExpressionContext()
        else:
            return None

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
            fields = w.sourceFields()
            self.actionAddMissingSourceFields.setEnabled(fields.count() > 0)
        else:
            self.actionAddMissingSourceFields.setEnabled(False)

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
            return

        assert isinstance(import_format, int), f'import_format={import_format} (type {import_format})'
        if import_format != self.cbFormat.currentIndex():
            self.cbFormat.setCurrentIndex(import_format)
            return

        import_widget: SpectralLibraryImportWidget = import_widgets[import_format]

        assert isinstance(import_widget, SpectralLibraryImportWidget)
        assert import_widget in import_widgets

        self.fileWidget.setFilter(import_widget.filter())

        support = import_widget.supportsMultipleFiles()
        if support is None:
            self.fileWidget.setVisible(False)
            self.labelFilename.setVisible(False)
        else:
            self.fileWidget.setVisible(True)
            self.labelFilename.setVisible(True)
            if support:
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

    def onAddMissingSourceFields(self):
        sourceFields = None
        w = self.currentImportWidget()
        if isinstance(w, SpectralLibraryImportWidget):
            sourceFields = w.sourceFields()
        speclib = self.speclib()

        if isinstance(sourceFields, QgsFields) and sourceFields.count() > 0 and isinstance(speclib, QgsVectorLayer):
            if CopyAttributesDialog.copyLayerFields(speclib, sourceFields):
                self.fieldMappingWidget.setDestinationFields(speclib.fields())

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

                return io.exportProfiles(path, profiles, settings, feedback)
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
    from ..io.geojson import GeoJsonSpectralLibraryIO
    from ..io.envi import EnviSpectralLibraryIO
    from ..io.asd import ASDSpectralLibraryIO
    from ..io.rastersources import RasterLayerSpectralLibraryIO

    speclibIOs = [
        GeoPackageSpectralLibraryIO(),
        GeoJsonSpectralLibraryIO(),
        EnviSpectralLibraryIO(),
        ASDSpectralLibraryIO(),
        RasterLayerSpectralLibraryIO()
    ]

    for speclibIO in speclibIOs:
        SpectralLibraryIO.registerSpectralLibraryIO(speclibIO)
