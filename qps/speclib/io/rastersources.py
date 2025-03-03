# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/io/rastersources.py


    ---------------------
    Beginning            : 2018-12-17
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
    along with this software. If not, see <https://www.gnu.org/licenses/>.
***************************************************************************
"""
import pathlib
import sys
from typing import Generator, List, Union

import numpy as np
from osgeo import gdal
from qgis.core import Qgis, QgsApplication, QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsExpression, \
    QgsExpressionContext, QgsExpressionContextUtils, QgsFeature, QgsFeatureRequest, QgsField, QgsFields, QgsGeometry, \
    QgsMapLayerProxyModel, QgsPointXY, QgsProcessingFeedback, QgsProject, QgsProviderRegistry, QgsRasterDataProvider, \
    QgsRasterLayer, QgsTask, QgsTaskManager, QgsVectorLayer, QgsWkbTypes
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt import sip
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QProgressBar,
                                 QTextEdit)

from .. import FIELD_NAME, FIELD_VALUES, speclibUiPath
from ..core import create_profile_field
from ..core.spectrallibrary import SpectralLibraryUtils
from ..core.spectrallibraryio import IMPORT_SETTINGS_KEY_REQUIRED_SOURCE_FIELDS, SpectralLibraryImportWidget, \
    SpectralLibraryIO
from ..core.spectralprofile import encodeProfileValueDict, prepareProfileValueDict
from ...models import Option, OptionListModel
from ...qgisenums import QGIS_GEOMETRYTYPE, QGIS_LAYERFILTER, QGIS_WKBTYPE, QMETATYPE_INT, QMETATYPE_QSTRING
from ...qgsfunctions import RasterProfile
from ...qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ...utils import gdalDataset, loadUi, noDataValues, parseBadBandList, parseFWHM, parseWavelength, \
    px2geocoordinatesV2, qgsRasterLayer, qgsVectorLayer, rasterArray, SelectMapLayersDialog

PIXEL_LIMIT = 100 * 100


class SpectralProfileLoadingTask(QgsTask):

    def __init__(self,
                 path_vector: str,
                 path_raster: str,
                 all_touched: bool = True,
                 copy_attributes: bool = False,
                 aggregate: str = 'mean'):

        super().__init__('Load spectral profiles', QgsTask.CanCancel)
        assert isinstance(path_vector, str)
        assert isinstance(path_raster, str)

        self.path_vector = path_vector
        self.path_raster = path_raster
        self.all_touched = all_touched
        self.copy_attributes = copy_attributes
        self.aggregate: str = aggregate
        self.exception = None
        self.profiles = []

    def run(self):

        feedback = QgsProcessingFeedback()
        feedback.progressChanged.connect(self.setProgress)
        # todo: emit progress
        try:
            vector = QgsVectorLayer(self.path_vector)
            raster = QgsRasterLayer(self.path_raster)

            IO = RasterLayerSpectralLibraryIO()
            settings = {'raster_layer': raster,
                        'vector_layer': vector,
                        'all_touched': self.all_touched,
                        'aggregate': self.aggregate}
            if not self.copy_attributes:
                settings['required_fields'] = []

            profiles = list(IO.importProfiles('', settings, feedback))

            self.profiles.extend(profiles)
        except Exception as ex:
            import traceback
            info = ''.join(traceback.format_stack())
            self.exception = ex
            return False

        return True

    def onProgressChanged(self, vMin, vMax, vValue):
        if vValue <= 0:
            self.progressChanged.emit(0)
        else:
            self.progressChanged.emit(100. * vValue / (vMax - vMin))

    def cancel(self):
        self.progress_handler.cancel()
        super().cancel()

    def finished(self, result):
        if result is True:
            s = ""
        elif result is False:

            if isinstance(self.exception, Exception):
                print(self.exception, file=sys.stderr)
            else:
                s = ""
        pass


class SpectralProfileImportPointsDialog(SelectMapLayersDialog):

    def __init__(self, parent=None, f: Qt.WindowFlags = None):
        super(SpectralProfileImportPointsDialog, self).__init__()

        self.setWindowTitle('Read Spectral Profiles')
        self.addLayerDescription('Raster Layer', QgsMapLayerProxyModel.RasterLayer)
        cb = self.addLayerDescription('Vector Layer', QgsMapLayerProxyModel.VectorLayer)
        cb.layerChanged.connect(self.onVectorLayerChanged)

        self.mProfiles = []
        self.mWkbType = None
        self.aggregateOptions = OptionListModel()
        self.aggregateOptions.addOptions([
            Option('mean'),
            Option('median'),
            Option('min'),
            Option('max'),
            Option('none', toolTip='Returns a spectral profile for each covered pixel')
        ])

        self.mCbAggregation = QComboBox()
        self.mCbAggregation.setModel(self.aggregateOptions)

        self.mCbTouched = QCheckBox(self)
        self.mCbTouched.setText('All touched')
        self.mCbTouched.setToolTip(
            'Activate to extract all touched pixels, not only those entirely covered by a geometry.')

        self.mCbAllAttributes = QCheckBox(self)
        self.mCbAllAttributes.setText('Copy Attributes')
        self.mCbAllAttributes.setToolTip(
            'Activate to copy vector attributes into the Spectral Library'
        )

        self.labelAggregate = QLabel('Aggregate')
        layout = QHBoxLayout()
        layout.addStretch(0)
        layout.addWidget(self.labelAggregate)
        layout.addWidget(self.mCbAggregation)
        layout.addWidget(self.mCbTouched)
        layout.addWidget(self.mCbAllAttributes)

        self.mGrid.addLayout(layout, self.mGrid.rowCount(), 0, 1, self.mGrid.columnCount())

        self.mProgressBar = QProgressBar(self)
        self.mProgressBar.setRange(0, 100)
        self.mGrid.addWidget(self.mProgressBar, self.mGrid.rowCount(), 0, 1, self.mGrid.columnCount())
        self.buttonBox().button(QDialogButtonBox.Ok).clicked.disconnect()
        self.buttonBox().button(QDialogButtonBox.Cancel).clicked.disconnect()
        self.buttonBox().button(QDialogButtonBox.Ok).clicked.connect(self.run)
        self.buttonBox().button(QDialogButtonBox.Cancel).clicked.connect(self.onCancel)

        self.onVectorLayerChanged(cb.currentLayer())

        self.mTasks = dict()
        self.mIsFinished = False

    def setWkbType(self, wkbType):
        self.mWkbType = wkbType

    def wkbType(self):
        return self.mWkbType

    def onCancel(self):
        for t in self.mTasks.items():
            if isinstance(t, QgsTask) and t.canCancel():
                t.cancel()
        self.mIsFinished = True
        self.reject()

    def onVectorLayerChanged(self, layer: QgsVectorLayer):

        if not isinstance(layer, QgsVectorLayer):
            bTouched = bAggregrate = False
        else:
            bTouched = layer.geometryType() != QGIS_GEOMETRYTYPE.Point
            bAggregrate = layer.wkbType() != QGIS_WKBTYPE.Point

            if self.mWkbType is None:
                self.mWkbType = layer.wkbType()

        for w in [self.labelAggregate, self.mCbAggregation]:
            w.setEnabled(bAggregrate)
            w.setVisible(bAggregrate)

        self.mCbTouched.setEnabled(bTouched)
        self.mCbTouched.setVisible(bTouched)

    def profiles(self) -> List[QgsFeature]:
        return self.mProfiles[:]

    def speclib(self) -> QgsVectorLayer:

        slib = SpectralLibraryUtils.createSpectralLibrary(wkbType=self.wkbType(), profile_fields=[])
        slib.startEditing()
        SpectralLibraryUtils.addProfiles(slib, self.mProfiles, addMissingFields=True)
        slib.commitChanges()
        return slib

    def setRasterSource(self, lyr):
        if isinstance(lyr, str):
            lyr = QgsRasterLayer(lyr)
        assert isinstance(lyr, QgsRasterLayer)
        self.selectMapLayer(0, lyr)

    def setVectorSource(self, lyr):
        if isinstance(lyr, str):
            lyr = QgsVectorLayer(lyr)
        assert isinstance(lyr, QgsVectorLayer)
        self.selectMapLayer(1, lyr)

    def onProgressChanged(self, progress):
        self.mProgressBar.setValue(int(progress))

    def onCompleted(self, task: SpectralProfileLoadingTask):
        if isinstance(task, SpectralProfileLoadingTask) and not sip.isdeleted(task):
            self.mProfiles = task.profiles[:]
            self.mTasks.clear()
            self.setResult(QDialog.Accepted)
            self.mIsFinished = True
            self.accept()

    def isFinished(self) -> bool:
        return self.mIsFinished

    def onTerminated(self, *args):
        s = ""
        self.setResult(QDialog.Rejected)
        self.mIsFinished = True
        self.reject()

    def run(self, run_async: bool = True):
        """
        Call this to start loading the profiles in a background process
        """
        self.mProfiles.clear()
        task = SpectralProfileLoadingTask(self.vectorSource().source(),
                                          self.rasterSource().source(),
                                          all_touched=self.allTouched(),
                                          copy_attributes=self.allAttributes(),
                                          aggregate=self.aggregation()

                                          )

        task.progressChanged.connect(self.onProgressChanged)
        task.taskCompleted.connect(lambda *args, t=task: self.onCompleted(t))
        task.taskTerminated.connect(lambda *args, t=task: self.onTerminated(t))

        if run_async:
            mgr = QgsApplication.taskManager()
            assert isinstance(mgr, QgsTaskManager)

            id = mgr.addTask(task)
            self.mTasks[id] = task
        else:
            task.run()
            self.onCompleted(task)

    def allAttributes(self) -> bool:
        """
        Returns True if the "All Attributes" combo box is enabled and checked.
        :return: bool
        """
        return self.mCbAllAttributes.isEnabled() and self.mCbAllAttributes.isChecked()

    def allTouched(self) -> bool:
        """
        Returns True if the "All Touched" combo box is enabled and checked.
        :return: bool
        """
        return self.mCbTouched.isEnabled() and self.mCbTouched.isChecked()

    def setAggregation(self, aggregation: str):
        o = self.aggregateOptions.findOption(aggregation)
        if isinstance(o, Option):
            self.mCbAggregation.setCurrentIndex(self.aggregateOptions.mOptions.index(o))

    def aggregation(self) -> str:
        return self.mCbAggregation.currentData().value()

    def rasterSource(self) -> QgsRasterLayer:
        """
        Returns the selected QgsRasterLayer
        :return: QgsRasterLayer
        """
        return self.mapLayers()[0]

    def vectorSource(self) -> QgsVectorLayer:
        """
        Returns the selected QgsVectorLayer
        :return: QgsVectorLayer
        """
        return self.mapLayers()[1]


RF_PROFILE = FIELD_VALUES
RF_SOURCE = 'source'
RF_NAME = FIELD_NAME
RF_PX_X = 'px_x'
RF_PX_Y = 'px_y'

RASTER_FIELDS = QgsFields()
RASTER_FIELDS.append(create_profile_field(RF_PROFILE))
RASTER_FIELDS.append(QgsField(RF_NAME, QMETATYPE_QSTRING))
RASTER_FIELDS.append(QgsField(RF_SOURCE, QMETATYPE_QSTRING))
RASTER_FIELDS.append(QgsField(RF_PX_X, QMETATYPE_INT))
RASTER_FIELDS.append(QgsField(RF_PX_Y, QMETATYPE_INT))


class RasterLayerSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)
        loadUi(speclibUiPath('rasterspectrallibraryinput.ui'), self)
        self.mFields: QgsFields = QgsFields(RASTER_FIELDS)

        self.cbRasterLayer: QgsMapLayerComboBox
        self.cbVectorLayer: QgsMapLayerComboBox
        self.mCbTouched: QCheckBox
        # self.mCbAllAttributes: QCheckBox
        self.tbInfo: QTextEdit

        self.cbRasterLayer.setAllowEmptyLayer(False)
        if Qgis.versionInt() < 32000:
            self.cbVectorLayer.setAllowEmptyLayer(True)
        else:
            self.cbVectorLayer.setAllowEmptyLayer(True, 'Each Raster Pixel')
        self.cbRasterLayer.setFilters(QGIS_LAYERFILTER.RasterLayer)
        self.cbVectorLayer.setFilters(QGIS_LAYERFILTER.VectorLayer)
        excluded = [p for p in QgsProviderRegistry.instance().providerList() if p not in ['ogr']]
        self.cbVectorLayer.setExcludedProviders(excluded)
        self.mCbTouched.stateChanged.connect(self.updateInfoBox)
        # self.mCbAllAttributes.stateChanged.connect(self.updateInfoBox)
        self.cbRasterLayer.layerChanged.connect(self.updateInfoBox)
        self.cbVectorLayer.layerChanged.connect(self.updateInfoBox)

        self.updateInfoBox()

    def importSettings(self, settings: dict) -> dict:

        settings['raster_layer'] = self.cbRasterLayer.currentLayer()
        settings['fields'] = QgsFields(self.mFields)

        vl = self.cbVectorLayer.currentLayer()
        if isinstance(vl, QgsVectorLayer):
            settings['vector_layer'] = vl
            settings['all_touched'] = self.mCbTouched.isChecked()
            # settings['copy_vector_attributes'] = self.mCbAllAttributes.isChecked()

        return settings

    def updateInfoBox(self):
        rl: QgsRasterLayer = self.rasterLayer()
        vl: QgsVectorLayer = self.vectorLayer()
        has_vector = isinstance(vl, QgsVectorLayer)

        # self.mCbAllAttributes.setEnabled(has_vector)
        self.mCbTouched.setEnabled(has_vector and QgsWkbTypes.geometryType(vl.wkbType()) == QgsWkbTypes.PolygonGeometry)

        if has_vector:
            info = 'Extract raster profiles for geometry positions'
        else:
            info = 'Extracts a profiles from each valid pixel position'
            if isinstance(rl, QgsRasterLayer):
                info += f'\n{rl.width()} x {rl.height()} = up to {rl.width() * rl.height()} profiles'
        self.tbInfo.setText(info)

        self.updateFields()

    def rasterLayer(self) -> QgsRasterLayer:
        return self.cbRasterLayer.currentLayer()

    def vectorLayer(self) -> QgsVectorLayer:
        return self.cbVectorLayer.currentLayer()

    def updateFields(self):

        new_fields = QgsFields(RASTER_FIELDS)

        vl: QgsVectorLayer = self.vectorLayer()
        # copy attributes from input vector
        if isinstance(vl, QgsVectorLayer):
            for field in vl.fields():
                if field not in new_fields:
                    new_fields.append(QgsField(field))

        self.mFields = new_fields
        self.sigSourceChanged.emit()

    def spectralLibraryIO(cls) -> 'SpectralLibraryIO':
        return SpectralLibraryIO.spectralLibraryIOInstances(RasterLayerSpectralLibraryIO)

    def supportsMultipleFiles(self) -> bool:
        return None

    def filter(self) -> str:
        return "GeoTiff (*.tif);;Any file (*.*)"

    def setSource(self, source: str):
        if self.mSource != source:
            self.mSource = source
            self.sigSourceChanged.emit()

    def sourceCrs(self) -> QgsCoordinateReferenceSystem:
        lyr = self.rasterLayer()
        if isinstance(lyr, QgsRasterLayer):
            return QgsCoordinateReferenceSystem(lyr.crs())
        else:
            return QgsCoordinateReferenceSystem()

    def sourceFields(self) -> QgsFields:
        return QgsFields(self.mFields)


class RasterLayerSpectralLibraryIO(SpectralLibraryIO):

    def __init__(self, *args, **kwds):

        super().__init__(*args, **kwds)

    @classmethod
    def formatName(cls) -> str:
        return 'Raster Layer'

    @classmethod
    def createImportWidget(cls) -> SpectralLibraryImportWidget:
        return RasterLayerSpectralLibraryImportWidget()

    @classmethod
    def importProfiles(cls,
                       path: Union[str, pathlib.Path, QUrl],
                       importSettings: dict = dict(),
                       feedback: QgsProcessingFeedback = QgsProcessingFeedback()) -> List[QgsFeature]:

        path = cls.extractFilePath(path)
        required_fields = QgsFields()
        if 'fields' in importSettings.keys():
            available_fields: QgsFields = QgsFields(importSettings['fields'])
        else:
            available_fields: QgsFields = QgsFields(RASTER_FIELDS)

        if IMPORT_SETTINGS_KEY_REQUIRED_SOURCE_FIELDS in importSettings.keys():
            for name in importSettings[IMPORT_SETTINGS_KEY_REQUIRED_SOURCE_FIELDS]:
                if name in available_fields.names():
                    required_fields.append(available_fields.field(name))
        else:
            required_fields = available_fields

        rl = importSettings.get('raster_layer', path)
        vl = importSettings.get('vector_layer', None)
        all_touched = importSettings.get('all_touched', False)
        if isinstance(rl, (str, pathlib.Path)):
            rl = QgsRasterLayer(pathlib.Path(rl).as_posix(), 'raster')

        assert isinstance(rl, QgsRasterLayer) and rl.isValid()

        generator = None
        if vl is None:
            generator = RasterLayerSpectralLibraryIO.readRaster(rl, required_fields, feedback=feedback)
        else:
            if not isinstance(vl, QgsVectorLayer):
                vl = QgsVectorLayer(vl)
            assert isinstance(vl, QgsVectorLayer) and vl.isValid()
            generator = RasterLayerSpectralLibraryIO.readRasterVector(rl, vl, required_fields, all_touched,
                                                                      feedback=feedback)

        profiles = []
        if generator:
            for p in generator:
                profiles.append(p)
        return profiles

    @staticmethod
    def readRaster(raster,
                   fields: QgsFields,
                   feedback: QgsProcessingFeedback = QgsProcessingFeedback()) \
            -> Generator[QgsFeature, None, None]:

        raster: QgsRasterLayer
        try:
            raster = qgsRasterLayer(raster)
        except Exception as ex:
            feedback.pushWarning(f'Unable to open {raster} as QgsRasterLayer.\n{ex}')
            raise StopIteration

        assert isinstance(fields, QgsFields)

        raster_source = raster.source()
        raster_name = pathlib.Path(raster_source).name
        dp: QgsRasterDataProvider = raster.dataProvider()
        ds: gdal.Dataset = gdalDataset(raster)
        if isinstance(ds, gdal.Dataset):
            wl, wlu = parseWavelength(ds)
            fwhm = parseFWHM(ds)
            bbl = parseBadBandList(ds)
        else:
            wl = wlu = fwhm = bbl = None

        # each none-masked pixel is a profile
        array = rasterArray(raster)

        # todo: add multi-band masking options
        valid = np.isfinite(array[0, :])
        if dp.sourceHasNoDataValue(1):
            valid = np.logical_and(valid, array[0, :] != dp.sourceNoDataValue(1))
        for ndv in dp.userNoDataValues(1):
            valid = np.logical_and(valid, array[0, :] != ndv)

        valid = np.where(valid)

        geo_x, geo_y = px2geocoordinatesV2(raster)

        n_profiles = len(valid[0])
        if n_profiles > PIXEL_LIMIT:
            raise Exception(f'Number of raster image pixels {n_profiles} exceeds PIXEL_LIMIT {PIXEL_LIMIT}')

        if wl is not None:
            xvalues = wl.tolist()
        else:
            xvalues = (np.arange(ds.RasterCount) + 1).tolist()

        i_RF_NAME = fields.lookupField(RF_NAME)
        i_RF_SOURCE = fields.lookupField(RF_SOURCE)
        i_RF_PX_X = fields.lookupField(RF_PX_X)
        i_RF_PX_Y = fields.lookupField(RF_PX_Y)
        i_RF_PROFILE = fields.lookupField(RF_PROFILE)

        for y, x in zip(*valid):

            yvalues = array[:, y, x]

            p = QgsFeature(fields)

            if i_RF_NAME >= 0:
                p.setAttribute(i_RF_NAME, raster_name)

            if i_RF_SOURCE >= 0:
                p.setAttribute(i_RF_SOURCE, raster_source)

            if i_RF_PX_X >= 0:
                p.setAttribute(i_RF_PX_X, x)

            if i_RF_PX_Y >= 0:
                p.setAttribute(i_RF_PX_Y, y)

            gx, gy = geo_x[x], geo_y[y]
            p.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(gx, gy)))

            if i_RF_PROFILE >= 0:
                spectrum_dict = prepareProfileValueDict(x=xvalues, y=yvalues, xUnit=wlu)
                p.setAttribute(i_RF_PROFILE, encodeProfileValueDict(spectrum_dict, fields.at(i_RF_PROFILE)))

            yield p

    @staticmethod
    def readRasterVector(raster, vector,
                         fields: QgsFields,
                         all_touched: bool = True,
                         aggregation: str = 'mean',
                         cache: int = 5 * 2 ** 20,
                         feedback: QgsProcessingFeedback = QgsProcessingFeedback()) \
            -> Generator[QgsFeature, None, None]:

        rl = qgsRasterLayer(raster)
        vl = qgsVectorLayer(vector)

        path = pathlib.Path(rl.source())
        raster_name = path.name
        raster_source = path.as_posix()

        sp = QgsRasterLayerSpectralProperties.fromRasterLayer(rl)
        bbl = sp.badBands()
        wl = sp.wavelengths()
        wlu = sp.wavelengthUnits()[0]

        transform = QgsCoordinateTransform()
        transform.setSourceCrs(vl.crs()),

        transform.setDestinationCrs(rl.crs())

        i_RF_NAME = fields.lookupField(RF_NAME)
        i_RF_SOURCE = fields.lookupField(RF_SOURCE)
        i_RF_PX_X = fields.lookupField(RF_PX_X)
        i_RF_PX_Y = fields.lookupField(RF_PX_Y)
        i_RF_PROFILE = fields.lookupField(RF_PROFILE)

        PROFILE_COUNTS = dict()

        NODATA = noDataValues(rl)
        errors = set()

        func = RasterProfile()

        request = QgsFeatureRequest()
        request.setInvalidGeometryCheck(QgsFeatureRequest.InvalidGeometryCheck.GeometrySkipInvalid)
        request.setDestinationCrs(rl.crs(), QgsProject.instance().transformContext())
        request.setFilterRect(rl.extent())

        all_touched = False
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.layerScope(rl))

        fcontext = QgsExpressionContext(context)
        n_total = vl.featureCount()
        next_progress = 5
        for iFeature, f in enumerate(vl.getFeatures(request)):
            g = f.geometry()
            if not isinstance(g, QgsGeometry):
                continue

            all_touched = False
            values = [rl, g, aggregation, all_touched, 'dict']
            exp = QgsExpression()
            fcontext.setGeometry(g)
            profiles_at = func.func(values, fcontext, exp, None)

            if exp.hasParserError() or exp.hasEvalError():
                error = '\n'.join([exp.parserErrorString(), exp.evalErrorString()])
                if error not in errors:
                    feedback.pushWarning(error)
                    errors.add(error)

                continue

            if profiles_at is None:
                continue

            if isinstance(profiles_at, dict):
                profiles_at = [profiles_at]

            loc_geo = fcontext.variable('raster_array_geo')
            loc_px_x, loc_px_y = fcontext.variable('raster_array_px')

            progress = int(100. * iFeature / n_total)
            if progress >= next_progress:
                feedback.setProgress(progress)
                next_progress += 5

            for i, pDict in enumerate(profiles_at):

                p = QgsFeature(fields)
                if False and aggregation.lower() == 'none':
                    g: QgsGeometry = f.geometry()
                else:
                    g: QgsGeometry = QgsGeometry.fromPointXY(loc_geo[i])
                p.setGeometry(g)

                if i_RF_NAME >= 0:
                    p.setAttribute(i_RF_NAME, raster_name)

                if i_RF_SOURCE >= 0:
                    p.setAttribute(i_RF_SOURCE, raster_source)

                if i_RF_PROFILE >= 0:
                    p.setAttribute(i_RF_PROFILE,
                                   encodeProfileValueDict(pDict, fields.at(i_RF_PROFILE)))

                if i_RF_PX_X >= 0:
                    p[i_RF_PX_X] = loc_px_x[i]

                if i_RF_PX_Y >= 0:
                    p[i_RF_PX_Y] = loc_px_y[i]

                if isinstance(f, QgsFeature) and f.isValid():
                    for field in f.fields():
                        if field in fields:
                            p.setAttribute(field.name(), f.attribute(field.name()))
                yield p
        return
