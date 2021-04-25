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
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""

# see http://python-future.org/str_literals.html for str issue discussion
import json
import enum
import pickle
import typing
import pathlib
import itertools
import os
import datetime
import re
import sys
import copy
import weakref
import warnings
import collections
from osgeo import gdal, ogr, osr, gdal_array
import uuid
import numpy as np
from qgis.PyQt.QtCore import Qt, QVariant, QPoint, QUrl, QMimeData, \
    QFileInfo, pyqtSignal, QByteArray
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QWidget, QFileDialog, QDialog

from qgis.core import QgsApplication, \
    QgsRenderContext, QgsFeature, QgsVectorLayer, QgsMapLayer, QgsRasterLayer, \
    QgsAttributeTableConfig, QgsField, QgsFields, QgsCoordinateReferenceSystem, QgsCoordinateTransform, \
    QgsActionManager, QgsFeatureIterator, QgsFeatureRequest, \
    QgsGeometry, QgsPointXY, QgsPoint, QgsDefaultValue, QgsReadWriteContext, \
    QgsCategorizedSymbolRenderer, QgsMapLayerProxyModel, \
    QgsSymbol, QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol, \
    QgsEditorWidgetSetup, QgsAction, QgsTask, QgsMessageLog, QgsFileUtils, \
    QgsProcessingFeedback

from qgis.gui import \
    QgsGui


from ...utils import SelectMapLayersDialog, geo2px, gdalDataset, \
    createQgsField, px2geocoordinates, qgsVectorLayer, qgsRasterLayer, findMapLayer, \
    fid2pixelindices, parseWavelength, parseBadBandList, optimize_block_size, \
    qgsField, qgsFieldAttributes2List, qgsFields2str, str2QgsFields
from ...plotstyling.plotstyling import PlotStyle
from .. import speclibSettings, EDITOR_WIDGET_REGISTRY_KEY
from .spectralprofile import SpectralProfileKey, SpectralProfile, SpectralProfileBlock, \
    SpectralSetting, groupBySpectralProperties
from .. import SpectralLibrarySettingsKey, SPECLIB_EPSG_CODE, FIELD_NAME, FIELD_FID, FIELD_VALUES

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


def generateProfileKeys(feature_ids: typing.List[int],
                        value_fields: typing.Union[QgsField, str]) -> typing.List[SpectralProfileKey]:
    field_names = []
    for f in value_fields:
        if isinstance(f, QgsField):
            f = f.name()
        assert isinstance(f, str)
        field_names.append(f)

    return [SpectralProfileKey(fid, field_name) for fid, field_name in itertools.product(feature_ids, field_names)]


class SerializationMode(enum.Enum):
    JSON = 1
    PICKLE = 2


def read_profiles(vectorlayer: QgsVectorLayer,
                  fids: typing.List[int] = None,
                  value_fields: typing.List[str] = None,
                  profile_keys: typing.List[SpectralProfileKey] = None) -> typing.Generator[
    SpectralProfile, None, None]:
    """
    Reads SpectralProfiles from a vector layers BLOB 'value_fields'.

    Like features(keys_to_remove=None), but converts each returned QgsFeature into a SpectralProfile.
    If multiple value fields are set, profiles are returned ordered by (i) fid and (ii) value field.
    SpectralProfiles are returned for value_fields != NULL only
    :param vectorlayer:
    :param value_fields:
    :type value_fields:
    :param profile_keys:
    :type profile_keys:
    :param fids: optional, [int-list-of-feature-ids] to return
    :return: generator of [List-of-SpectralProfiles]
    """

    if profile_keys is None:
        if value_fields is None:
            value_fields = [f.name() for f in spectralValueFields(vectorlayer)]
        if fids is None:
            fids = vectorlayer.allFeatureIds()

        elif not isinstance(value_fields, list):
            value_fields = [value_fields]

        profile_keys = [SpectralProfileKey(fid, n) for fid, n in itertools.product(fids, value_fields)]

    ID2KEY: typing.Dict[int, SpectralProfileKey] = dict()
    for k in profile_keys:
        if not isinstance(k, SpectralProfileKey):
            s = ""
        fields = ID2KEY.get(k.fid, [])
        fields.append(k.field)
        ID2KEY[k.fid] = fields

    featureRequest = QgsFeatureRequest()
    featureRequest.setFilterFids(sorted(ID2KEY.keys()))
    # features = list(vectorlayer.getFeatures(featureRequest))
    for f in vectorlayer.getFeatures(featureRequest):
        if not isinstance(f, QgsFeature):
            s = ""
        for field in ID2KEY[f.id()]:
            if isinstance(f.attribute(field), QByteArray):
                yield SpectralProfile.fromQgsFeature(f, value_field=field)



def log(msg: str):
    if DEBUG:
        QgsMessageLog.logMessage(msg, 'spectrallibraries.py')


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
    :param styleField: str, name of string field in layer.fields() to store the PlotStyle
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
                #:gdal.GDT_CInt16,
                # 8:gdal.GDT_CInt32,
                6: gdal.GDT_CFloat32,
                9: gdal.GDT_CFloat64}




def spectralValueFields(spectralLibrary: QgsVectorLayer) -> typing.List[QgsField]:
    """
    Returns the fields that contains values of SpectralProfiles
    :param spectralLibrary:
    :return:
    """
    fields = [f for f in spectralLibrary.fields() if
              f.type() == QVariant.ByteArray and
              f.editorWidgetSetup().type() == EDITOR_WIDGET_REGISTRY_KEY]

    return fields


def defaultCurvePlotStyle() -> PlotStyle:
    ps = PlotStyle()
    ps.setLineColor('white')
    ps.markerSymbol = None
    ps.linePen.setStyle(Qt.SolidLine)
    return ps


class SpectralProfileRenderer(object):

    @staticmethod
    def default():
        """
        Returns the default plotStyle scheme.
        :return:
        :rtype: SpectralProfileRenderer
        """
        return SpectralProfileRenderer.dark()

    @staticmethod
    def fromUserSettings():
        """
        Returns the SpectralProfileRenderer last saved in then library settings
        :return:
        :rtype:
        """
        settings = speclibSettings()

        scheme = SpectralProfileRenderer.default()

        if SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name in settings.allKeys():
            scheme.profileStyle = PlotStyle.fromJSON(
                settings.value(SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name))
        if SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name in settings.allKeys():
            scheme.temporaryProfileStyle = PlotStyle.fromJSON(
                settings.value(SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name))

        scheme.backgroundColor = settings.value(SpectralLibrarySettingsKey.BACKGROUND_COLOR.name,
                                                scheme.backgroundColor)
        scheme.foregroundColor = settings.value(SpectralLibrarySettingsKey.FOREGROUND_COLOR.name,
                                                scheme.foregroundColor)
        scheme.infoColor = settings.value(SpectralLibrarySettingsKey.INFO_COLOR.name, scheme.infoColor)
        scheme.selectionColor = settings.value(SpectralLibrarySettingsKey.SELECTION_COLOR.name, scheme.selectionColor)
        scheme.useRendererColors = settings.value(SpectralLibrarySettingsKey.USE_VECTOR_RENDER_COLORS.name,
                                                  scheme.useRendererColors) in ['True', 'true', True]

        return scheme

    @staticmethod
    def dark():
        ps = defaultCurvePlotStyle()
        ps.setLineColor('white')

        cs = defaultCurvePlotStyle()
        cs.setLineColor('green')

        return SpectralProfileRenderer(
            name='Dark',
            fg=QColor('white'),
            bg=QColor('black'),
            ic=QColor('white'),
            sc=QColor('yellow'),
            ps=ps, cs=cs, useRendererColors=False)

    @staticmethod
    def bright():
        ps = defaultCurvePlotStyle()
        ps.setLineColor('black')

        cs = defaultCurvePlotStyle()
        cs.setLineColor('green')

        return SpectralProfileRenderer(
            name='Bright',
            fg=QColor('black'),
            bg=QColor('white'),
            ic=QColor('black'),
            sc=QColor('red'),
            ps=ps, cs=cs, useRendererColors=False)

    def __init__(self,
                 name: str = 'color_scheme',
                 fg: QColor = QColor('white'),
                 bg: QColor = QColor('black'),
                 ps: PlotStyle = None,
                 cs: PlotStyle = None,
                 ic: QColor = QColor('white'),
                 sc: QColor = QColor('yellow'),
                 useRendererColors: bool = True):
        """
        :param name: name of color scheme
        :type name: str
        :param fg: foreground color
        :type fg: QColor
        :param bg: background color
        :type bg: QColor
        :param ps: default profile style
        :type ps: PlotStyle
        :param cs: current profile style, i.e. selected profiles
        :type cs: PlotStyle
        :param ic: info color, color of additional information, like crosshair and cursor location
        :type ic: QColor
        :param useRendererColors: if true (default), use colors from the QgsVectorRenderer to colorize plot lines
        :type useRendererColors: bool
        """

        if ps is None:
            ps = defaultCurvePlotStyle()

        if cs is None:
            cs = defaultCurvePlotStyle()
            cs.setLineColor('green')

        self.name: str = name
        self.foregroundColor: QColor = fg
        self.backgroundColor: QColor = bg
        self.profileStyle: PlotStyle = ps
        self.temporaryProfileStyle: PlotStyle = cs
        self.infoColor: QColor = ic
        self.selectionColor: QColor = sc
        self.useRendererColors: bool = useRendererColors

        self.mProfileKey2Style: typing.Dict[SpectralProfileKey, PlotStyle] = dict()
        self.mTemporaryKeys: typing.Set[SpectralProfileKey] = set()
        self.mInputSource: QgsVectorLayer = None

    def reset(self):
        self.mProfileKey2Style.clear()

    @staticmethod
    def readXml(node: QDomElement, *args):
        """
        Reads the SpectralProfileRenderer from a QDomElement (XML node)
        :param self:
        :param node:
        :param args:
        :return:
        """
        from .spectrallibrary import XMLNODE_PROFILE_RENDERER
        if node.tagName() != XMLNODE_PROFILE_RENDERER:
            node = node.firstChildElement(XMLNODE_PROFILE_RENDERER)
        if node.isNull():
            return None

        default: SpectralProfileRenderer = SpectralProfileRenderer.default()

        renderer = SpectralProfileRenderer()
        renderer.backgroundColor = QColor(node.attribute('bg', renderer.backgroundColor.name()))
        renderer.foregroundColor = QColor(node.attribute('fg', renderer.foregroundColor.name()))
        renderer.selectionColor = QColor(node.attribute('sc', renderer.selectionColor.name()))
        renderer.infoColor = QColor(node.attribute('ic', renderer.infoColor.name()))
        renderer.useRendererColors = 'true' == node.attribute('use_symbolcolor',
                                                              str(renderer.useRendererColors)).lower()

        nodeName = node.firstChildElement('name')
        renderer.name = nodeName.firstChild().nodeValue()

        nodeDefaultStyle = node.firstChildElement('default_style')
        renderer.profileStyle = PlotStyle.readXml(nodeDefaultStyle)
        if not isinstance(renderer.profileStyle, PlotStyle):
            renderer.profileStyle = default.profileStyle

        customStyleNodes = node.firstChildElement('custom_styles').childNodes()
        for i in range(customStyleNodes.count()):
            customStyleNode = customStyleNodes.at(i)
            customStyle = PlotStyle.readXml(customStyleNode)
            if isinstance(customStyle, PlotStyle):
                fids = customStyleNode.firstChildElement('keys').firstChild().nodeValue().split(',')
                rxInt = re.compile(r'\d+[ ]*')
                fids = [int(f) for f in fids if rxInt.match(f)]
                renderer.setProfilePlotStyle(customStyle, fids)

        return renderer

    def setInput(self, vectorLayer: QgsVectorLayer):
        self.mInputSource = vectorLayer

    def writeXml(self, node: QDomElement, doc: QDomDocument) -> bool:
        """
        Writes the PlotStyle to a QDomNode
        :param node:
        :param doc:
        :return:
        """
        from .spectrallibrary import XMLNODE_PROFILE_RENDERER
        profileRendererNode = doc.createElement(XMLNODE_PROFILE_RENDERER)
        profileRendererNode.setAttribute('bg', self.backgroundColor.name())
        profileRendererNode.setAttribute('fg', self.foregroundColor.name())
        profileRendererNode.setAttribute('sc', self.selectionColor.name())
        profileRendererNode.setAttribute('ic', self.infoColor.name())
        profileRendererNode.setAttribute('use_symbolcolor', str(self.useRendererColors))

        nodeName = doc.createElement('name')
        nodeName.appendChild(doc.createTextNode(self.name))
        profileRendererNode.appendChild(nodeName)

        if isinstance(self.profileStyle, PlotStyle):
            nodeDefaultStyle = doc.createElement('default_style')
            self.profileStyle.writeXml(nodeDefaultStyle, doc)
            profileRendererNode.appendChild(nodeDefaultStyle)

        nodeCustomStyles = doc.createElement('custom_styles')

        customStyles = self.nonDefaultPlotStyles()
        for style in customStyles:
            fids = [k for k, s in self.mProfileKey2Style.items() if s == style]
            nodeStyle = doc.createElement('custom_style')
            style.writeXml(nodeStyle, doc)
            nodeFIDs = doc.createElement('keys')
            nodeFIDs.appendChild(doc.createTextNode(','.join([str(i) for i in fids])))
            nodeStyle.appendChild(nodeFIDs)
            nodeCustomStyles.appendChild(nodeStyle)
        profileRendererNode.appendChild(nodeCustomStyles)
        node.appendChild(profileRendererNode)

        return True

    def setTemporaryFIDs(self, fids):
        self.mTemporaryKeys.clear()
        self.mTemporaryKeys.update(fids)

    def setProfilePlotStyle(self, plotStyle, keys: typing.List[SpectralProfileKey]) -> typing.List[SpectralProfileKey]:
        if isinstance(keys, SpectralProfileKey):
            keys = [keys]
        changed_keys = [k for k in keys if self.mProfileKey2Style.get(k) != plotStyle]

        if isinstance(plotStyle, PlotStyle):
            for k in keys:
                self.mProfileKey2Style[k] = plotStyle
        else:
            # use default style
            for k in keys:
                if k in self.mProfileKey2Style.keys():
                    self.mProfileKey2Style.pop(k)

        return changed_keys

    def nonDefaultPlotStyles(self) -> typing.List[PlotStyle]:
        return list(set(self.mProfileKey2Style.values()))

    def profilePlotStyle(self, key: SpectralProfileKey, ignore_selection: bool = True) -> PlotStyle:
        d = self.profilePlotStyles([key], ignore_selection=ignore_selection)
        return d.get(key, None)

    def profilePlotStyles(self, keys: typing.List[SpectralProfileKey], ignore_selection: bool = False) -> \
            typing.Dict[SpectralProfileKey, PlotStyle]:

        profileStyles: typing.Dict[SpectralProfileKey, PlotStyle] = dict()

        if isinstance(self.mInputSource, QgsVectorLayer):
            selectedFIDs = self.mInputSource.selectedFeatureIds()
        else:
            selectedFIDs = []

        if self.useRendererColors and isinstance(self.mInputSource, QgsVectorLayer):

            fids = sorted(set([k.fid for k in keys]))
            feature_styles: typing.Dict[int, PlotStyle] = dict()

            renderContext = QgsRenderContext()
            renderContext.setExtent(self.mInputSource.extent())
            renderer = self.mInputSource.renderer().clone()
            # renderer.setInput(self.mInputSource.dataSource())
            renderer.startRender(renderContext, self.mInputSource.fields())
            features = self.mInputSource.getFeatures(fids)
            for i, feature in enumerate(features):
                fid = feature.id()
                style = self.mProfileKey2Style.get(fid, self.profileStyle).clone()
                symbol = renderer.symbolForFeature(feature, renderContext)
                if not isinstance(symbol, QgsSymbol):
                    if not ignore_selection and fid in selectedFIDs:
                        pass
                    else:
                        style.setVisibility(False)
                    # symbol = renderer.sourceSymbol()
                elif isinstance(symbol, (QgsMarkerSymbol, QgsLineSymbol, QgsFillSymbol)):
                    color: QColor = symbol.color()
                    color.setAlpha(int(symbol.opacity() * 100))

                    style.setLineColor(color)
                    style.setMarkerColor(color)
                feature_styles[fid] = style
            renderer.stopRender(renderContext)
            for k in keys:
                profileStyles[k] = feature_styles.get(k.fid)
        else:
            for k in keys:
                profileStyles[k] = self.mProfileKey2Style.get(k, self.profileStyle).clone()

        line_increase_selected = 2
        line_increase_temp = 3

        # highlight selected features
        if not ignore_selection:

            for fid, style in profileStyles.items():
                if fid in selectedFIDs:
                    style.setLineColor(self.selectionColor)
                    style.setMarkerColor(self.selectionColor)
                    style.markerBrush.setColor(self.selectionColor)
                    style.markerSize += line_increase_selected
                    style.linePen.setWidth(style.linePen.width() + line_increase_selected)
                elif fid in self.mTemporaryKeys:
                    style.markerSize += line_increase_selected
                    style.linePen.setWidth(style.linePen.width() + line_increase_selected)

        return profileStyles

    def clone(self):
        # todo: avoid refs
        renderer = copy.copy(self)
        return renderer

    def saveToUserSettings(self):
        """
        Saves this plotStyle scheme to the user Qt user settings
        :return:
        :rtype:
        """
        settings = speclibSettings()

        settings.setValue(SpectralLibrarySettingsKey.DEFAULT_PROFILE_STYLE.name, self.profileStyle.json())
        settings.setValue(SpectralLibrarySettingsKey.CURRENT_PROFILE_STYLE.name, self.temporaryProfileStyle.json())
        settings.setValue(SpectralLibrarySettingsKey.BACKGROUND_COLOR.name, self.backgroundColor)
        settings.setValue(SpectralLibrarySettingsKey.FOREGROUND_COLOR.name, self.foregroundColor)
        settings.setValue(SpectralLibrarySettingsKey.INFO_COLOR.name, self.infoColor)
        settings.setValue(SpectralLibrarySettingsKey.SELECTION_COLOR.name, self.selectionColor)
        settings.setValue(SpectralLibrarySettingsKey.USE_VECTOR_RENDER_COLORS.name, self.useRendererColors)

    def printDifferences(self, renderer):
        assert isinstance(renderer, SpectralProfileRenderer)
        keys = [k for k in self.__dict__.keys()
                if not k.startswith('_') and
                k not in ['name', 'mInputSource']]

        differences = []
        for k in keys:
            if self.__dict__[k] != renderer.__dict__[k]:
                differences.append(f'{k}: {self.__dict__[k]} != {renderer.__dict__[k]}')
        if len(differences) == 0:
            print(f'# no differences')
        else:
            print(f'# {len(differences)} differences:')
            for d in differences:
                print(d)
        return True

    def __eq__(self, other):
        if not isinstance(other, SpectralProfileRenderer):
            return False
        else:
            keys = [k for k in self.__dict__.keys()
                    if not k.startswith('_') and
                    k not in ['name', 'mInputSource']]

            for k in keys:
                if self.__dict__[k] != other.__dict__[k]:
                    return False
            return True


class SpectralLibrary(QgsVectorLayer):
    """
    SpectralLibrary
    """

    @staticmethod
    def readFromMimeData(mimeData: QMimeData):
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
            if isinstance(sl, SpectralLibrary) and id(sl) == sid:
                return sl

        if MIMEDATA_SPECLIB in mimeData.formats():
            sl = SpectralLibrary.readFromPickleDump(mimeData.data(MIMEDATA_SPECLIB))
            if isinstance(sl, SpectralLibrary) and len(sl) > 0:
                return sl

        if mimeData.hasUrls():
            urls = mimeData.urls()
            if isinstance(urls, list) and len(urls) > 0:
                sl = SpectralLibrary.readFrom(urls[0])
                if isinstance(sl, SpectralLibrary) and len(sl) > 0:
                    return sl

        if MIMEDATA_TEXT in mimeData.formats():
            txt = mimeData.text()
            from ..io.csvdata import CSVSpectralLibraryIO
            sl = CSVSpectralLibraryIO.fromString(txt)
            if isinstance(sl, SpectralLibrary) and len(sl) > 0:
                return sl

        return None

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
            if isinstance(sl, SpectralLibrary):
                speclib.addProfiles(sl)
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
                       block_size: typing.Tuple[int, int] = None,
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
                f'invalid field name "{name_field}". Allowed values are {", ".join(vector.fields().names())}'
        else:
            for i in range(vector.fields().count()):
                field: QgsField = vector.fields().at(i)
                if field.type() == QVariant.String and re.search('name', field.name(), re.I):
                    name_field = field.name()
                    break

        ds: gdal.Dataset = gdalDataset(raster)
        assert isinstance(ds, gdal.Dataset), f'Unable to open {raster.source()} as gdal.Dataset'

        if progress_handler:
            progress_handler.setLabelText('Calculate profile positions...')

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

        if progress_handler:
            progress_handler.setRange(0, nBlocksTotal + 1)

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
            progress_handler.setLabelText('Read profile values..')
            progress_handler.setValue(progress_handler.value() + 1)

        PROFILE_COUNTS = dict()

        FEATURES: typing.Dict[int, QgsFeature] = dict()

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

                        for i in range(n_p):
                            # create profile feature
                            sp = SpectralProfile(fields=spectral_library.fields())

                            # create geometry
                            sp.setGeometry(QgsPoint(profile_geo_x[i],
                                                    profile_geo_y[i]))

                            PROFILE_COUNTS[fid] = PROFILE_COUNTS.get(fid, 0) + 1
                            # sp.setName(f'{fid_basename}_{PROFILE_COUNTS[fid]}')
                            sp.setValues(x=wl,
                                         y=fid_profiles[:, i],
                                         xUnit=wlu,
                                         bbl=bbl)
                            if vectorFeature.isValid():
                                for field_name in fields_to_copy:
                                    sp[field_name] = vectorFeature[field_name]
                            if copy_pixel_positions:
                                sp['px_x'] = int(profile_px_x[i])
                                sp['px_y'] = int(profile_px_y[i])
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

    def reloadSpectralValues(self, raster, selectedOnly: bool = True,
                             destination: typing.Union[QgsField, int, str]=None):
        """
        Reloads the spectral values for each point based on the spectral values found in raster image "raster"
        :param raster: str | QgsRasterLayer | gdal.Dataset
        :param selectedOnly: bool, if True (default) spectral values will be retireved for selected features only.
        """
        assert self.isEditable()
        if destination is None:
            destination = self.spectralValueFields()[0]
        else:
            destination = qgsField(self, destination)

        assert isinstance(destination, QgsField)
        assert destination in self.spectralValueFields()

        source = gdalDataset(raster)
        assert isinstance(source, gdal.Dataset)
        gt = source.GetGeoTransform()
        crs = QgsCoordinateReferenceSystem(source.GetProjection())

        geoPositions = []
        fids = []

        features = self.selectedFeatures() if selectedOnly else self.features()
        for f in features:
            assert isinstance(f, QgsFeature)
            if f.hasGeometry():
                fids.append(f.id())
                geoPositions.append(QgsPointXY(f.geometry().get()))
        if len(fids) == 0:
            return

        # transform feature coordinates into the raster data set's CRS
        if crs != self.crs():
            trans = QgsCoordinateTransform()
            trans.setSourceCrs(self.crs())
            trans.setDestinationCrs(crs)
            geoPositions = [trans.transform(p) for p in geoPositions]

        # transform coordinates into pixel positions
        pxPositions = [geo2px(p, gt) for p in geoPositions]

        idxSPECLIB = self.fields().indexOf(destination.name())
        idxPROFILE = None

        for fid, pxPosition in zip(fids, pxPositions):
            assert isinstance(pxPosition, QPoint)
            profile = SpectralProfile.fromRasterSource(source, pxPosition, crs=crs, gt=gt)
            if isinstance(profile, SpectralProfile):
                if idxPROFILE is None:
                    idxPROFILE = profile.fields().indexOf(FIELD_VALUES)
                assert self.changeAttributeValue(fid, idxSPECLIB, profile.attribute(idxPROFILE))

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
            progressDialog.setMinimum(0)
            progressDialog.setMaximum(nTotal)
            progressDialog.setValue(0)
            progressDialog.setLabelText('Extract pixel profiles...')

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

                    # see https://enmap-box.readthedocs.io/en/latest/usr_section/usr_manual/processing_datatypes.html#labelled-spectral-library
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

    def copyEditorWidgetSetup(self, fields: typing.Union[QgsVectorLayer, typing.List[QgsField]]):
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
            idx = self.fields().indexOf(fSrc.name())

            if idx == -1:
                # field name does not exist
                continue
            fDst = self.fields().at(idx)
            assert isinstance(fDst, QgsField)

            setup = fSrc.editorWidgetSetup()
            if QgsGui.instance().editorWidgetRegistry().factory(setup.type()).supportsField(self, idx):
                self.setEditorWidgetSetup(idx, setup)

    @staticmethod
    def readFrom(uri, progressDialog: QgsProcessingFeedback = None):
        """
        Reads a Spectral Library from the source specified in "uri" (path, url, ...)
        :param uri: path or uri of the source from which to read SpectralProfiles and return them in a SpectralLibrary
        :return: SpectralLibrary
        """
        if isinstance(uri, QUrl):
            if uri.isLocalFile():
                uri = uri.toLocalFile()
            else:
                uri.toString()

        if isinstance(uri, str) and uri.endswith('.gpkg'):
            try:
                return SpectralLibrary(path=uri)
            except Exception as ex:
                print(ex)
                return None

        if isinstance(uri, str) and uri.endswith('.sli'):
            from ..io.envi import EnviSpectralLibraryIO
            if EnviSpectralLibraryIO.canRead(uri):
                sl = EnviSpectralLibraryIO.readFrom(uri, progressDialog=progressDialog)
                if isinstance(sl, SpectralLibrary):
                    if sl.name() in [DEFAULT_NAME, '']:
                        sl.setName(os.path.basename(uri))
                    return sl

        from .spectrallibraryio import AbstractSpectralLibraryIO
        readers = AbstractSpectralLibraryIO.subClasses()

        for cls in sorted(readers, key=lambda r: r.score(uri), reverse=True):
            try:
                if cls.canRead(uri):
                    sl = cls.readFrom(uri, progressDialog=progressDialog)
                    if isinstance(sl, SpectralLibrary):
                        if sl.name() in [DEFAULT_NAME, '']:
                            sl.setName(os.path.basename(uri))
                        return sl
            except Exception as ex:
                s = ""
        return None

    @classmethod
    def instances(cls) -> list:
        warnings.warn('SpectraLibrary.instances() Will be removed', DeprecationWarning)
        return []

    sigProgressInfo = pyqtSignal(int, int, str)
    sigProfileRendererChanged = pyqtSignal(SpectralProfileRenderer)

    def __init__(self,
                 path: str = None,
                 baseName: str = DEFAULT_NAME,
                 options: QgsVectorLayer.LayerOptions = None,
                 profile_fields: typing.List[str] = [FIELD_VALUES],
                 create_name_field: bool = True):

        if isinstance(path, pathlib.Path):
            path = path.as_posix()

        if not isinstance(options, QgsVectorLayer.LayerOptions):
            options = QgsVectorLayer.LayerOptions(loadDefaultStyle=True, readExtentFromXml=True)

        create_new_speclib = path is None
        if create_new_speclib:
            # create a new, empty in-memory GPKG backend
            existing_vsi_files = vsiSpeclibs()
            assert isinstance(existing_vsi_files, list)
            while True:
                path = pathlib.PurePosixPath(VSI_DIR) / f'{baseName}.{uuid.uuid4()}.gpkg'
                path = path.as_posix().replace('\\', '/')
                if not path in existing_vsi_files:
                    break

            drv = ogr.GetDriverByName('GPKG')
            missingGPKGInfo = \
                "Your GDAL/OGR installation does not support the GeoPackage (GPKG) vector driver " + \
                "(https://gdal.org/drivers/vector/gpkg.html).\n" + \
                "Linux users might need to install libsqlite3."
            assert isinstance(drv, ogr.Driver), missingGPKGInfo

            co = ['VERSION=AUTO']
            dsSrc = drv.CreateDataSource(path, options=co)
            assert isinstance(dsSrc, ogr.DataSource)
            srs = osr.SpatialReference()
            srs.ImportFromEPSG(SPECLIB_EPSG_CODE)
            co = ['GEOMETRY_NAME=geom',
                  'GEOMETRY_NULLABLE=YES',
                  # 'FID=fid'
                  ]

            lyr = dsSrc.CreateLayer(baseName, srs=srs, geom_type=ogr.wkbPoint, options=co)
            try:
                dsSrc.FlushCache()
            except RuntimeError as rt:
                if 'failed: no such module: rtree' in str(rt):
                    pass
                else:
                    raise rt

        assert isinstance(path, str)
        super(SpectralLibrary, self).__init__(path, baseName, 'ogr', options)

        if create_new_speclib:
            self.startEditing()
            # add profile fields
            names = self.fields().names()
            for fieldname in profile_fields:
                self.addAttribute(QgsField(fieldname, QVariant.ByteArray, 'Binary'))

            # add a single name field (more is not required)
            if create_name_field:
                self.addAttribute(QgsField('name', QVariant.String, 'varchar'))
            self.commitChanges(stopEditing=True)

        # set binary array fields as spectral profile columns
        for field in self.fields():
            field: QgsField
            if field.type() == QVariant.ByteArray:
                self.setEditorWidgetSetup(self.fields().lookupField(field.name()),
                                          QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {}))

        # self.beforeCommitChanges.connect(self.onBeforeCommitChanges)

        self.committedFeaturesAdded.connect(self.onCommittedFeaturesAdded)
        self.mProfileRenderer: SpectralProfileRenderer = SpectralProfileRenderer()
        self.mProfileRenderer.setInput(self)


        self.attributeAdded.connect(self.onAttributeAdded)
        self.attributeDeleted.connect(self.onFieldsChanged)

        self.initTableConfig()
        self.initProfileRenderer()

    def onAttributeAdded(self, idx: int):

        field: QgsField = self.fields().at(idx)
        if field.type() == QVariant.ByteArray:
            # let new ByteArray fields be SpectralProfile columns by default
            self.setEditorWidgetSetup(idx, QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {}))

    def onFieldsChanged(self):
        pass
        # self.mSpectralValueFields = spectralValueFields(self)

    def onCommittedFeaturesAdded(self, id, features):

        if id != self.id():
            return

        newFIDs = [f.id() for f in features]
        # see qgsvectorlayereditbuffer.cpp
        oldFIDs = list(reversed(list(self.editBuffer().addedFeatures().keys())))
        mFID2Style = self.profileRenderer().mProfileKey2Style
        updates = dict()
        for fidOld, fidNew in zip(oldFIDs, newFIDs):
            if fidOld in mFID2Style.keys():
                updates[fidNew] = mFID2Style.pop(fidOld)
        mFID2Style.update(updates)

    def setEditorWidgetSetup(self, index: int, setup: QgsEditorWidgetSetup):
        super().setEditorWidgetSetup(index, setup)
        self.onFieldsChanged()

    def setProfileRenderer(self, profileRenderer: SpectralProfileRenderer):
        assert isinstance(profileRenderer, SpectralProfileRenderer)
        b = profileRenderer != self.mProfileRenderer
        self.mProfileRenderer = profileRenderer
        if profileRenderer.mInputSource != self:
            s = ""
        if b:
            self.sigProfileRendererChanged.emit(self.mProfileRenderer)

    def profileRenderer(self) -> SpectralProfileRenderer:
        return self.mProfileRenderer

    def initProfileRenderer(self):
        """
        Initializes the default QgsFeatureRenderer
        """
        # color = speclibSettings().value('DEFAULT_PROFILE_COLOR', QColor('green'))
        # self.renderer().symbol().setColor(color)

        uri = self.source()
        uri = os.path.splitext(uri)[0] + '.qml'

        self.mProfileRenderer = SpectralProfileRenderer.default()
        self.mProfileRenderer.setInput(self)

        self.loadNamedStyle(uri)

    def initTableConfig(self):
        """
        Initializes the QgsAttributeTableConfig and further options
        """
        mgr = self.actions()
        assert isinstance(mgr, QgsActionManager)
        mgr.clearActions()

        # actionSetStyle = createSetPlotStyleAction(self.fields().at(self.fields().lookupField(FIELD_STYLE)))
        # assert isinstance(actionSetStyle, QgsAction)
        # mgr.addAction(actionSetStyle)

        actionRemoveSpectrum = createRemoveFeatureAction()
        assert isinstance(actionRemoveSpectrum, QgsAction)
        mgr.addAction(actionRemoveSpectrum)

        columns = self.attributeTableConfig().columns()
        visibleColumns = ['name']
        for column in columns:
            assert isinstance(column, QgsAttributeTableConfig.ColumnConfig)

            column.hidden = column.name not in visibleColumns and column.type != QgsAttributeTableConfig.Action

        # set column order
        c_action = [c for c in columns if c.type == QgsAttributeTableConfig.Action][0]
        c_name = [c for c in columns if c.name == FIELD_NAME][0]
        firstCols = [c_action, c_name]
        columns = [c_action, c_name] + [c for c in columns if c not in firstCols]

        conf = QgsAttributeTableConfig()
        conf.setColumns(columns)
        conf.setActionWidgetVisible(False)
        conf.setActionWidgetStyle(QgsAttributeTableConfig.ButtonList)

        self.setAttributeTableConfig(conf)

    def mimeData(self, formats: list = None) -> QMimeData:
        """
        Wraps this Speclib into a QMimeData object
        :return: QMimeData
        """
        if isinstance(formats, str):
            formats = [formats]
        elif formats is None:
            formats = [MIMEDATA_SPECLIB_LINK]

        mimeData = QMimeData()

        for format in formats:
            assert format in [MIMEDATA_SPECLIB_LINK, MIMEDATA_SPECLIB, MIMEDATA_TEXT, MIMEDATA_URL]
            if format == MIMEDATA_SPECLIB_LINK:
                global SPECLIB_CLIPBOARD
                thisID = id(self)
                SPECLIB_CLIPBOARD[thisID] = self

                mimeData.setData(MIMEDATA_SPECLIB_LINK, pickle.dumps(thisID))
            elif format == MIMEDATA_SPECLIB:
                mimeData.setData(MIMEDATA_SPECLIB, pickle.dumps(self))
            elif format == MIMEDATA_URL:
                mimeData.setUrls([QUrl(self.source())])
            elif format == MIMEDATA_TEXT:
                from ..io.csvdata import CSVSpectralLibraryIO
                txt = CSVSpectralLibraryIO.asString(self)
                mimeData.setText(txt)

        return mimeData

    def optionalFieldNames(self) -> list:
        """
        Returns the names of additions fields / attributes
        :return: [list-of-str]
        """
        warnings.warn('Deprecated and desimplemented', DeprecationWarning)
        # requiredFields = [f.name for f in ogrStandardFields()]
        return []

    def addSpectralProfileAttribute(self, name: str, comment: str = None) -> bool:

        field = QgsField(name, QVariant.ByteArray, 'Binary', comment=comment)
        b = self.addAttribute(field)
        if b:
            self.setEditorWidgetSetup(self.fields().lookupField(field.name()),
                                      QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {}))
        return b

    def addMissingFields(self, fields: QgsFields, copyEditorWidgetSetup: bool = True):
        """
        :param fields: list of QgsFields
        :param copyEditorWidgetSetup: if True (default), the editor widget setup is copied for each field
        """
        missingFields = []
        for field in fields:
            assert isinstance(field, QgsField)
            i = self.fields().lookupField(field.name())
            if i == -1:
                missingFields.append(field)

        if len(missingFields) > 0:
            for fOld in missingFields:
                self.addAttribute(QgsField(fOld))

            if copyEditorWidgetSetup:
                self.copyEditorWidgetSetup(missingFields)

    def addSpeclib(self, speclib,
                   addMissingFields: bool = True,
                   copyEditorWidgetSetup: bool = True,
                   progressDialog: QgsProcessingFeedback = None) -> typing.List[int]:
        """
        Adds profiles from another SpectraLibrary
        :param speclib: SpectralLibrary
        :param addMissingFields: if True (default), missing fields / attributes will be added automatically
        :param copyEditorWidgetSetup: if True (default), the editor widget setup will be copied for each added field
        :param progressDialog: QProgressDialog or qps.speclib.core.ProgressHandler

        :returns: set of added feature ids
        """
        assert isinstance(speclib, SpectralLibrary)

        fids_old = sorted(speclib.allFeatureIds(), key=lambda i: abs(i))
        fids_new = self.addProfiles(speclib,
                                    addMissingFields=addMissingFields,
                                    copyEditorWidgetSetup=copyEditorWidgetSetup,
                                    progressDialog=progressDialog)

        fid2Style = copy.deepcopy(speclib.profileRenderer().mProfileKey2Style)

        for fid_old, fid_new in [(fo, fn) for fo, fn in zip(fids_old, fids_new) if fo in fid2Style.keys()]:
            self.profileRenderer().mProfileKey2Style[fid_new] = fid2Style[fid_old]

        return fids_new

    def addProfiles(self,
                    profiles: typing.Union[typing.List[SpectralProfile], QgsVectorLayer],
                    addMissingFields: bool = None, \
                    copyEditorWidgetSetup: bool = True, \
                    progressDialog: QgsProcessingFeedback = None,
                    feedback: QgsProcessingFeedback = None) -> typing.List[int]:

        # todo: allow to add profiles with distinct key
        if isinstance(profiles, SpectralProfile):
            profiles = [profiles]

        if addMissingFields is None:
            addMissingFields = isinstance(profiles, SpectralLibrary)

        nTotal = len(profiles)
        if nTotal == 0:
            return

        assert self.isEditable(), 'SpectralLibrary "{}" is not editable. call startEditing() first'.format(self.name())

        keysBefore = set(self.editBuffer().addedFeatures().keys())

        lastTime = datetime.datetime.now()
        dt = datetime.timedelta(seconds=2)

        if isinstance(feedback, QgsProcessingFeedback):
            feedback.setProgressText('Add {} profiles'.format(len(profiles)))
            feedback.setProgress(0)

        iSrcList = []
        iDstList = []

        bufferLength = 1000
        profileBuffer = []

        nAdded = 0

        def flushBuffer(triggerProgressBar: bool = False):
            nonlocal self, nAdded, profileBuffer, feedback, lastTime, dt
            if not self.addFeatures(profileBuffer):
                self.raiseError()
            nAdded += len(profileBuffer)
            profileBuffer.clear()

            if isinstance(feedback, QgsProcessingFeedback):
                # update progressbar in intervals of dt
                if triggerProgressBar or (lastTime + dt) < datetime.datetime.now():
                    feedback.setProgress(nAdded)
                    lastTime = datetime.datetime.now()

        new_edit_command: bool = not self.isEditCommandActive()
        if new_edit_command:
            self.beginEditCommand('Add profiles')

        for i, pSrc in enumerate(profiles):
            if i == 0:
                if addMissingFields:
                    self.addMissingFields(pSrc.fields(), copyEditorWidgetSetup=copyEditorWidgetSetup)

                for iSrc, srcName in enumerate(pSrc.fields().names()):
                    if srcName == FIELD_FID:
                        continue
                    iDst = self.fields().lookupField(srcName)
                    if iDst >= 0:
                        iSrcList.append(iSrc)
                        iDstList.append(iDst)
                    elif addMissingFields:
                        raise Exception('Missing field: "{}"'.format(srcName))

            # create new feature + copy geometry
            pDst = QgsFeature(self.fields())
            pDst.setGeometry(pSrc.geometry())

            # copy attributes
            for iSrc, iDst in zip(iSrcList, iDstList):
                pDst.setAttribute(iDst, pSrc.attribute(iSrc))

            profileBuffer.append(pDst)

            if len(profileBuffer) >= bufferLength:
                flushBuffer()

        # final buffer call
        flushBuffer(triggerProgressBar=True)

        if new_edit_command:
            self.endEditCommand()

        # return the edited features
        MAP = self.editBuffer().addedFeatures()
        fids_inserted = [MAP[k].id() for k in reversed(list(MAP.keys())) if k not in keysBefore]
        return fids_inserted

    def speclibFromFeatureIDs(self, fids):
        if isinstance(fids, int):
            fids = [fids]
        assert isinstance(fids, list)

        profiles = list(self.profiles(fids))

        speclib = SpectralLibrary()
        speclib.startEditing()
        speclib.addMissingFields(self.fields())
        speclib.addProfiles(profiles)
        speclib.commitChanges()
        return speclib

    def removeProfiles(self, profiles):
        """
        Removes profiles from this ProfileSet
        :param profiles: Profile or [list-of-profiles] to be removed
        :return: [list-of-remove profiles] (only profiles that existed in this set before)
        """
        if not isinstance(profiles, list):
            profiles = [profiles]

        for p in profiles:
            assert isinstance(p, SpectralProfile)

        fids = [p.id() for p in profiles]
        if len(fids) == 0:
            return

        assert self.isEditable()
        self.deleteFeatures(fids)

    def features(self, fids=None) -> QgsFeatureIterator:
        """
        Returns the QgsFeatures stored in this QgsVectorLayer
        :param fids: optional, [int-list-of-feature-ids] to return
        :return: QgsFeatureIterator
        """
        featureRequest = QgsFeatureRequest()
        if fids is not None:
            if isinstance(fids, int):
                fids = [fids]
            if not isinstance(fids, list):
                fids = list(fids)
            for fid in fids:
                assert isinstance(fid, int)
            featureRequest.setFilterFids(fids)
        # features = [f for f in self.features() if f.id() in keys_to_remove]
        return self.getFeatures(featureRequest)

    def profileBlocks(self,
                      fids=None,
                      value_fields=None,
                      profile_keys=None,
                      ) -> typing.List[SpectralProfileBlock]:
        """
        Reads SpectralProfiles into profile blocks with different spectral settings
        :param blob:
        :return:
        """
        return SpectralProfileBlock.fromSpectralProfiles(
            self.profiles(fids=fids, value_fields=value_fields, profile_keys=profile_keys)
        )

    def profile(self, fid: int, value_field=None) -> SpectralProfile:
        if value_field is None:
            value_field = self.spectralValueFields()[0]
        return SpectralProfile.fromQgsFeature(self.getFeature(fid), value_field=value_field)

    def profiles(self,
                 fids=None,
                 value_fields=None,
                 profile_keys: typing.List[SpectralProfileKey] = None) -> typing.Generator[SpectralProfile, None, None]:
        """
        Like features(keys_to_remove=None), but converts each returned QgsFeature into a SpectralProfile.
        If multiple value fields are set, profiles are returned ordered by (i) fid and (ii) value field.
        :param value_fields:
        :type value_fields:
        :param profile_keys:
        :type profile_keys:
        :param fids: optional, [int-list-of-feature-ids] to return
        :return: generator of [List-of-SpectralProfiles]
        """

        return read_profiles(self, fids=fids, value_fields=value_fields, profile_keys=profile_keys)

    def groupBySpectralProperties(self,
                                  fids=None,
                                  value_fields=None,
                                  profile_keys=None,
                                  excludeEmptyProfiles: bool = True
                                  ) -> typing.Dict[SpectralSetting, typing.List[SpectralProfile]]:
        """
        Returns SpectralProfiles grouped by key = (xValues, xUnit and yUnit):

            xValues: None | [list-of-xvalues with n>0 elements]
            xUnit: None | str with len(str) > 0, e.g. a wavelength like 'nm'
            yUnit: None | str with len(str) > 0, e.g. 'reflectance' or '-'

        :return: {SpectralSetting:[list-of-profiles]}
        """
        return groupBySpectralProperties(self.profiles(
            fids=fids,
            value_fields=value_fields,
            profile_keys=profile_keys,
        ),
            excludeEmptyProfiles=excludeEmptyProfiles
        )

    def exportNamedStyle(self,
                         doc: QDomDocument,
                         context: QgsReadWriteContext,
                         categories: QgsMapLayer.StyleCategories
                         ) -> str:

        msg = super(SpectralLibrary, self).exportNamedStyle(doc, context=context, categories=categories)
        if msg == '':
            qgsNode = doc.documentElement().toElement()

            if isinstance(self.mProfileRenderer, SpectralProfileRenderer):
                self.mProfileRenderer.writeXml(qgsNode, doc)

        return msg

    def importNamedStyle(self, doc: QDomDocument,
                         categories: QgsMapLayer.StyleCategories = QgsMapLayer.AllStyleCategories):

        success, errorMsg = super(SpectralLibrary, self).importNamedStyle(doc, categories)
        if success:
            elem = doc.documentElement().firstChildElement(XMLNODE_PROFILE_RENDERER)
            if not elem.isNull():

                scheme = SpectralProfileRenderer.readXml(elem)
                if isinstance(scheme, SpectralProfileRenderer):
                    self.mProfileRenderer = scheme
                    self.mProfileRenderer.setInput(self)
        return success, errorMsg

    def exportProfiles(self, *args, **kwds) -> list:
        warnings.warn('Use SpectralLibrary.write() instead', DeprecationWarning)
        return self.write(*args, **kwds)

    def writeRasterImages(self, pathOne: typing.Union[str, pathlib.Path], drv: str = 'GTiff') -> typing.List[
        pathlib.Path]:
        """
        Writes the SpectralLibrary into images of same spectral properties
        :return: list of image paths
        """
        if not isinstance(pathOne, pathlib.Path):
            pathOne = pathlib.Path(pathOne)

        basename, ext = os.path.splitext(pathOne.name)

        assert pathOne.as_posix().startswith('/vsimem/') or pathOne.parent.is_dir(), f'Canot write to {pathOne}'
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

    def write(self, path: str, **kwds) -> typing.List[str]:
        """
        Exports profiles to a file.
        This wrapper tries to identify a fitting AbstractSpectralLibraryIO from the
        file extension in `path`.
        To ensure the way how the SpectralLibrary is written into file data, use
        a AbstractSpectralLibraryIO implementation of choice.
        :param path: str, filepath
        :param kwds: keywords to be used in specific `AbstractSpectralLibraryIO.write(...)` methods.
        :return: list of written files
        """

        if path is None:
            path, filter = QFileDialog.getSaveFileName(parent=kwds.get('parent'),
                                                       caption='Save Spectral Library',
                                                       directory=QgsFileUtils.stringToSafeFilename(
                                                           self.name() + '.gpkg'),
                                                       filter=FILTERS,
                                                       initialFilter='Geopackage (*.gpkg)')

        if isinstance(path, pathlib.Path):
            path = path.as_posix()

        if len(path) > 0:
            ext = os.path.splitext(path)[-1].lower()
            from ..io.csvdata import CSVSpectralLibraryIO
            from ..io.vectorsources import VectorSourceSpectralLibraryIO
            from ..io.envi import EnviSpectralLibraryIO

            # todo: implement filter strings in AbstractSpectralLibraryIOs to auto-match file extensions
            if ext in ['.sli', '.esl']:
                return EnviSpectralLibraryIO.write(self, path, **kwds)

            elif ext in ['.json', '.geojson', '.geojsonl', '.csv', '.gpkg']:
                return VectorSourceSpectralLibraryIO.write(self, path, **kwds)
            else:
                raise Exception(f'Filetype not supported: {path}')
        return []

    def spectralValueFields(self) -> typing.List[QgsField]:
        return spectralValueFields(self)

    def yRange(self) -> typing.List[float]:
        """
        Returns the maximum y range
        :return:
        :rtype:
        """

        minY = maxY = 0

        for p in self.profiles():
            yValues = p.yValues()
            minY = min(minY, min(yValues))
            maxY = max(maxY, max(yValues))

        return minY, maxY

    def __repr__(self):
        return str(self.__class__) + '"{}" {} feature(s)'.format(self.name(), self.dataProvider().featureCount())

    def plot(self) -> QWidget:
        """Create a plot widget and shows all SpectralProfile in this SpectralLibrary."""

        app = None
        if not isinstance(QgsApplication.instance(), QgsApplication):
            from ...testing import start_app
            app = start_app()

        from ..gui.spectrallibrarywidget import SpectralLibraryWidget

        w = SpectralLibraryWidget(speclib=self)
        w.show()

        if app:
            app.exec_()

        return w

    def fieldNames(self) -> list:
        """
        Returns the field names. Shortcut from self.fields().names()
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
        for feature in self.features():
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
        fieldNames = self.fieldNames()
        dataFields = str2QgsFields(fields)
        fieldsToAdd = [f for f in dataFields if f.name() not in fieldNames]
        self.startEditing()
        if len(fieldsToAdd) > 0:

            for field in fieldsToAdd:
                assert isinstance(field, QgsField)
                self.fields().append(field)
            self.commitChanges()
            self.startEditing()

        fieldNames = self.fieldNames()
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
            feature.setAttribute(FIELD_FID, nextFID)
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

    def __getitem__(self, slice) -> typing.Union[SpectralProfile, typing.List[SpectralProfile]]:
        fids = sorted(self.allFeatureIds())[slice]
        fields = self.spectralValueFields()
        if len(fields) > 0:
            value_field = fields[0].name()
            if isinstance(fids, list):
                return sorted(self.profiles(fids=fids), key=lambda p: p.id())
            else:
                return SpectralProfile.fromQgsFeature(self.getFeature(fids), value_field=value_field)

    def __delitem__(self, slice):
        profiles = self[slice]
        self.removeProfiles(profiles)

    def __eq__(self, other):
        if not isinstance(other, SpectralLibrary):
            return False

        if len(self) != len(other):
            return False

        for p1, p2 in zip(self.__iter__(), other.__iter__()):
            if not p1 == p2:
                return False
        return True

    def __hash__(self):
        # return super(SpectralLibrary, self).__hash__()
        return hash(self.id())


class ConsistencyRequirement(enum.IntFlag):
    HasWavelengths = 1,
    UnifiedWavelengths = 2,
    UnifiedWavelengthUnits = 4,
    AttributesNotNone = 8


class SpectralLibraryConsistencyCheckTask(QgsTask):

    def __init__(self, path_speclib: str, flags, fields=typing.List[str], callback=None):
        super().__init__('Check Speclib Consistency', QgsTask.CanCancel)
        assert isinstance(path_speclib, str)

        self.mPathSpeclib: str = path_speclib
        self.mFlags = flags
        self.mFields = fields
        self.mCallback = callback
        self.mTimeDeltaProgress = datetime.timedelta(seconds=1)

    def run(self):
        try:
            t0 = datetime.datetime.now()
            speclib = SpectralLibrary(path=self.mPathSpeclib)
            n = len(speclib)
            MISSING_FIELD_VALUE = dict()
            for i, profile in enumerate(speclib):
                # check this profile

                for f in self.mFields:
                    if profile.attribute(f) in ['', None]:
                        fids = MISSING_FIELD_VALUE.get(f, [])
                        fids.append(profile.id())
                        MISSING_FIELD_VALUE[f] = fids

                # report progress
                tn = datetime.datetime.now()
                if tn - t0 >= self.mTimeDeltaProgress:
                    self.progressChanged.emit(i / n * 100)

        except Exception as ex:
            self.exception = ex
            return False

        return True

    def finished(self, result):
        if self.mCallback:
            self.mCallback(result, self)


def consistencyCheck(speclib: SpectralLibrary, requirements, notNoneAttributes=[], progressDialog=None) -> typing.Dict[
    str, typing.List[int]]:
    problems: typing.Dict[str, typing.List[int]] = dict()

    bCheckWL = bool(requirements & ConsistencyRequirement.UnifiedWavelengths)
    bCheckHasWL = bool(requirements & ConsistencyRequirement.HasWavelengths)
    n = len(speclib)
    for i, profile in enumerate(speclib):
        fid = profile.id()

    return problems


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
