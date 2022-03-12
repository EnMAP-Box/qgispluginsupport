# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/core.py

    Spectral Profiles and Libraries for QGIS.
    ---------------------
    Date                 : Juli 2017
    Copyright            : (C) 2020 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
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

import datetime
# see http://python-future.org/str_literals.html for str issue discussion
import json
import os
import pathlib
import pickle
import re
import sys
import warnings
import weakref
from typing import List, Union, Tuple, Dict, Optional, Generator

import numpy as np
from osgeo import gdal, ogr, osr, gdal_array

from qgis.PyQt.QtCore import Qt, QVariant, QUrl, QMimeData, \
    QFileInfo
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QWidget, QFileDialog, QDialog
from qgis.core import QgsApplication, QgsFeatureIterator, \
    QgsFeature, QgsVectorLayer, QgsRasterLayer, \
    QgsAttributeTableConfig, QgsField, QgsFields, QgsCoordinateReferenceSystem, QgsActionManager, QgsFeatureRequest, \
    QgsGeometry, QgsPoint, QgsDefaultValue, QgsMapLayerProxyModel, \
    QgsEditorWidgetSetup, QgsAction, QgsProcessingFeedback, \
    QgsRemappingProxyFeatureSink, QgsRemappingSinkDefinition, \
    QgsExpressionContext, QgsCoordinateTransformContext, QgsProperty, QgsExpressionContextScope
from qgis.gui import \
    QgsGui
from . import field_index
from . import profile_field_list, first_profile_field_index, create_profile_field, \
    is_spectral_library
from .spectralprofile import SpectralProfile, SpectralProfileBlock, \
    SpectralSetting, groupBySpectralProperties, prepareProfileValueDict, encodeProfileValueDict, ProfileEncoding
from .. import FIELD_VALUES
from .. import speclibSettings, EDITOR_WIDGET_REGISTRY_KEY, SPECLIB_EPSG_CODE
from ...plotstyling.plotstyling import PlotStyle
from ...utils import SelectMapLayersDialog, gdalDataset, \
    createQgsField, px2geocoordinates, qgsVectorLayer, qgsRasterLayer, findMapLayer, \
    fid2pixelindices, parseWavelength, parseBadBandList, optimize_block_size, \
    qgsField, qgsFieldAttributes2List, qgsFields2str, str2QgsFields

# get to now how we can import this module
MODULE_IMPORT_PATH = None
XMLNODE_PROFILE_RENDERER = 'spectralProfileRenderer'

for name, module in sys.modules.items():
    if hasattr(module, '__file__') and module.__file__ == __file__:
        MODULE_IMPORT_PATH = name
        break

MIMEDATA_SPECLIB = 'application/hub-spectrallibrary'
MIMEDATA_SPECLIB_LINK = 'application/hub-spectrallibrary-link'
MIMEDATA_XQT_WINDOWS_CSV = 'application/x-qt-windows-mime;value="Csv"'

# see https://doc.qt.io/qt-5/qwinmime.html
MIMEDATA_TEXT = 'text/plain'
MIMEDATA_URL = 'text/uri-list'

SPECLIB_CLIPBOARD = weakref.WeakValueDictionary()
DEFAULT_NAME = 'SpectralLibrary'

OGR_EXTENSION2DRIVER = dict()
OGR_EXTENSION2DRIVER[''] = []  # list all drivers without specific extension

FILTERS = 'Geopackage (*.gpkg);;ENVI Spectral Library (*.sli *.esl);;CSV Table (*.csv);;GeoJSON (*.geojson)'

PICKLE_PROTOCOL = pickle.HIGHEST_PROTOCOL
# CURRENT_SPECTRUM_STYLE = PlotStyle()
# CURRENT_SPECTRUM_STYLE.markerSymbol = None
# CURRENT_SPECTRUM_STYLE.linePen.setStyle(Qt.SolidLine)
# CURRENT_SPECTRUM_STYLE.linePen.setColor(Qt.green)


# DEFAULT_SPECTRUM_STYLE = PlotStyle()
# DEFAULT_SPECTRUM_STYLE.markerSymbol = None
# DEFAULT_SPECTRUM_STYLE.linePen.setStyle(Qt.SolidLine)
# DEFAULT_SPECTRUM_STYLE.linePen.setColor(Qt.white)


VSI_DIR = r'/vsimem/speclibs/'
X_UNITS = ['Index', 'Micrometers', 'Nanometers', 'Millimeters', 'Centimeters', 'Meters', 'Wavenumber', 'Angstroms',
           'GHz', 'MHz', '']
Y_UNITS = ['DN', 'Reflectance', 'Radiance', '']

for i in range(ogr.GetDriverCount()):
    drv = ogr.GetDriver(i)
    extensions = drv.GetMetadataItem(gdal.DMD_EXTENSIONS)
    if isinstance(extensions, str):
        extensions = extensions.split(',')
        for ext in extensions:
            if ext not in OGR_EXTENSION2DRIVER.keys():
                OGR_EXTENSION2DRIVER[ext] = []
            OGR_EXTENSION2DRIVER[ext].append(drv.GetName())
    else:
        OGR_EXTENSION2DRIVER[''].append(drv.GetName())
OGR_EXTENSION2DRIVER[None] = OGR_EXTENSION2DRIVER['']

DEBUG = os.environ.get('DEBUG', 'false').lower() in ['true', '1']


def read_profiles(*args, **kwds):
    warnings.warn('Use SpectralProfileUtils.profiles() instead')
    return SpectralLibraryUtils.readProfiles(*args, **kwds)


def containsSpeclib(mimeData: QMimeData) -> bool:
    """
    Short, fast test if a QMimeData object might contain a SpectralLibrary.
    Might be wrong, but should be fast enough to be used in drag and drop operations
    :param mimeData:
    :type mimeData:
    :return:
    :rtype:
    """
    if mimeData.hasUrls():
        return True

    for f in [MIMEDATA_SPECLIB, MIMEDATA_SPECLIB_LINK]:
        if f in mimeData.formats():
            return True

    return False


def vsiSpeclibs() -> list:
    """
    Returns the URIs pointing on VSIMEM in memory speclibs
    :return: [list-of-str]
    """
    warnings.warn(
        DeprecationWarning('SpectralLibrary are not stored in VSI Mem anymore and use the QGIS Memory driver'))
    visSpeclibs = []

    entry = gdal.ReadDir(VSI_DIR)
    if entry is not None:
        for bn in entry:
            p = pathlib.PurePosixPath(VSI_DIR) / bn
            p = p.as_posix()
            stats = gdal.VSIStatL(p)
            if isinstance(stats, gdal.StatBuf) and not stats.IsDirectory():
                visSpeclibs.append(p)
    return visSpeclibs


def runRemoveFeatureActionRoutine(layerID, id: int):
    """
    Is applied to a set of layer features to change the plotStyle JSON string stored in styleField
    :param layerID: QgsVectorLayer or vector id str
    :param id: feature id of feature for which the QgsAction was called
    """

    layer = findMapLayer(layerID)

    if isinstance(layer, QgsVectorLayer):
        selectedIDs = layer.selectedFeatureIds()
        if id in selectedIDs:
            ids = selectedIDs
        else:
            ids = [id]
        if len(ids) == 0:
            return

        wasEditable = layer.isEditable()
        if not wasEditable:
            if not layer.startEditing():
                raise Exception('Layer "{}" can not be edited'.format(layer.name()))
        layer.beginEditCommand('Remove {} features'.format(len(ids)))
        layer.deleteFeatures(ids)
        layer.endEditCommand()
        if not layer.commitChanges():
            errors = layer.commitErrors()
            raise Exception('Unable to save {} to layer {}'.format('\n'.join(errors), layer.name()))

        if wasEditable:
            layer.startEditing()

    else:
        raise Exception('unable to find layer "{}"'.format(layerID))


RX_SUPPORTED_DROP_FORMATS = re.compile(r'.*\.(gpkg|geojson|asd|\d+)$', re.I)


def createRemoveFeatureAction():
    """
    Creates a QgsAction to remove selected QgsFeatures from a QgsVectorLayer
    :return: QgsAction
    """

    iconPath = ':/images/themes/default/mActionDeleteSelected.svg'
    pythonCode = """
from {modulePath} import runRemoveFeatureActionRoutine
layerId = '[% @layer_id %]'
#layerId = [% "layer" %]
runRemoveFeatureActionRoutine(layerId, [% $id %])
""".format(modulePath=MODULE_IMPORT_PATH)

    return QgsAction(QgsAction.GenericPython, 'Remove Spectrum', pythonCode, iconPath, True,
                     notificationMessage='msgRemoveSpectra',
                     actionScopes={'Feature'})


# Lookup table for ENVI IDL DataTypes to GDAL Data Types
LUT_IDL2GDAL = {1: gdal.GDT_Byte,
                12: gdal.GDT_UInt16,
                2: gdal.GDT_Int16,
                13: gdal.GDT_UInt32,
                3: gdal.GDT_Int32,
                4: gdal.GDT_Float32,
                5: gdal.GDT_Float64,
                # :gdal.GDT_CInt16,
                # 8:gdal.GDT_CInt32,
                6: gdal.GDT_CFloat32,
                9: gdal.GDT_CFloat64}


def defaultCurvePlotStyle() -> PlotStyle:
    ps = PlotStyle()
    ps.setLineColor('white')
    ps.markerSymbol = None
    ps.linePen.setStyle(Qt.SolidLine)
    return ps


class SpectralLibraryUtils:
    """
    This class provides methods to handle SpectralProfiles in a QgsVectorLayer
    """

    @staticmethod
    def createProfileField(
            name: str,
            comment: str = 'SpectralProfile Field',
            encoding: ProfileEncoding = ProfileEncoding.Bytes) -> QgsField:
        """
        Creates a QgsField that can store spectral profiles
        :param name: field name
        :param comment: field comment, optional
        :return: QgsField
        """
        encoding = ProfileEncoding.fromInput(encoding)
        if encoding == ProfileEncoding.Bytes:
            field = QgsField(name=name, type=QVariant.ByteArray, comment=comment)
        elif encoding == ProfileEncoding.Text:
            field = QgsField(name=name, type=QVariant.String, len=0, comment=comment)
        elif encoding == ProfileEncoding.Json:
            field = QgsField(name=name, type=8, comment=comment)

        setup = QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {})
        field.setEditorWidgetSetup(setup)
        return field

    @staticmethod
    def writeToSource(*args, **kwds) -> List[str]:
        from .spectrallibraryio import SpectralLibraryIO
        return SpectralLibraryIO.writeToSource(*args, **kwds)

    @staticmethod
    def readFromSource(uri: str, feedback: QgsProcessingFeedback = QgsProcessingFeedback()):
        from .spectrallibraryio import SpectralLibraryIO
        return SpectralLibraryIO.readSpeclibFromUri(uri, feedback=feedback)

    @staticmethod
    def groupBySpectralProperties(*args, **kwds) -> Dict[SpectralSetting, List[QgsFeature]]:
        return groupBySpectralProperties(*args, **kwds)

    @staticmethod
    def readFromVectorLayer(source: Union[str, QgsVectorLayer]) -> Optional[QgsVectorLayer]:
        """
        Returns a vector layer as Spectral Library vector layer.
        It is assumed that binary fields without special editor widget setup are Spectral Profile fields.
        :param source: str | QgsVectorLayer
        :return: QgsVectorLayer
        """
        if isinstance(source, str):
            source = QgsVectorLayer(source)

        if not isinstance(source, QgsVectorLayer):
            return None
        if not source.isValid():
            return None

        # assume that binary fields without other editor widgets are Spectral Profile Widgets
        for idx in range(source.fields().count()):
            field: QgsField = source.fields().at(idx)
            if field.type() == QVariant.ByteArray and field.editorWidgetSetup().type() == '':
                source.setEditorWidgetSetup(idx, QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {}))

        if not is_spectral_library(source):
            return None

        return source

    @staticmethod
    def readFromMimeData(mimeData: QMimeData) -> Optional[QgsVectorLayer]:
        """
        Reads a SpectraLibrary from mime data.
        :param mimeData: QMimeData
        :return: SpectralLibrary
        """
        if MIMEDATA_SPECLIB_LINK in mimeData.formats():
            # extract from link
            sid = pickle.loads(mimeData.data(MIMEDATA_SPECLIB_LINK))
            global SPECLIB_CLIPBOARD
            sl = SPECLIB_CLIPBOARD.get(sid)
            if is_spectral_library(sl) and id(sl) == sid:
                return sl

        if mimeData.hasUrls():
            speclibs = []
            for url in mimeData.urls():
                path = url.toString(QUrl.PreferLocalFile)
                if RX_SUPPORTED_DROP_FORMATS.search(path):
                    sl = SpectralLibraryUtils.readFromSource(path)
                    if isinstance(sl, QgsVectorLayer) and sl.isValid() and sl.featureCount() > 0:
                        speclibs.append(sl)
            if len(speclibs) == 0:
                return None
            elif len(speclibs) == 1:
                return speclibs[0]
            elif len(speclibs) > 1:
                sl = speclibs[0]
                sl.startEditing()
                for sl2 in speclibs[1:]:
                    SpectralLibraryUtils.addSpeclib(sl, sl2)
                sl.commitChanges()
                return sl
        return None

    @staticmethod
    def createSpectralLibrary(
            profile_fields: List[str] = ['profiles'],
            name: str = DEFAULT_NAME) -> QgsVectorLayer:
        """
        Creates an empty in-memory spectral library with a "name" and a "profiles" field
        """
        provider = 'memory'
        path = f"point?crs=epsg:{SPECLIB_EPSG_CODE}"
        options = QgsVectorLayer.LayerOptions(loadDefaultStyle=True, readExtentFromXml=True)

        lyr = QgsVectorLayer(path, name, provider, options=options)
        lyr.setCustomProperty('skipMemoryLayerCheck', 1)
        lyr.startEditing()
        lyr.beginEditCommand('Add fields')

        assert lyr.addAttribute(QgsField(name='name', type=QVariant.String))
        for fieldname in profile_fields:
            if isinstance(fieldname, QgsField):
                fieldname = fieldname.name()
            SpectralLibraryUtils.addAttribute(lyr, create_profile_field(fieldname))
        lyr.endEditCommand()
        assert lyr.commitChanges(stopEditing=True)

        SpectralLibraryUtils.initTableConfig(lyr)

        return lyr

    @staticmethod
    def addAttribute(speclib: QgsVectorLayer, field: QgsField) -> bool:
        success = speclib.addAttribute(field)
        if success:
            i = speclib.fields().lookupField(field.name())
            if i > -1:
                speclib.setEditorWidgetSetup(i, field.editorWidgetSetup())
        return success

    @staticmethod
    def initTableConfig(speclib: QgsVectorLayer):
        """
        Initializes the QgsAttributeTableConfig and further options
        """
        assert isinstance(speclib, QgsVectorLayer)
        mgr = speclib.actions()
        assert isinstance(mgr, QgsActionManager)
        mgr.clearActions()

        # actionSetStyle = createSetPlotStyleAction(self.fields().at(self.fields().lookupField(FIELD_STYLE)))
        # assert isinstance(actionSetStyle, QgsAction)
        # mgr.addAction(actionSetStyle)

        actionRemoveSpectrum = createRemoveFeatureAction()
        assert isinstance(actionRemoveSpectrum, QgsAction)
        mgr.addAction(actionRemoveSpectrum)

        columns = speclib.attributeTableConfig().columns()

        # to discuss: invisible columns?
        invisibleColumns = []

        for column in columns:
            assert isinstance(column, QgsAttributeTableConfig.ColumnConfig)
            column.hidden = column.name in invisibleColumns

        # set column order
        # c_action = [c for c in columns if c.type == QgsAttributeTableConfig.Action][0]
        # c_name = [c for c in columns if c.name == FIELD_NAME][0]
        # firstCols = [c_action, c_name]
        # columns = [c_action, c_name] + [c for c in columns if c not in firstCols]

        conf = QgsAttributeTableConfig()
        conf.setColumns(columns)
        conf.setActionWidgetVisible(False)
        conf.setActionWidgetStyle(QgsAttributeTableConfig.ButtonList)

        speclib.setAttributeTableConfig(conf)

    @staticmethod
    def canReadFromMimeData(mimeData: QMimeData) -> bool:
        formats = [MIMEDATA_SPECLIB_LINK, MIMEDATA_SPECLIB, MIMEDATA_URL]
        for format in formats:
            if format in mimeData.formats():
                if format == MIMEDATA_URL:
                    for url in mimeData.urls():
                        if RX_SUPPORTED_DROP_FORMATS.search(url.toString(QUrl.PreferLocalFile)):
                            return True
                else:
                    return True
        return False

    @staticmethod
    def mimeData(speclib: QgsVectorLayer, formats: list = None) -> QMimeData:
        """
        Wraps this Speclib into a QMimeData object
        :return: QMimeData
        """
        assert isinstance(speclib, QgsVectorLayer)
        if isinstance(formats, str):
            formats = [formats]
        elif formats is None:
            formats = [MIMEDATA_SPECLIB_LINK]

        mimeData = QMimeData()

        for format in formats:
            assert format in [MIMEDATA_SPECLIB_LINK, MIMEDATA_SPECLIB, MIMEDATA_TEXT, MIMEDATA_URL]
            if format == MIMEDATA_SPECLIB_LINK:
                global SPECLIB_CLIPBOARD
                thisID = id(speclib)
                SPECLIB_CLIPBOARD[thisID] = speclib

                mimeData.setData(MIMEDATA_SPECLIB_LINK, pickle.dumps(thisID))
            elif format == MIMEDATA_SPECLIB:
                mimeData.setData(MIMEDATA_SPECLIB, pickle.dumps(speclib))

            elif format == MIMEDATA_URL:
                mimeData.setUrls([QUrl(speclib.source())])

            elif format == MIMEDATA_TEXT:
                from ..io.csvdata import CSVSpectralLibraryIO
                txt = CSVSpectralLibraryIO.asString(speclib)
                mimeData.setText(txt)

        return mimeData

    @staticmethod
    def addSpectralProfileField(speclib: QgsVectorLayer, name: str, comment: str = None) -> bool:
        return speclib.addAttribute(create_profile_field(name, comment))

    @staticmethod
    def addMissingFields(speclib: QgsVectorLayer, fields: QgsFields, copyEditorWidgetSetup: bool = True):
        """
        :param fields: list of QgsFields
        :param copyEditorWidgetSetup: if True (default), the editor widget setup is copied for each profile_field
        """
        assert isinstance(speclib, QgsVectorLayer)
        missingFields = []
        for field in fields:
            assert isinstance(field, QgsField)
            iField = speclib.fields().lookupField(field.name())
            if iField == -1:
                missingFields.append(field)

        if len(missingFields) > 0:
            for fOld in missingFields:
                speclib.addAttribute(QgsField(fOld))

            if copyEditorWidgetSetup:
                SpectralLibraryUtils.copyEditorWidgetSetup(speclib, missingFields)

    @staticmethod
    def addSpeclib(speclibDst, speclibSrc,
                   addMissingFields: bool = True,
                   copyEditorWidgetSetup: bool = True,
                   feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> List[int]:
        """
        Adds profiles from another SpectraLibrary
        :param speclibDst: QgsVectorLayer
        :param addMissingFields: if True (default), missing fields / attributes will be added automatically
        :param copyEditorWidgetSetup: if True (default), the editor widget setup will be copied
               for each added profile_field
        :param progressDialog: QProgressDialog or qps.speclib.core.ProgressHandler

        :returns: set of added feature ids
        """
        assert is_spectral_library(speclibSrc)
        assert is_spectral_library(speclibDst)

        fids_old = sorted(speclibSrc.allFeatureIds(), key=lambda i: abs(i))
        fids_new = SpectralLibraryUtils.addProfiles(
            speclibDst,
            speclibSrc.getFeatures(),
            addMissingFields=addMissingFields,
            copyEditorWidgetSetup=copyEditorWidgetSetup,
            feedback=feedback)

        return fids_new

    @staticmethod
    def addProfiles(speclib: QgsVectorLayer,
                    profiles: Union[QgsFeature, List[QgsFeature], QgsVectorLayer],
                    crs: QgsCoordinateReferenceSystem = None,
                    addMissingFields: bool = False,
                    copyEditorWidgetSetup: bool = True,
                    feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> List[int]:

        assert isinstance(speclib, QgsVectorLayer)
        assert speclib.isEditable(), 'SpectralLibrary "{}" is not editable. call startEditing() first'.format(
            speclib.name())

        if isinstance(profiles, QgsFeature):
            profiles = [profiles]
        elif isinstance(profiles, QgsVectorLayer):
            crs = profiles.crs()
            profiles = list(profiles.getFeatures())
        elif isinstance(profiles, QgsFeatureIterator):
            profiles = list(profiles)

        if len(profiles) == 0:
            return []

        if crs is None:
            crs = speclib.crs()

        refProfile = profiles[0]

        new_edit_command: bool = not speclib.isEditCommandActive()
        if new_edit_command:
            speclib.beginEditCommand('Add profiles')

        if addMissingFields:
            SpectralLibraryUtils.addMissingFields(speclib, refProfile.fields(),
                                                  copyEditorWidgetSetup=copyEditorWidgetSetup)
            assert speclib.commitChanges(False)

        keysBefore = set(speclib.editBuffer().addedFeatures().keys())

        lastTime = datetime.datetime.now()
        dt = datetime.timedelta(seconds=2)
        nTotal = len(profiles)
        feedback.setProgressText(f'Add {nTotal} profiles')
        feedback.setProgress(0)

        speclib.commitChanges(False)

        sinkDefinition = QgsRemappingSinkDefinition()
        sinkDefinition.setSourceCrs(crs)
        sinkDefinition.setDestinationCrs(speclib.crs())
        sinkDefinition.setDestinationFields(speclib.fields())
        sinkDefinition.setDestinationWkbType(speclib.wkbType())
        for field in refProfile.fields():
            name = field.name()
            if name in speclib.fields().names():
                sinkDefinition.addMappedField(name, QgsProperty.fromField(name))

        expressionContext = QgsExpressionContext()
        expressionContext.setFields(refProfile.fields())
        expressionContext.setFeedback(feedback)

        scope = QgsExpressionContextScope()
        scope.setFields(refProfile.fields())
        expressionContext.appendScope(scope)
        transformationContext = QgsCoordinateTransformContext()

        featureSink = QgsRemappingProxyFeatureSink(sinkDefinition, speclib)
        featureSink.setExpressionContext(expressionContext)
        featureSink.setTransformContext(transformationContext)

        if not featureSink.addFeatures(profiles):
            print(featureSink.lastError(), file=sys.stderr)
            return []
        else:
            featureSink.flushBuffer()
        if new_edit_command:
            speclib.endEditCommand()

        # return the edited features
        MAP = speclib.editBuffer().addedFeatures()
        fids_inserted = [MAP[k].id() for k in reversed(list(MAP.keys())) if k not in keysBefore]
        return fids_inserted

    @staticmethod
    def setProfileValues(feature: QgsFeature, *args, field: Union[int, str, QgsField] = None, **kwds):
        if field is None:
            # use the first profile field by default
            field = profile_field_list(feature)[0]
        else:
            field: QgsField = qgsField(feature, field)
        profileDict = prepareProfileValueDict(*args, **kwds)
        value = encodeProfileValueDict(profileDict, field)
        feature.setAttribute(field.name(), value)

    @staticmethod
    def speclibFromFeatureIDs(layer: QgsVectorLayer, fids):
        if isinstance(fids, int):
            fids = [fids]
        assert isinstance(fids, list)

        features = list(layer.getFeatures(fids))

        sl = SpectralLibraryUtils.createSpectralLibrary(profile_fields=[])
        sl.startEditing()
        SpectralLibraryUtils.addMissingFields(sl, layer.fields())
        sl.addFeatures(features)
        sl.commitChanges()
        return sl

    @staticmethod
    def renameAttribute(speclib: QgsVectorLayer, index, newName):
        setup = speclib.editorWidgetSetup(index)
        speclib.renameAttribute(index, newName)
        speclib.setEditorWidgetSetup(index, setup)

    @staticmethod
    def profileBlocks(speclib: QgsVectorLayer,
                      fids=None,
                      profile_field: Union[int, str, QgsField] = None,
                      ) -> List[SpectralProfileBlock]:
        """
        Reads SpectralProfiles into profile blocks with different spectral settings
        :return:
        """
        if profile_field is None:
            profile_field = first_profile_field_index(speclib)
        return SpectralProfileBlock.fromSpectralProfiles(
            SpectralLibraryUtils.profiles(speclib, fids=fids, profile_field=profile_field),
            profile_field=profile_field
        )

    @staticmethod
    def countProfiles(speclib: QgsVectorLayer) -> Dict[str, int]:
        COUNTS = dict()
        for field in profile_field_list(speclib):
            requests = QgsFeatureRequest()
            requests.setFilterExpression(f'"{field.name()}" is not NULL')
            n = len(list(speclib.getFeatures(requests)))

            COUNTS[field.name()] = n
        return COUNTS

    @staticmethod
    def profile(speclib: QgsVectorLayer, fid: int, value_field=None) -> SpectralProfile:
        warnings.warn(DeprecationWarning())
        assert is_spectral_library(speclib)
        if value_field is None:
            value_field = profile_field_list(speclib)[0]
        return SpectralProfile.fromQgsFeature(speclib.getFeature(fid), profile_field=value_field)

    @staticmethod
    def profiles(vectorlayer: QgsVectorLayer,
                 fids: List[int] = None,
                 profile_field: Union[int, str, QgsField] = None,
                 ) -> \
            Generator[SpectralProfile, None, None]:
        """
        Reads SpectralProfiles from a vector layers BLOB 'profile_field'.

        Like features(keys_to_remove=None), but converts each returned QgsFeature into a SpectralProfile.
        If multiple value fields are set, profiles are returned ordered by (i) fid and (ii) value profile_field.
        SpectralProfiles are returned for profile_field != NULL only
        :param vectorlayer:
        :param profile_field:
        :type profile_field:
        :param fids: optional, [int-list-of-feature-ids] to return
        :return: generator of [List-of-SpectralProfiles]
        """
        warnings.warn(DeprecationWarning())
        if profile_field is None:
            profile_field = first_profile_field_index(vectorlayer)
        else:
            assert isinstance(profile_field, (int, str, QgsField))
            profile_field = field_index(vectorlayer, profile_field)
        featureRequest = QgsFeatureRequest()
        if fids:
            featureRequest.setFilterFids(fids)
        for f in vectorlayer.getFeatures(featureRequest):
            yield SpectralProfile.fromQgsFeature(f, profile_field=profile_field)

    @staticmethod
    def plot(speclib: QgsVectorLayer) -> QWidget:
        assert is_spectral_library(speclib)
        app = None
        if not isinstance(QgsApplication.instance(), QgsApplication):
            from ...testing import start_app
            app = start_app()

        from ..gui.spectrallibrarywidget import SpectralLibraryWidget

        w = SpectralLibraryWidget(speclib=speclib)
        w.show()

        if app:
            app.exec_()

        return w

    @staticmethod
    def copyEditorWidgetSetup(speclib: QgsVectorLayer, fields: Union[QgsVectorLayer, List[QgsField]]):
        """

        :param fields:
        :type fields:
        :return:
        :rtype:
        """
        """Copies the editor widget setup from another vector layer or list of QgsField"""
        if isinstance(fields, QgsVectorLayer):
            fields = fields.fields()

        for fSrc in fields:
            assert isinstance(fSrc, QgsField)
            idx = speclib.fields().indexOf(fSrc.name())

            if idx == -1:
                # profile_field name does not exist
                continue
            fDst = speclib.fields().at(idx)
            assert isinstance(fDst, QgsField)

            setup = fSrc.editorWidgetSetup()
            if QgsGui.instance().editorWidgetRegistry().factory(setup.type()).supportsField(speclib, idx):
                speclib.setEditorWidgetSetup(idx, setup)
    # assign


class SpectralLibrary(QgsVectorLayer):
    """
    SpectralLibrary
    """

    @staticmethod
    def readFromMimeData(*args, **kwds):
        return SpectralLibraryUtils.readFromMimeData(*args, **kwds)

    @staticmethod
    def readFromPickleDump(data):
        """
        Reads a SpectralLibrary from a pickle.dump()-generate bytes object.
        :param data: bytes
        :return: SpectralLibrary
        """
        return pickle.loads(data)

    @staticmethod
    def readFromSourceDialog(parent=None):
        """
        Opens a FileOpen dialog to select a spectral library
        :param parent:
        :return: SpectralLibrary
        """

        SETTINGS = speclibSettings()
        lastDataSourceDir = SETTINGS.value('SpeclibSourceDirectory', '')

        if not QFileInfo(lastDataSourceDir).isDir():
            lastDataSourceDir = None

        uris, filter = QFileDialog.getOpenFileNames(parent, "Open Spectral Library", lastDataSourceDir,
                                                    filter=FILTERS + ';;All files (*.*)', )

        if len(uris) > 0:
            SETTINGS.setValue('SpeclibSourceDirectory', os.path.dirname(uris[0]))

        uris = [u for u in uris if QFileInfo(u).isFile()]

        if len(uris) == 0:
            return None

        speclib = SpectralLibrary()
        speclib.startEditing()
        for u in uris:
            sl = SpectralLibrary.readFrom(str(u))
            if is_spectral_library(sl):
                SpectralLibraryUtils.addProfiles(speclib, sl)
        assert speclib.commitChanges()
        return speclib

    # thanks to Ann for providing https://bitbucket.org/jakimowb/qgispluginsupport/issues/6/speclib-spectrallibrariespy
    @staticmethod
    def readFromVector(vector: QgsVectorLayer = None,
                       raster: QgsRasterLayer = None,
                       progress_handler: QgsProcessingFeedback = None,
                       name_field: str = None,
                       all_touched: bool = False,
                       cache: int = 5 * 2 ** 20,
                       copy_attributes: bool = False,
                       block_size: Tuple[int, int] = None,
                       return_profile_list: bool = False):
        """
        Reads SpectraProfiles from a raster source, based on the locations specified in a vector data set.
        Opens a Select Polygon Layer dialog to select the correct polygon and returns a Spectral Library with
        metadata according to the polygons attribute table.

        :param block_size:
        :param copy_attributes:
        :param cache:
        :param vector: QgsVectorLayer | str
        :param raster: QgsRasterLayer | str
        :param progress_handler: QProgressDialog (optional)
        :param name_field: str | int | QgsField that is used to generate individual profile names.
        :param all_touched: bool, False (default) = extract only pixel entirely covered with a geometry
                                  True = extract all pixels touched by a geometry
        :param return_profile_list: bool, False (default) = return a SpectralLibrary
                                        True = return a [list-of-SpectralProfiles] and skip the creation of
                                        a SpectralLibrary. This might become faster if the spectral profiles
                                        are to be added to another SpectraLibrary anyway.
        :return: Spectral Library | [list-of-profiles]
        """

        t0 = datetime.datetime.now()
        dtReport = datetime.timedelta(seconds=1)

        # get QgsLayers of vector and raster
        if vector is None and raster is None:

            dialog = SelectMapLayersDialog()
            dialog.addLayerDescription('Raster', QgsMapLayerProxyModel.RasterLayer)
            dialog.addLayerDescription('Vector', QgsMapLayerProxyModel.VectorLayer)
            dialog.exec_()
            if dialog.result() == QDialog.Accepted:
                raster, vector = dialog.mapLayers()

                if not isinstance(vector, QgsVectorLayer) or not isinstance(raster, QgsRasterLayer):
                    return

        vector: QgsVectorLayer = qgsVectorLayer(vector)
        raster: QgsRasterLayer = qgsRasterLayer(raster)

        if name_field:
            assert name_field in vector.fields().names(), \
                f'invalid profile_field name "{name_field}". Allowed values are {", ".join(vector.fields().names())}'
        else:
            for idx in range(vector.fields().count()):
                field: QgsField = vector.fields().at(idx)
                if field.type() == QVariant.String and re.search('name', field.name(), re.I):
                    name_field = field.name()
                    break

        ds: gdal.Dataset = gdalDataset(raster)
        assert isinstance(ds, gdal.Dataset), f'Unable to open {raster.source()} as gdal.Dataset'

        if progress_handler:
            progress_handler.setProgressText('Calculate profile positions...')

        bbl = parseBadBandList(ds)
        wl, wlu = parseWavelength(ds)

        # the SpectralLibrary to be returned
        spectral_library = SpectralLibrary()
        spectral_library.startEditing()

        # add other attributes to SpectralLibrary
        fields_to_copy = []
        copy_pixel_positions: bool = False
        if copy_attributes:
            existing = [n.lower() for n in spectral_library.fields().names()]
            for field in vector.fields():
                assert isinstance(field, QgsField)
                if field.name().lower() not in existing:
                    spectral_library.addAttribute(QgsField(field))
                    fields_to_copy.append(field.name())
                    existing.append(field.name().lower())
            # copy raster pixel positions
            if 'px_x' not in existing and 'px_y' not in existing:
                spectral_library.addAttribute(createQgsField('px_x', 1, 'pixel index x'))
                spectral_library.addAttribute(createQgsField('px_y', 1, 'pixel index y'))
                copy_pixel_positions = True

        assert spectral_library.commitChanges()
        assert spectral_library.startEditing()

        if block_size is None:
            block_size = optimize_block_size(ds, cache=cache)

        nXBlocks = int((ds.RasterXSize + block_size[0] - 1) / block_size[0])
        nYBlocks = int((ds.RasterYSize + block_size[1] - 1) / block_size[1])
        nBlocksTotal = nXBlocks * nYBlocks
        nBlocksDone = 0

        # pixel center coordinates as geolocation
        geo_x, geo_y = px2geocoordinates(ds,
                                         target_srs=spectral_library.crs(),
                                         pxCenter=True)

        # get FID positions
        layer = 0
        for sub in vector.dataProvider().subLayers():
            layer = sub.split('!!::!!')[1]
            break

        fid_positions, no_fid = fid2pixelindices(ds, vector,
                                                 layer=layer,
                                                 all_touched=all_touched)

        if progress_handler:
            progress_handler.setProgressText('Read profile values..')
            progress_handler.setValue(progress_handler.value() + 1)

        PROFILE_COUNTS = dict()

        FEATURES: Dict[int, QgsFeature] = dict()

        block_profiles = []

        for y in range(nYBlocks):
            yoff = y * block_size[1]
            for x in range(nXBlocks):
                xoff = x * block_size[0]
                xsize = min(block_size[0], ds.RasterXSize - xoff)
                ysize = min(block_size[1], ds.RasterYSize - yoff)
                cube: np.ndarray = ds.ReadAsArray(xoff=xoff, yoff=yoff, xsize=xsize, ysize=ysize)
                fid_pos = fid_positions[yoff:yoff + ysize, xoff:xoff + xsize]
                assert cube.shape[1:] == fid_pos.shape

                for fid in [int(v) for v in np.unique(fid_pos) if v != no_fid]:
                    fid_yy, fid_xx = np.where(fid_pos == fid)
                    n_p = len(fid_yy)
                    if n_p > 0:

                        if fid not in FEATURES.keys():
                            FEATURES[fid] = vector.getFeature(fid)
                        vectorFeature: QgsFeature = FEATURES.get(fid)
                        if name_field:
                            fid_basename = str(FEATURES[fid].attribute(name_field)).strip()
                        else:
                            fid_basename = f'{vector.name()} {fid}'.strip()

                        fid_profiles = cube[:, fid_yy, fid_xx]
                        profile_geo_x = geo_x[fid_yy + yoff, fid_xx + xoff]
                        profile_geo_y = geo_y[fid_yy + yoff, fid_xx + xoff]
                        profile_px_x = fid_xx + xoff
                        profile_px_y = fid_yy + yoff

                        for idx in range(n_p):
                            # create profile feature
                            sp = SpectralProfile(fields=spectral_library.fields())

                            # create geometry
                            sp.setGeometry(QgsPoint(profile_geo_x[idx],
                                                    profile_geo_y[idx]))

                            PROFILE_COUNTS[fid] = PROFILE_COUNTS.get(fid, 0) + 1
                            # sp.setName(f'{fid_basename}_{PROFILE_COUNTS[fid]}')
                            sp.setValues(x=wl,
                                         y=fid_profiles[:, idx],
                                         xUnit=wlu,
                                         bbl=bbl)
                            if vectorFeature.isValid():
                                for field_name in fields_to_copy:
                                    sp[field_name] = vectorFeature[field_name]
                            if copy_pixel_positions:
                                sp['px_x'] = int(profile_px_x[idx])
                                sp['px_y'] = int(profile_px_y[idx])
                            if progress_handler and progress_handler.wasCanceled():
                                return None

                            block_profiles.append(sp)
                if not return_profile_list:
                    if not spectral_library.addFeatures(block_profiles):
                        spectral_library.raiseError()
                    block_profiles.clear()

                nBlocksDone += 1
                if progress_handler:
                    if nBlocksDone == nBlocksTotal or datetime.datetime.now() - t0 > dtReport:
                        t0 = datetime.datetime.now()
                        progress_handler.setValue(nBlocksDone + 1)

        if return_profile_list:
            return block_profiles
        else:
            if not spectral_library.commitChanges():
                spectral_library.raiseError()

            return spectral_library

    @staticmethod
    def readFromRasterPositions(pathRaster, positions,
                                progressDialog: QgsProcessingFeedback = None):
        """
        Reads a SpectralLibrary from a set of positions
        :param pathRaster:
        :param positions:
        :return:
        """
        if not isinstance(positions, list):
            positions = [positions]
        profiles = []

        source = gdalDataset(pathRaster)
        i = 0

        nTotal = len(positions)
        if isinstance(progressDialog, QgsProcessingFeedback):
            progressDialog.setProgress(0)
            progressDialog.setProgressText('Extract pixel profiles...')

        for p, position in enumerate(positions):

            if isinstance(progressDialog, QgsProcessingFeedback) and progressDialog.wasCanceled():
                return None

            profile = SpectralProfile.fromRasterSource(source, position)
            if isinstance(profile, SpectralProfile):
                profiles.append(profile)
                i += 1

            if isinstance(progressDialog, QgsProcessingFeedback):
                progressDialog.setValue(progressDialog.value() + 1)

        sl = SpectralLibrary()
        sl.startEditing()
        sl.addProfiles(profiles)
        assert sl.commitChanges()
        return sl

    def readJSONProperties(self, pathJSON: str):
        """
        Reads additional SpectralLibrary properties from a JSON definition according to
        https://enmap-box.readthedocs.io/en/latest/usr_section/usr_manual/processing_datatypes.html#labelled-spectral-library

        :param pathJSON: file path (any) | JSON dictionary | str

        :returns: None | JSON dictionary
        """
        jsonData = None
        try:
            if isinstance(pathJSON, dict):
                jsonData = pathJSON
            elif isinstance(pathJSON, str):
                if os.path.isfile(pathJSON):
                    if not re.search(r'.json$', pathJSON):
                        pathJSON = os.path.splitext(pathJSON)[0] + '.json'
                        if not os.path.isfile(pathJSON):
                            return
                    with open(pathJSON, 'r') as file:
                        jsonData = json.load(file)
                else:
                    jsonData = json.loads(pathJSON)

        except Exception as ex:
            print(ex, file=sys.stderr)
            pass

        if not isinstance(jsonData, dict):
            return None
        b = self.isEditable()
        self.startEditing()
        try:
            for fieldName in self.fields().names():
                fieldIndex = self.fields().lookupField(fieldName)
                field = self.fields().at(fieldIndex)
                assert isinstance(field, QgsField)
                assert isinstance(fieldName, str)
                if fieldName in jsonData.keys():
                    fieldProperties = jsonData[fieldName]
                    assert isinstance(fieldProperties, dict)

                    # see https://enmap-box.readthedocs.io/en/latest/usr_section/
                    # usr_manual/processing_datatypes.html#labelled-spectral-library
                    # for details
                    if 'categories' in fieldProperties.keys():
                        from ...classification.classificationscheme import ClassificationScheme, ClassInfo, \
                            classSchemeToConfig
                        from ...classification.classificationscheme import EDITOR_WIDGET_REGISTRY_KEY as ClassEditorKey
                        classes = []
                        for item in fieldProperties['categories']:
                            cColor = None
                            if len(item) >= 3:
                                cColor = item[2]
                                if isinstance(cColor, str):
                                    cColor = QColor(cColor)
                                elif isinstance(cColor, list):
                                    cColor = QColor(*cColor)

                            classes.append(ClassInfo(label=int(item[0]), name=str(item[1]), color=cColor))
                        classes = sorted(classes, key=lambda c: c.label())
                        scheme = ClassificationScheme()
                        for classInfo in classes:
                            scheme.insertClass(classInfo)
                        classConfig = classSchemeToConfig(scheme)

                        self.setEditorWidgetSetup(fieldIndex,
                                                  QgsEditorWidgetSetup(ClassEditorKey, classConfig))

                        s = ""
                    if 'no data value' in fieldProperties.keys():
                        defaultValue = QgsDefaultValue('{}'.format(fieldProperties['no data value']))
                        field.setDefaultValueDefinition(defaultValue)
                        pass

                    if 'description' in fieldProperties.keys():
                        field.setComment(fieldProperties['description'])

            self.commitChanges()
        except Exception as ex:
            self.rollBack()
            print(ex, file=sys.stderr)

        if b:
            self.startEditing()

        return jsonData

    def copyEditorWidgetSetup(self, *args, **kwds):
        SpectralLibraryUtils.copyEditorWidgetSetup(self, *args, **kwds)

    @staticmethod
    def readFrom(uri, feedback: QgsProcessingFeedback = None):
        """
        Reads a Spectral Library from the source specified in "uri" (path, url, ...)
        :param feedback:
        :param uri: path or uri of the source from which to read SpectralProfiles and return them in a SpectralLibrary
        :return: SpectralLibrary
        """
        return SpectralLibraryUtils.readFromSource(uri, feedback)

    # sigProgressInfo = pyqtSignal(int, int, str)

    def __init__(self,
                 path: str = None,
                 baseName: str = DEFAULT_NAME,
                 provider: str = 'ogr',
                 options: QgsVectorLayer.LayerOptions = None,
                 fields: QgsFields = None,
                 profile_fields: List[str] = [FIELD_VALUES],
                 create_name_field: bool = True):
        """
        Create a SpectralLibrary, i.e. a QgsVectorLayer with one or multiple binary fields that use the
        the SpectralProfile editor widget
        :param path: str
        :param baseName: layer name
        :param options: QgsVectorLayer.LayerOptions. Will be used if path refers to an existing layer
        :param fields: QgsField. Described the fields to create.
        :param profile_fields: list of field names to be used for profile fields (1).
        :param create_name_field: bool, if True (default) a string field will be added to contain profile names (1).
        (1) Only used of fields is None
        """
        warnings.warn(DeprecationWarning('Will be removed. Use SpectralLibraryUtils to access spectral profiles '
                                         'within QgsVectorLayers'), stacklevel=2)
        if isinstance(path, pathlib.Path):
            path = path.as_posix()

        if not isinstance(options, QgsVectorLayer.LayerOptions):
            options = QgsVectorLayer.LayerOptions(loadDefaultStyle=True, readExtentFromXml=True)

        create_new_speclib = path is None

        if create_new_speclib:
            # QGIS In-Memory Layer
            provider = 'memory'
            # path = "point?crs=epsg:4326&field=fid:integer"
            path = f"point?crs=epsg:{SPECLIB_EPSG_CODE}"
            # scratchLayer = QgsVectorLayer(uri, "Scratch point layer", "memory")
        assert isinstance(path, str)
        super().__init__(path, baseName, provider, options)

        self.setCustomProperty('skipMemoryLayerCheck', 1)

        if create_new_speclib:

            if fields is None:
                assert self.startEditing()
                # add profile fields
                self.beginEditCommand('Add fields')
                names = self.fields().names()
                # add a single name profile_field (more is not required)
                if create_name_field:
                    self.addAttribute(QgsField(name='name', type=QVariant.String))

                for fieldname in profile_fields:
                    self.addAttribute(create_profile_field(fieldname))
                    # assert self.addSpectralProfileField(fieldname), f'Unable to add profile field "{fieldname}"'

                profile_indices = [self.fields().lookupField(f) for f in profile_fields]
                self.endEditCommand()
                fields = []
                for i in profile_indices:
                    assert self.editorWidgetSetup(i).type() == EDITOR_WIDGET_REGISTRY_KEY
                    s = ""
                assert self.commitChanges(stopEditing=True)
                for i in profile_indices:
                    assert self.editorWidgetSetup(i).type() == EDITOR_WIDGET_REGISTRY_KEY
            else:
                assert self.startEditing()
                self.beginEditCommand('Add fields')
                for i in range(fields.count()):
                    field = fields.at(i)
                    self.addAttribute(field)
                self.endEditCommand()

                # copy editor widget type

                assert self.commitChanges(stopEditing=True)
        else:
            fields: QgsFields = self.fields()
            for name in profile_fields:
                i = fields.lookupField(name)
                if i > -1:
                    field: QgsField = fields.at(i)
                    editorWidget: QgsEditorWidgetSetup = field.editorWidgetSetup()
                    if field.type() == QVariant.ByteArray and editorWidget.type() == '':
                        self.setEditorWidgetSetup(i, QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {}))

        self.initTableConfig()

    def addAttribute(self, field):
        return SpectralLibraryUtils.addAttribute(self, field)

    def initTableConfig(self):

        """
        Initializes the QgsAttributeTableConfig and further options
        """
        SpectralLibraryUtils.initTableConfig(self)

    def mimeData(self, *args, **kwds) -> QMimeData:
        return SpectralLibraryUtils.mimeData(self, *args, **kwds)

    def addSpectralProfileField(self, *args, **kwds) -> bool:
        return SpectralLibraryUtils.addSpectralProfileField(self, *args, **kwds)

    def addMissingFields(self, *args, **kwds):
        SpectralLibraryUtils.addMissingFields(self, *args, **kwds)

    def addSpeclib(self, *args, **kwds):
        return SpectralLibraryUtils.addSpeclib(self, *args, **kwds)

    def addProfiles(self, *args, **kwds):
        return SpectralLibraryUtils.addProfiles(self, *args, **kwds)

    def speclibFromFeatureIDs(self, *args, **kwds) -> QgsVectorLayer:
        return SpectralLibraryUtils.speclibFromFeatureIDs(self, *args, **kwds)

    def renameAttribute(self, *args, **kwds):
        SpectralLibraryUtils.renameAttribute(self, *args, **kwds)

    def removeProfiles(self, profiles):
        """
        Removes profiles from this ProfileSet
        :param profiles: Profile or [list-of-profiles] to be removed
        :return: [list-of-remove profiles] (only profiles that existed in this set before)
        """
        warnings.warn('will be removed', DeprecationWarning)
        if not isinstance(profiles, list):
            profiles = [profiles]

        for p in profiles:
            assert isinstance(p, SpectralProfile)

        fids = [p.id() for p in profiles]
        if len(fids) == 0:
            return

        assert self.isEditable()
        self.deleteFeatures(fids)

    def profileBlocks(self, *args, **kwds):
        return SpectralLibraryUtils.profileBlocks(self, *args, **kwds)

    def profile(self, *args, **kwds):
        return SpectralLibraryUtils.profile(self, *args, **kwds)

    def profiles(self, *args, **kwds):
        return SpectralLibraryUtils.profiles(self, *args, **kwds)

    def groupBySpectralProperties(self,
                                  fids=None,
                                  profile_field=None,
                                  excludeEmptyProfiles: bool = True
                                  ) -> Dict[SpectralSetting, List[SpectralProfile]]:
        """
        Returns SpectralProfiles grouped by key = (xValues, xUnit and yUnit):

            xValues: None | [list-of-xvalues with n>0 elements]
            xUnit: None | str with len(str) > 0, e.g. a wavelength like 'nm'
            yUnit: None | str with len(str) > 0, e.g. 'reflectance' or '-'

        :return: {SpectralSetting:[list-of-profiles]}
        """
        return groupBySpectralProperties(self.profiles(
            fids=fids,
            profile_field=profile_field,
        ),
            excludeEmptyProfiles=excludeEmptyProfiles
        )

    def exportProfiles(self, *args, **kwds) -> list:
        warnings.warn('Use SpectralLibrary.write() instead', DeprecationWarning)
        return self.write(*args, **kwds)

    def writeRasterImages(self, pathOne: Union[str, pathlib.Path], drv: str = 'GTiff') -> \
            List[pathlib.Path]:
        warnings.warn('will be removed', DeprecationWarning)
        """
        Writes the SpectralLibrary into images of same spectral properties
        :return: list of image paths
        """
        if not isinstance(pathOne, pathlib.Path):
            pathOne = pathlib.Path(pathOne)

        basename, ext = os.path.splitext(pathOne.name)

        assert pathOne.as_posix().startswith('/vsimem/') or pathOne.parent.is_dir(), f'Cannot write to {pathOne}'
        imageFiles = []
        for setting, profiles in self.groupBySpectralProperties().items():
            xValues = setting.x()
            xUnit = setting.xUnit()
            yUnit = setting.yUnit()

            ns: int = len(profiles)
            nb = len(xValues)

            ref_profile = np.asarray(profiles[0].yValues())
            dtype = ref_profile.dtype
            imageArray = np.empty((nb, 1, ns), dtype=dtype)
            imageArray[:, 0, 0] = ref_profile

            for i in range(1, len(profiles)):
                imageArray[:, 0, i] = np.asarray(profiles[i].yValues(), dtype=dtype)

            if len(imageFiles) == 0:
                pathDst = pathOne.parent / f'{basename}{ext}'
            else:
                pathDst = pathOne.parent / f'{basename}{len(imageFiles)}{ext}'

            dsDst: gdal.Dataset = gdal_array.SaveArray(imageArray, pathDst.as_posix(), format=drv)
            fakeProjection: osr.SpatialReference = osr.SpatialReference()
            fakeProjection.SetFromUserInput('EPSG:3857')
            dsDst.SetProjection(fakeProjection.ExportToWkt())
            # north-up project, 1 px above equator, starting at 0°, n pixels = n profiles towards east
            dsDst.SetGeoTransform([0.0, 1.0, 0.0, 1.0, 0.0, -1.0])
            xvalue_string = ','.join(f'{v}' for v in xValues)
            dsDst.SetMetadataItem('wavelength units', xUnit)
            dsDst.SetMetadataItem('wavelength', xvalue_string)
            # backward compatibility for stupid algorithms
            dsDst.SetMetadataItem('wavelength units', xUnit, 'ENVI')
            dsDst.SetMetadataItem('wavelength', f'{{{xvalue_string}}}', 'ENVI')

            dsDst.FlushCache()
            imageFiles.append(pathDst)
            del dsDst
        return imageFiles

    def write(self, uri,
              settings: dict = None,
              feedback: QgsProcessingFeedback = None) -> List[str]:
        return SpectralLibraryUtils.writeToSource(self, uri, settings=settings, feedback=feedback)

    def spectralProfileFields(self) -> List[QgsField]:
        return profile_field_list(self)

    def __repr__(self):
        return str(self.__class__) + '"{}" {} feature(s)'.format(
            self.name(), self.dataProvider().featureCount())

    def plot(self) -> QWidget:
        """Create a plot widget and shows all SpectralProfile in this SpectralLibrary."""
        return SpectralLibraryUtils.plot(self)

    def fieldNames(self) -> list:
        """
        Returns the profile_field names. Shortcut from self.fields().names()
        :return: [list-of-str]
        """
        return self.fields().names()

    def __reduce_ex__(self, protocol):
        return self.__class__, (), self.__getstate__()

    def __getstate__(self):
        """
        Pickles a SpectralLibrary
        :return: pickle dump
        """

        fields = qgsFields2str(self.fields())
        data = []
        for feature in self.getFeatures():
            data.append((feature.geometry().asWkt(),
                         qgsFieldAttributes2List(feature.attributes())
                         ))

        dump = pickle.dumps((self.name(), fields, data))
        return dump
        # return self.__dict__.copy()

    def __setstate__(self, state):
        """
        Restores a pickled SpectralLibrary
        :param state:
        :return:
        """
        name, fields, data = pickle.loads(state)
        self.setName(name)
        fieldNames = self.fields().names()
        dataFields = str2QgsFields(fields)
        fieldsToAdd = [f for f in dataFields if f.name() not in fieldNames]
        self.startEditing()
        if len(fieldsToAdd) > 0:

            for field in fieldsToAdd:
                assert isinstance(field, QgsField)
                self.fields().append(field)
            self.commitChanges()
            self.startEditing()

        fieldNames = self.fields().names()
        order = [fieldNames.index(f.name()) for f in dataFields]
        reoder = list(range(len(dataFields))) != order

        features = []
        nextFID = self.allFeatureIds()
        nextFID = max(nextFID) if len(nextFID) else 0

        for i, datum in enumerate(data):
            nextFID += 1
            wkt, attributes = datum
            feature = QgsFeature(self.fields(), nextFID)
            if reoder:
                attributes = [attributes[i] for i in order]
            feature.setAttributes(attributes)
            # feature.setAttribute(FIELD_FID, nextFID)
            feature.setGeometry(QgsGeometry.fromWkt(wkt))
            features.append(feature)
        self.addFeatures(features)
        self.commitChanges()

    def __len__(self) -> int:
        cnt = self.featureCount()
        # can be -1 if the number of features is unknown
        return max(cnt, 0)

    def __iter__(self):
        return self.profiles()

    def __getitem__(self, slice) -> Union[SpectralProfile, List[SpectralProfile]]:
        fids = sorted(self.allFeatureIds())[slice]
        fields = self.spectralProfileFields()
        if len(fields) > 0:
            value_field = fields[0].name()
            if isinstance(fids, list):
                return sorted(self.profiles(fids=fids), key=lambda p: p.id())
            else:
                return SpectralProfile.fromQgsFeature(self.getFeature(fids), profile_field=value_field)

    def __delitem__(self, slice):
        profiles = self[slice]
        if not isinstance(profiles, list):
            profiles = [profiles]

        fids = [p.id() for p in profiles if isinstance(p, QgsFeature)]
        if len(fids) == 0:
            return

        assert self.isEditable()
        self.deleteFeatures(fids)

    def __hash__(self):
        # return super(SpectralLibrary, self).__hash__()
        return hash(self.id())


def deleteSelected(layer):
    assert isinstance(layer, QgsVectorLayer)
    b = layer.isEditable()

    layer.startEditing()
    layer.beginEditCommand('Delete selected features')
    layer.deleteSelectedFeatures()
    layer.endEditCommand()

    if not b:
        layer.commitChanges()

    # saveEdits(layer, leaveEditable=b)
