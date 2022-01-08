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
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import pathlib
import sys
import typing
import warnings

import numpy as np
from qgis.PyQt.QtCore import QVariant, Qt
from qgis.PyQt.QtWidgets import QDialogButtonBox, QProgressBar, QDialog, QTextEdit, QCheckBox, QHBoxLayout
from osgeo import gdal

from qgis.PyQt import sip
from qgis.core import QgsFields, QgsField, Qgis, QgsFeature, QgsRasterDataProvider, \
    QgsCoordinateReferenceSystem, QgsGeometry, QgsPointXY, QgsPoint
from qgis.core import QgsProviderRegistry
from qgis.core import QgsTask, QgsVectorLayer, QgsRasterLayer, QgsWkbTypes, \
    QgsTaskManager, QgsMapLayerProxyModel, QgsApplication, QgsProcessingFeedback
from qgis.gui import QgsMapLayerComboBox
from .. import speclibUiPath
from ..core import create_profile_field
from ..core.spectrallibrary import SpectralProfile, SpectralLibrary
from ..core.spectrallibraryio import SpectralLibraryIO, SpectralLibraryImportWidget, \
    IMPORT_SETTINGS_KEY_REQUIRED_SOURCE_FIELDS
from ..core.spectralprofile import prepareProfileValueDict, encodeProfileValueDict
from ...utils import SelectMapLayersDialog, gdalDataset, parseWavelength, parseFWHM, parseBadBandList, loadUi, \
    rasterLayerArray, qgsRasterLayer, px2geocoordinatesV2, optimize_block_size, px2geocoordinates, fid2pixelindices

PIXEL_LIMIT = 100 * 100


class SpectralProfileLoadingTask(QgsTask):

    def __init__(self, path_vector: str, path_raster: str, all_touched: bool = True, copy_attributes: bool = False):
        super().__init__('Load spectral profiles', QgsTask.CanCancel)
        assert isinstance(path_vector, str)
        assert isinstance(path_raster, str)

        self.path_vector = path_vector
        self.path_raster = path_raster
        self.all_touched = all_touched
        self.copy_attributes = copy_attributes
        self.exception = None
        self.profiles = None

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
                        'all_touched': self.all_touched}
            if not self.copy_attributes:
                settings['required_fields'] = []

            profiles = list(IO.importProfiles('', settings, feedback))

            self.profiles = profiles
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

        self.mCbTouched = QCheckBox(self)
        self.mCbTouched.setText('All touched')
        self.mCbTouched.setToolTip(
            'Activate to extract all touched pixels, not only those entirely covered by a geometry.')

        self.mCbAllAttributes = QCheckBox(self)
        self.mCbAllAttributes.setText('Copy Attributes')
        self.mCbAllAttributes.setToolTip(
            'Activate to copy vector attributes into the Spectral Library'
        )

        layout = QHBoxLayout()
        layout.addWidget(self.mCbTouched)
        layout.addWidget(self.mCbAllAttributes)
        i = self.mGrid.rowCount()
        self.mGrid.addLayout(layout, i, 1)

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

    def onCancel(self):
        for t in self.mTasks.items():
            if isinstance(t, QgsTask) and t.canCancel():
                t.cancel()
        self.mIsFinished = True
        self.reject()

    def onVectorLayerChanged(self, layer: QgsVectorLayer):
        self.mCbTouched.setEnabled(isinstance(layer, QgsVectorLayer)
                                   and QgsWkbTypes.geometryType(layer.wkbType()) == QgsWkbTypes.PolygonGeometry)

    def profiles(self) -> typing.List[SpectralProfile]:
        return self.mProfiles[:]

    def speclib(self) -> SpectralLibrary:
        slib = SpectralLibrary()
        slib.startEditing()
        if len(self.mProfiles) > 0:
            slib.addMissingFields(self.mProfiles[0].fields())

        slib.addProfiles(self.mProfiles, addMissingFields=False)
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
        task = SpectralProfileLoadingTask(self.vectorSource().source(),
                                          self.rasterSource().source(),
                                          all_touched=self.allTouched(),
                                          copy_attributes=self.allAttributes()
                                          )

        task.progressChanged.connect(self.onProgressChanged)

        if run_async:
            mgr = QgsApplication.taskManager()
            assert isinstance(mgr, QgsTaskManager)
            task.taskCompleted.connect(lambda task=task: self.onCompleted(task))
            task.taskTerminated.connect(lambda task=task: self.onTerminated(task))

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


RF_PROFILE = 'raster_profile'
RF_SOURCE = 'raster_source'
RF_NAME = 'raster_name'
RF_PX_X = 'raster_px_x'
RF_PX_Y = 'raster_px_y'

RASTER_FIELDS = QgsFields()
RASTER_FIELDS.append(create_profile_field(RF_PROFILE))
RASTER_FIELDS.append(QgsField(RF_NAME, QVariant.String))
RASTER_FIELDS.append(QgsField(RF_SOURCE, QVariant.String))
RASTER_FIELDS.append(QgsField(RF_PX_X, QVariant.Int))
RASTER_FIELDS.append(QgsField(RF_PX_Y, QVariant.Int))


class RasterLayerSpectralLibraryImportWidget(SpectralLibraryImportWidget):

    def __init__(self, *args, **kwds):
        super(RasterLayerSpectralLibraryImportWidget, self).__init__(*args, **kwds)
        loadUi(speclibUiPath('rasterspectrallibraryinput.ui'), self)
        self.mFields: QgsFields = QgsFields(RASTER_FIELDS)

        self.cbRasterLayer: QgsMapLayerComboBox
        self.cbVectorLayer: QgsMapLayerComboBox
        self.mCbTouched: QCheckBox
        # self.mCbAllAttributes: QCheckBox
        self.tbInfo: QTextEdit

        Qgis.version()
        self.cbRasterLayer.setAllowEmptyLayer(False)
        if Qgis.versionInt() < 32000:
            self.cbVectorLayer.setAllowEmptyLayer(True)
        else:
            self.cbVectorLayer.setAllowEmptyLayer(True, 'Each Raster Pixel')
        self.cbRasterLayer.setFilters(QgsMapLayerProxyModel.RasterLayer)
        self.cbVectorLayer.setFilters(QgsMapLayerProxyModel.PointLayer | QgsMapLayerProxyModel.PolygonLayer)
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
                       path: str,
                       importSettings: dict,
                       feedback: QgsProcessingFeedback) -> typing.List[QgsFeature]:

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
        if not isinstance(rl, QgsRasterLayer):
            rl = QgsRasterLayer(rl)

        assert isinstance(rl, QgsRasterLayer) and rl.isValid()

        if vl is None:
            return RasterLayerSpectralLibraryIO.readRaster(rl, required_fields)
        else:
            if not isinstance(vl, QgsVectorLayer):
                vl = QgsVectorLayer(vl)
            assert isinstance(vl, QgsVectorLayer) and vl.isValid()
            return RasterLayerSpectralLibraryIO.readRasterVector(rl, vl, required_fields, all_touched)

    @staticmethod
    def readRaster(raster, fields: QgsFields) -> typing.Generator[QgsFeature, None, None]:

        raster: QgsRasterLayer
        try:
            raster = qgsRasterLayer(raster)

        except Exception as ex:
            warnings.warn(f'Unable to open {raster} as QgsRasterLayer.\n{ex}')
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
        array = rasterLayerArray(raster)

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
                p.setAttribute(i_RF_PROFILE, encodeProfileValueDict(spectrum_dict))

            yield p

    @staticmethod
    def readRasterVector(raster, vector,
                         fields: QgsFields,
                         all_touched: bool,
                         cache: int = 5 * 2 ** 20) -> typing.Generator[QgsFeature, None, None]:

        ds: gdal.Dataset = gdalDataset(raster)
        assert isinstance(ds, gdal.Dataset), f'Unable to open {raster.source()} as gdal.Dataset'

        path = pathlib.Path(ds.GetDescription())
        raster_name = path.name
        raster_source = path.as_posix()

        bbl = parseBadBandList(ds)
        wl, wlu = parseWavelength(ds)

        block_size = optimize_block_size(ds, cache=cache)

        nXBlocks = int((ds.RasterXSize + block_size[0] - 1) / block_size[0])
        nYBlocks = int((ds.RasterYSize + block_size[1] - 1) / block_size[1])
        nBlocksTotal = nXBlocks * nYBlocks
        nBlocksDone = 0

        # pixel center coordinates as geolocations

        geo_x, geo_y = px2geocoordinates(ds, pxCenter=True)

        # get FID positions
        layer = 0
        for sub in vector.dataProvider().subLayers():
            layer = sub.split('!!::!!')[1]
            break

        fid_positions, no_fid = fid2pixelindices(ds, vector,
                                                 layer=layer,
                                                 all_touched=all_touched)

        i_RF_NAME = fields.lookupField(RF_NAME)
        i_RF_SOURCE = fields.lookupField(RF_SOURCE)
        i_RF_PX_X = fields.lookupField(RF_PX_X)
        i_RF_PX_Y = fields.lookupField(RF_PX_Y)
        i_RF_PROFILE = fields.lookupField(RF_PROFILE)

        PROFILE_COUNTS = dict()

        FEATURES: typing.Dict[int, QgsFeature] = dict()

        for y in range(nYBlocks):
            yoff = y * block_size[1]
            for x in range(nXBlocks):
                xoff = x * block_size[0]
                xsize = min(block_size[0], ds.RasterXSize - xoff)
                ysize = min(block_size[1], ds.RasterYSize - yoff)
                cube: np.ndarray = ds.ReadAsArray(xoff=xoff, yoff=yoff, xsize=xsize, ysize=ysize)
                cube = cube.reshape((ds.RasterCount, ysize, xsize))
                fid_pos = fid_positions[yoff:yoff + ysize, xoff:xoff + xsize]
                assert cube.shape[1:] == fid_pos.shape

                for fid in [int(v) for v in np.unique(fid_pos) if v != no_fid]:
                    fid_yy, fid_xx = np.where(fid_pos == fid)
                    n_p = len(fid_yy)
                    if n_p > 0:

                        if fid not in FEATURES.keys():
                            FEATURES[fid] = vector.getFeature(fid)
                        vectorFeature: QgsFeature = FEATURES.get(fid)

                        fid_profiles = cube[:, fid_yy, fid_xx]
                        profile_geo_x = geo_x[fid_yy + yoff, fid_xx + xoff]
                        profile_geo_y = geo_y[fid_yy + yoff, fid_xx + xoff]
                        profile_px_x = fid_xx + xoff
                        profile_px_y = fid_yy + yoff

                        for i in range(n_p):
                            # create profile feature
                            p = QgsFeature(fields)

                            # create geometry
                            p.setGeometry(QgsPoint(profile_geo_x[i],
                                                   profile_geo_y[i]))

                            PROFILE_COUNTS[fid] = PROFILE_COUNTS.get(fid, 0) + 1
                            # sp.setName(f'{fid_basename}_{PROFILE_COUNTS[fid]}')

                            if i_RF_NAME >= 0:
                                p.setAttribute(i_RF_NAME, raster_name)

                            if i_RF_SOURCE >= 0:
                                p.setAttribute(i_RF_SOURCE, raster_source)

                            if i_RF_PROFILE >= 0:
                                spectrum_dict = prepareProfileValueDict(x=wl, y=fid_profiles[:, i], xUnit=wlu, bbl=bbl)
                                p.setAttribute(i_RF_PROFILE, encodeProfileValueDict(spectrum_dict))

                            if i_RF_PX_X >= 0:
                                p[i_RF_PX_X] = int(profile_px_x[i])

                            if i_RF_PX_Y >= 0:
                                p[i_RF_PX_Y] = int(profile_px_y[i])

                            if isinstance(vectorFeature, QgsFeature) and vectorFeature.isValid():
                                for field in vectorFeature.fields():
                                    if field in fields:
                                        p.setAttribute(field.name(), vectorFeature.attribute(field.name()))

                            yield p
