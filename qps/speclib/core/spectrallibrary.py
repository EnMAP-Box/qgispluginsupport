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
import os
import pathlib
import pickle
import re
import sys
import warnings
import weakref
from typing import Dict, List, Optional, Union

from osgeo import gdal, ogr

from qgis.PyQt.QtCore import QMimeData, QUrl, QVariant, Qt
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import Qgis, QgsAction, QgsActionManager, QgsApplication, QgsAttributeTableConfig, \
    QgsCoordinateReferenceSystem, QgsCoordinateTransformContext, QgsEditorWidgetSetup, QgsExpression, \
    QgsExpressionContext, QgsExpressionContextScope, QgsExpressionContextUtils, QgsFeature, QgsFeatureIterator, \
    QgsFeatureRequest, QgsField, QgsFields, QgsGeometry, QgsMapLayerStore, QgsPointXY, QgsProcessingFeedback, \
    QgsProject, QgsProperty, QgsRasterLayer, QgsRemappingProxyFeatureSink, QgsRemappingSinkDefinition, QgsVectorLayer, \
    QgsWkbTypes, edit
from . import can_store_spectral_profiles, create_profile_field, is_profile_field, is_spectral_library, \
    profile_field_list, profile_field_names
from .spectralprofile import ProfileEncoding, SpectralSetting, decodeProfileValueDict, encodeProfileValueDict, \
    groupBySpectralProperties, prepareProfileValueDict
from .. import EDITOR_WIDGET_REGISTRY_KEY, FIELD_NAME, FIELD_VALUES, SPECLIB_EPSG_CODE
from ...plotstyling.plotstyling import PlotStyle
from ...qgisenums import QGIS_WKBTYPE, QMETATYPE_QBYTEARRAY, QMETATYPE_QSTRING, QMETATYPE_QVARIANTMAP
from ...utils import SpatialPoint, copyEditorWidgetSetup, findMapLayer, qgsField

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
            comment: str = None,
            encoding: ProfileEncoding = ProfileEncoding.Text) -> QgsField:
        """
        Creates a QgsField that can store spectral profiles
        :param name: field name
        :param comment: field comment, optional
        :param encoding: ProfileEncoding, e.g. 'text' (default), 'bytes' or 'json'
        :return: QgsField
        """
        encoding = ProfileEncoding.fromInput(encoding)
        if encoding == ProfileEncoding.Bytes:
            field = QgsField(name=name, type=QMETATYPE_QBYTEARRAY, comment=comment)
        elif encoding == ProfileEncoding.Text:
            field = QgsField(name=name, type=QMETATYPE_QSTRING, len=-1, comment=comment)
        elif encoding == ProfileEncoding.Json:
            field = QgsField(name=name, type=QMETATYPE_QVARIANTMAP, typeName='JSON', comment=comment)

        setup = QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {})
        field.setEditorWidgetSetup(setup)
        return field

    @staticmethod
    def isProfileField(field: QgsField) -> bool:
        return can_store_spectral_profiles(field) and field.editorWidgetSetup().type() == EDITOR_WIDGET_REGISTRY_KEY

    @staticmethod
    def activateProfileFields(layer: QgsVectorLayer, check: str = 'first_feature'):
        """
        Sets fields that can store spectral profiles and without a special editor widget to SpectralProfiles
        editor widget.
        Parameters
        ----------
        layer

        Returns
        -------
        :param check:

        """
        assert check in ['first_feature', 'field_type']
        candidates = [f for f in layer.fields() if can_store_spectral_profiles(f)]

        if check == 'field_type':
            for f in candidates:
                SpectralLibraryUtils.makeToProfileField(layer, f)
        elif check == 'first_feature':
            firstFeature = None
            for f in layer.getFeatures():
                firstFeature = f
                break
            if isinstance(firstFeature, QgsFeature):
                for f in candidates:

                    try:
                        dump = firstFeature.attribute(f.name())
                        profileDict = decodeProfileValueDict(dump)
                        if isinstance(profileDict, dict) and len(profileDict) > 0:
                            SpectralLibraryUtils.makeToProfileField(layer, f)
                    except Exception:
                        s = ""
                        pass

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
    def readProfileDict(layer: QgsRasterLayer,
                        point: Union[SpatialPoint, QgsPointXY],
                        store: Optional[QgsMapLayerStore] = None) -> Dict:
        """
        Reads a spectral profile dictionary from a QgsRasterLayer at position point
        """

        if isinstance(point, SpatialPoint):
            point = point.toCrs(layer.crs())

        scopes = QgsExpressionContextUtils.globalProjectLayerScopes(layer)
        context = QgsExpressionContext()
        context.appendScopes(scopes)

        context.setGeometry(QgsGeometry.fromPointXY(point))

        if Qgis.versionInt() >= 33000:
            if store is None:
                store = QgsMapLayerStore()
            context.setLoadedLayerStore(store)
        else:
            store = QgsProject.instance().layerStore()

        add_layer = store.mapLayer(layer.id()) != layer
        if add_layer:
            store.addMapLayer(layer)

        from ...qgsfunctions import RasterProfile
        exp = QgsExpression(f"{RasterProfile.NAME}('{layer.id()}', $geometry, encoding:='dict')")
        exp.prepare(context)

        assert exp.parserErrorString() == '', exp.parserErrorString()
        d = exp.evaluate(context)
        assert exp.evalErrorString() == '', exp.evalErrorString()
        if add_layer:
            store.takeMapLayer(layer)
        return d

    @staticmethod
    def attributeMap(feature: QgsFeature, numpy_arrays: bool = False) -> Dict:
        """
        Reads the feature attributes. SpectralProfile field content will be converted into Dict
        :param numpy_arrays: set True to return the x and y values as numpy arrays instead lists.
        :param feature:
        :return:
        """
        pfields = profile_field_names(feature)
        d = feature.attributeMap()
        for field in pfields:
            d[field] = decodeProfileValueDict(d[field], numpy_arrays=numpy_arrays)
        return d

    @staticmethod
    def setAttributeMap(feature: QgsFeature, attributes: Dict):
        """
        Sets the attribute values. Spectral profile dictionaries are transformed into the QgsFeature specific field types.
        :param feature: The QgsFeature to set values for
        :param attributes: value dictionary.
        :return:
        """
        pfields = profile_field_names(feature)
        for k, v in attributes.items():
            if k in pfields and isinstance(v, dict):
                v = encodeProfileValueDict(v, feature.fields()[k])
            feature.setAttribute(k, v)

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
            profile_fields: List[str] = [FIELD_VALUES],
            name: str = DEFAULT_NAME,
            encoding: ProfileEncoding = ProfileEncoding.Json,
            wkbType: QGIS_WKBTYPE = QGIS_WKBTYPE.Point,
            crs: QgsCoordinateReferenceSystem = None) -> QgsVectorLayer:
        """
        Creates an empty in-memory spectral library with a "name" and a "profiles" field
        """
        provider = 'memory'
        if not isinstance(wkbType, str):
            wkbType = QgsWkbTypes.displayString(wkbType)
        path = f"{wkbType}?crs=epsg:{SPECLIB_EPSG_CODE}"
        options = QgsVectorLayer.LayerOptions(loadDefaultStyle=True, readExtentFromXml=True)

        lyr = QgsVectorLayer(path, name, provider, options=options)
        if isinstance(crs, QgsCoordinateReferenceSystem):
            lyr.setCrs(crs)
        lyr.setCustomProperty('skipMemoryLayerCheck', 1)
        with edit(lyr):
            lyr.beginEditCommand('Add fields')
            assert lyr.addAttribute(QgsField(name=FIELD_NAME, type=QMETATYPE_QSTRING))

            for fieldname in profile_fields:
                if isinstance(fieldname, QgsField):
                    fieldname = fieldname.name()
                SpectralLibraryUtils.addAttribute(lyr, create_profile_field(fieldname, encoding=encoding))
            lyr.endEditCommand()

            SpectralLibraryUtils.initTableConfig(lyr)
            lyr.setDisplayExpression(f'format(\'%1 %2\', $id, "{FIELD_NAME}")')

        return lyr

    @staticmethod
    def addAttribute(speclib: QgsVectorLayer, field: QgsField) -> bool:
        success = speclib.addAttribute(field)
        if success:
            i = speclib.fields().lookupField(field.name())
            if i > -1:
                speclib.setEditorWidgetSetup(i, field.editorWidgetSetup())
                speclib.updatedFields.emit()
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
    def removeProfileField(layer: QgsVectorLayer, field: Union[int, str, QgsField]) -> bool:
        assert isinstance(layer, QgsVectorLayer)
        field = qgsField(layer, field)

        if field.editorWidgetSetup().type() == EDITOR_WIDGET_REGISTRY_KEY:
            i = layer.fields().lookupField(field.name())
            layer.setEditorWidgetSetup(i, QgsEditorWidgetSetup('', {}))
            layer.updatedFields.emit()
        return not is_profile_field(layer.fields()[field.name()])

    @staticmethod
    def makeToProfileField(layer: QgsVectorLayer, field: Union[int, str, QgsField]) -> bool:
        """
        Changes the QgsEditorWidgetSetup to make a QgsField a SpectralProfile field
        Parameters
        ----------
        field

        Returns: True if successful. False if field type cannot be used to store spectral profiles.
        -------
        """
        assert isinstance(layer, QgsVectorLayer)
        field = qgsField(layer, field)
        if not can_store_spectral_profiles(field):
            return False
        i = layer.fields().lookupField(field.name())
        layer.setEditorWidgetSetup(i, QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {}))

        # inform that the field has been changed. see https://github.com/qgis/QGIS/issues/55873
        layer.updatedFields.emit()
        return SpectralLibraryUtils.isProfileField(layer.fields().at(i))

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
    def addSpectralProfileField(speclib: QgsVectorLayer,
                                name: str, comment: str = None,
                                encoding: ProfileEncoding = ProfileEncoding.Text) -> bool:
        return speclib.addAttribute(create_profile_field(name, comment, encoding=encoding))

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

        # speclib.commitChanges(False)

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
            if new_edit_command:
                speclib.endEditCommand()
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
    def setProfileValues(feature: QgsFeature, *args,
                         profileDict: dict = None,
                         field: Union[int, str, QgsField] = None,
                         **kwds):
        if field is None:
            # use the first profile field by default
            field = profile_field_list(feature)[0]
        else:
            field: QgsField = qgsField(feature, field)

        if profileDict is None:
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
    def countProfiles(speclib: QgsVectorLayer) -> Dict[str, int]:
        COUNTS = dict()
        for field in profile_field_list(speclib):
            requests = QgsFeatureRequest()
            requests.setFilterExpression(f'"{field.name()}" is not NULL')
            n = len(list(speclib.getFeatures(requests)))

            COUNTS[field.name()] = n
        return COUNTS

    @staticmethod
    def plot(speclib: QgsVectorLayer) -> QWidget:
        assert is_spectral_library(speclib)
        app = None
        if not isinstance(QgsApplication.instance(), QgsApplication):
            from qgis.testing import start_app
            app = start_app()

        from ..gui.spectrallibrarywidget import SpectralLibraryWidget

        w = SpectralLibraryWidget(speclib=speclib)
        w.show()

        if app:
            app.exec_()

        return w

    @staticmethod
    def copyEditorWidgetSetup(speclib: QgsVectorLayer, fields):
        """
        Copies the editor widget setup from another vector layer or list of QgsField
        :param speclib: QgsVectorLayer
        :param fields: QgsFields, QgsVectorLayer, QgsFeature or list of QgsField
        """
        copyEditorWidgetSetup(speclib, fields)


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
