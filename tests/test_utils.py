# coding=utf-8
"""Resources test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'benjamin.jakimow@geo.hu-berlin.de'
__date__ = '2017-07-17'
__copyright__ = 'Copyright 2017, Benjamin Jakimow'

import os
import pathlib
import pickle
import random
import re
import unittest
import warnings
import xml.etree.ElementTree as ET
from math import nan
from typing import Dict

import numpy as np
from osgeo import gdal, gdal_array, ogr, osr

from qgis.PyQt.QtCore import NULL, QByteArray, QObject, QPoint, QRect, QUrl, QVariant
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QDialog, QDockWidget, QGroupBox, QMainWindow, QMenu, QWidget
from qgis.PyQt.QtXml import QDomDocument, QDomElement
from qgis.core import QgsCoordinateReferenceSystem, QgsFeature, QgsFeatureRequest, QgsField, QgsGeometry, \
    QgsGeometryParameters, QgsMapLayerProxyModel, QgsMapLayerStore, QgsMapToPixel, QgsPointXY, QgsProcessingFeedback, \
    QgsProject, QgsRaster, QgsRasterDataProvider, QgsRasterIdentifyResult, QgsRasterLayer, QgsRectangle, QgsVector, \
    QgsVectorLayer
from qgis.core import QgsWkbTypes, QgsExpressionContextUtils
from qgis.gui import QgsDockWidget
from qgis.gui import QgsFieldCalculator
from qps.speclib.core import is_spectral_library
from qps.speclib.core.spectralprofile import decodeProfileValueDict
from qps.testing import start_app, TestCase, TestObjects
from qps.unitmodel import UnitLookup
from qps.utils import aggregateArray, appendItemsToMenu, createQgsField, defaultBands, displayBandNames, dn, \
    ExtentTileIterator, fid2pixelindices, file_search, filenameFromString, findMapLayerStores, findParent, gdalDataset, \
    gdalFileSize, geo2px, layerGeoTransform, loadUi, MapGeometryToPixel, nextColor, nodeXmlString, optimize_block_size, \
    osrSpatialReference, parseFWHM, parseWavelength, px2geo, px2geocoordinates, px2spatialPoint, qgsField, \
    qgsFieldAttributes2List, qgsRasterLayer, qgsRasterLayers, rasterArray, rasterBlockArray, rasterizeFeatures, \
    relativePath, SelectMapLayerDialog, SelectMapLayersDialog, snapGeoCoordinates, SpatialExtent, SpatialPoint, \
    spatialPoint2px, value2str, writeAsVectorFormat, create_picture_viewer_config, xy_pair_matrix, featureSymbolScope, \
    TemporaryGlobalLayerContext
from qpstestdata import enmap, enmap_multipoint, enmap_multipolygon, enmap_pixel, hymap, landcover

start_app()


class TestUtils(TestCase):

    def test_temp_project_layers(self):
        p1 = QgsProject.instance()
        self.assertTrue(len(p1.mapLayers().keys()) == 0)

        p2 = QgsProject()

        lyr = TestObjects.createRasterLayer()
        lyr.setName('A')
        lid = lyr.id()
        p2.addMapLayer(lyr)

        self.assertFalse(lid in p1.mapLayers().keys())
        self.assertTrue(lid in p2.mapLayers().keys())

        with TemporaryGlobalLayerContext(p2):
            self.assertTrue(lid in p1.mapLayers().keys())
            self.assertTrue(lid in p2.mapLayers().keys())

        self.assertFalse(lid in p1.mapLayers().keys())
        self.assertTrue(lid in p2.mapLayers().keys())

        p1.removeAllMapLayers()

    @unittest.skipIf(TestCase.runsInCI(), 'Blocking dialog.')
    def test_temp_project_layers_fieldcalculator(self):
        p1 = QgsProject.instance()
        self.assertTrue(len(p1.mapLayers().keys()) == 0)
        from qpstestdata import enmap_polygon, enmap_pixel
        lyrA = QgsVectorLayer(enmap_polygon.as_posix(), 'A', 'ogr')
        p1.addMapLayer(lyrA)

        p2 = QgsProject()

        lyrB = QgsVectorLayer(enmap_pixel.as_posix(), 'B', 'ogr')
        p2.addMapLayer(lyrB)

        with TemporaryGlobalLayerContext(p2):
            gui = QgsFieldCalculator(lyrB, None)
            gui.exec_()

    def test_loadUi(self):

        import qps
        sources = list(file_search(dn(qps.__file__), '*.ui', recursive=True))
        sources = [s for s in sources if 'pyqtgraph' not in s]
        sources = [s for s in sources if 'externals' not in s]

        for pathUi in sources:
            tree = ET.parse(pathUi)
            root = tree.getroot()
            self.assertEqual(root.tag, 'ui')
            baseClass = root.find('widget').attrib['class']

            print('Try to load {} as {}'.format(pathUi, baseClass))
            self.assertIsInstance(baseClass, str)

            if baseClass == 'QDialog':
                class TestWidget(QDialog):

                    def __init__(self):
                        super().__init__()
                        loadUi(pathUi, self)

            elif baseClass == 'QWidget':
                class TestWidget(QWidget):

                    def __init__(self):
                        super().__init__()
                        loadUi(pathUi, self)

            elif baseClass == 'QMainWindow':
                class TestWidget(QMainWindow):

                    def __init__(self):
                        super().__init__()
                        loadUi(pathUi, self)
            elif baseClass == 'QDockWidget':
                class TestWidget(QDockWidget):
                    def __init__(self):
                        super().__init__()
                        loadUi(pathUi, self)
            elif baseClass == 'QGroupBox':
                class TestWidget(QGroupBox):
                    def __init__(self):
                        super().__init__()
                        loadUi(pathUi, self)
            elif baseClass == 'QgsDockWidget':
                class TestWidget(QgsDockWidget):
                    def __init__(self):
                        super().__init__()
                        loadUi(pathUi, self)
            else:
                warnings.warn('BaseClass {} not implemented\nto test {}'.format(baseClass, pathUi), Warning)
                continue

            w = None
            try:
                w = TestWidget()
                s = ""

            except Exception as ex:
                info = 'Failed to load {}'.format(pathUi)
                info += '\n' + str(ex)
                self.fail(info)

    def test_gdal_filesize(self):

        DIR_VRT_STACK = r'Q:\Processing_BJ\99_OSARIS_Testdata\Loibl-2019-OSARIS-Ala-Archa\BJ_VRT_Stacks'

        if os.path.isdir(DIR_VRT_STACK):
            for path in file_search(DIR_VRT_STACK, '*.vrt'):
                size = gdalFileSize(path)
                self.assertTrue(size > 0)

    def test_qgsFieldAttributes2List(self):

        bstr = b'\x80\x04\x95^\x00\x00\x00\x00\x00\x00\x00}\x94(\x8c\x01x\x94]\x94(M,\x01M' \
               b'\x90\x01MX\x02M\xb0\x04M\xc4\te\x8c\x01y\x94]\x94(G?\xcdp\xa3\xd7\n=qG?' \
               b'\xd9\x99\x99\x99\x99\x99\x9aG?\xd3333333G?\xe9\x99\x99\x99\x99\x99\x9aG?' \
               b'\xe6ffffffe\x8c\x05xUnit\x94\x8c\x02nm\x94u.'
        attributes = [None,
                      NULL,
                      QVariant(None),
                      '',
                      'None',
                      QByteArray(bstr),
                      bstr,
                      bytes(bstr)
                      ]

        a2 = qgsFieldAttributes2List(attributes)
        dump = pickle.dumps(a2, protocol=pickle.HIGHEST_PROTOCOL)
        self.assertIsInstance(dump, bytes)

    def test_findParents(self):

        class ClassA(QObject):
            def __init__(self, *args, **kwds):
                super().__init__(*args, **kwds)

        class ClassB(ClassA):
            def __init__(self, *args, **kwds):
                super().__init__(*args, **kwds)

        obj1 = ClassA()
        obj2 = ClassB(parent=obj1)
        obj3 = ClassA(parent=obj2)

        r = findParent(obj3, ClassA)
        self.assertEqual(r, obj1)

        r = findParent(obj3, ClassA, checkInstance=True)
        self.assertEqual(r, obj2)

    def test_findmaplayerstores(self):

        ref = [QgsProject.instance(), QgsMapLayerStore(), QgsMapLayerStore()]

        found = list(findMapLayerStores())
        self.assertTrue(len(ref) <= len(found))
        for s in found:
            self.assertIsInstance(s, (QgsProject, QgsMapLayerStore))
        for s in ref:
            self.assertTrue(s in found)

    def test_findwavelength(self):

        lyr = TestObjects.createRasterLayer()
        wl, wlu = parseWavelength(lyr)

        self.assertIsInstance(wl, np.ndarray)
        self.assertIsInstance(wlu, str)

        paths = [lyr.source()]
        for p in paths:
            ds = None
            try:
                ds = gdalDataset(p)
            except NotImplementedError:
                pass

            if isinstance(ds, gdal.Dataset):
                wl, wlu = parseWavelength(ds)
                fwhm = parseFWHM(ds)
                self.assertIsInstance(wl, np.ndarray)
                self.assertTrue(len(wl), ds.RasterCount)
                self.assertIsInstance(wlu, str)

    def test_file_search(self):

        rootQps = pathlib.Path(__file__).parents[1]
        self.assertTrue(rootQps.is_dir())

        results = list(file_search(rootQps, 'test_utils.py', recursive=False))
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) == 0)

        for pattern in ['test_utils.py', 'test_utils*.py', re.compile(r'test_utils\.py')]:
            results = list(file_search(rootQps, pattern, recursive=True))
            self.assertIsInstance(results, list)
            self.assertTrue(len(results) == 1)
            self.assertTrue(os.path.isfile(results[0]))

    def test_vsimem(self):

        from qps.utils import check_vsimem

        b = check_vsimem()
        self.assertIsInstance(b, bool)

    def test_qgsField(self):

        lyr = TestObjects.createVectorLayer()
        for i, field in enumerate(lyr.fields()):
            name = field.name()
            self.assertEqual(field, qgsField(lyr, name))
            self.assertEqual(field, qgsField(lyr, field))
            self.assertEqual(field, qgsField(lyr, i))

    def test_qgsLayers(self):

        # raster
        lyr = TestObjects.createRasterLayer()
        sources = [lyr, lyr.source()]

        for s in sources:
            layer = qgsRasterLayer(s)
            self.assertIsInstance(layer, QgsRasterLayer)

        p = r'D:\LUMOS\Data\S2B_MSIL2A_20200106T105339_N0213_R051_T31UFS_20200106T121433.SAFE\MTD_MSIL2A.xml'
        if os.path.isfile(p):
            sources = [QgsRasterLayer(p), p]
            for s in sources:
                self.assertIsInstance(qgsRasterLayer(s), QgsRasterLayer)

            with_sublayers = list(qgsRasterLayers(sources))
            self.assertTrue(len(with_sublayers) > len(sources))
            for lyr in with_sublayers:
                self.assertIsInstance(lyr, QgsRasterLayer)
                self.assertTrue(lyr.isValid())

    def test_spatialObjects(self):

        wkt = 'PROJCS["BU MEaSUREs Lambert Azimuthal Equal Area - SA - V01",GEOGCS["GCS_WGS_1984",' \
              'DATUM["WGS_1984",SPHEROID["WGS_1984",6378137,298.257223563]],PRIMEM["Greenwich",0],' \
              'UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]]],' \
              'PROJECTION["Lambert_Azimuthal_Equal_Area"],PARAMETER["latitude_of_center",-15],' \
              'PARAMETER["longitude_of_center",-60],PARAMETER["false_easting",0],' \
              'PARAMETER["false_northing",0],UNIT["metre",1],AXIS["Easting",EAST],AXIS["Northing",NORTH]]'
        crs = QgsCoordinateReferenceSystem.fromWkt(wkt)
        self.assertTrue(crs.isValid())
        pt1 = SpatialPoint(wkt, 300, 300)
        self.assertIsInstance(pt1, SpatialPoint)
        d = pickle.dumps(pt1)
        pt2 = pickle.loads(d)
        self.assertEqual(pt1, pt2)

        doc = QDomDocument('qps')
        node = doc.createElement('POINT_NODE')
        pt1.writeXml(node, doc)
        pt3 = SpatialPoint.readXml(node)

        self.assertEqual(pt1, pt3)

        ext1 = SpatialExtent(wkt, QgsPointXY(0, 0), QgsPointXY(10, 20))
        d = pickle.dumps(ext1)
        ext2 = pickle.loads(d)
        self.assertEqual(ext1, ext2)

        node = doc.createElement('EXTENT_NODE')
        ext1.writeXml(node, doc)
        ext2 = SpatialExtent.readXml(node)
        self.assertEqual(ext1, ext2)
        self.assertEqual(ext1.crs().toWkt(), ext2.crs().toWkt())

        ext3 = SpatialExtent(ext1)
        self.assertEqual(ext3.asWktPolygon(), ext1.asWktPolygon())

    def test_writeAsVectorFormat(self):

        lyr = TestObjects.createSpectralLibrary(10)

        DIR = self.createTestOutputDirectory()

        extensions = ['.gml',
                      '.gpkg',
                      # '.csv',
                      '.kml',
                      '.geojson',
                      ]
        for i, extension in enumerate(extensions):
            path = DIR / f'example_{i + 1}{extension}'
            lyr2 = writeAsVectorFormat(lyr, path)
            return
            self.assertIsInstance(lyr2, QgsVectorLayer)
            self.assertTrue(lyr2.isValid())
            self.assertEqual(lyr.featureCount(), lyr2.featureCount())
            self.assertTrue(is_spectral_library(lyr2), msg=f'Not a speclib: {lyr2.source()}')

            for f1, f2 in zip(lyr.getFeatures(), lyr2.getFeatures()):
                f1: QgsFeature
                p1 = decodeProfileValueDict(f1.attribute('profiles0'))
                p2 = decodeProfileValueDict(f2.attribute('profiles0'))

                self.assertEqual(p1, p2)

        # ESRI Shapefile does not support string fields with unlimited length
        self.assertIsInstance(writeAsVectorFormat(lyr, DIR / 'exampleX.shp'), QgsVectorLayer)

    def test_profile_matrix(self):
        # index   :  0    2   3   4    5
        # x values:  1    2   3   4    7
        # y1        10   20  10  --   --
        # y2        -- None  20  10  NaN
        # -> sum    10   20  30  10  NaN
        # -> mean   10   20  15  10  NaN

        p1 = ([1, 2, 3],
              [10, 20, 10])
        p2 = {'x': [2, 3, 4, 7],
              'y': np.asarray([None, 20, 10, nan])}

        x, Y = xy_pair_matrix([p1, p2])

        self.assertTrue(np.all(x == np.asarray([1, 2, 3, 4, 7])))

        self.assertEqual(Y.shape, (5, 2))

        Y_expected = np.asarray([[10.0, nan], [20.0, nan], [10.0, 20.0], [nan, 10.0], [nan, nan]])
        self.assertTrue(np.array_equal(Y, Y_expected, equal_nan=True))
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', r'Mean of empty slice')
            y_sum = np.nansum(Y, axis=1)
            y_mean = np.nanmean(Y, axis=1)
        # Numpy <= 1.90 returns nansum([NaN, NaN]) == NaN
        self.assertTrue(np.array_equal(y_sum, np.asarray([10, 20, 30, 10, 0]), equal_nan=True))
        self.assertTrue(np.array_equal(y_mean, np.asarray([10, 20, 15, 10, np.nan]), equal_nan=True))

    def test_fid2pixelIndices(self):

        # create test datasets
        rl = QgsRasterLayer(enmap.as_posix())
        vl = QgsVectorLayer(enmap_pixel.as_posix())

        self.assertTrue(rl.isValid())
        self.assertTrue(vl.isValid())
        DIR_TEST = self.createTestOutputDirectory()
        burned, no_data = fid2pixelindices(rl, vl,
                                           all_touched=True)

        self.assertIsInstance(no_data, int)

        pathDst = DIR_TEST / 'fid2{}.tif'.format(pathlib.Path(vl.source().split('|')[0]).name)

        gdal_array.SaveArray(burned, pathDst.as_posix(), prototype=enmap.as_posix())
        self.assertIsInstance(burned, np.ndarray)
        fidsA = set(vl.allFeatureIds())
        fidsB = set([fid for fid in np.unique(burned) if fid != no_data])
        self.assertEqual(fidsA, fidsB)
        self.assertEqual(burned.shape[1], rl.width())
        self.assertEqual(burned.shape[0], rl.height())

    def test_SelectMapLayerDialog(self):

        p = QgsProject()
        lyr1 = TestObjects.createRasterLayer()
        lyr2 = TestObjects.createVectorLayer()
        p.addMapLayers([lyr1, lyr2])
        d = SelectMapLayerDialog()
        d.setProject(p)

        self.showGui()

    def test_nodeXmlString(self):

        doc = QDomDocument()
        root: QDomElement = doc.createElement('root')
        doc.appendChild(root)
        n0: QDomElement = doc.createElement('node0')

        n1: QDomElement = doc.createElement('node1')
        n2: QDomElement = doc.createElement('node11')
        n3: QDomElement = doc.createElement('node12')

        n0.appendChild(n1)
        n1.appendChild(n2)
        n1.appendChild(n3)
        root.appendChild(n0)

        xml1 = nodeXmlString(n1)
        s = ""

    def test_raster_block_interator(self):

        if True:
            ext = QgsRectangle(QgsPointXY(0, 10000),
                               QgsPointXY(50000, 0))

            iterator = ExtentTileIterator(ext, ext.width() / 4, ext.height() / 5)

            parts = []
            for i, ext2 in enumerate(iterator):
                self.assertIsInstance(ext2, QgsRectangle)
                self.assertTrue(ext.contains(ext2))
                self.assertEqual(iterator.n, i + 1)
                parts.append(QgsGeometry.fromRect(ext2))
            p = QgsGeometryParameters()
            p.setGridSize(10)
            union = QgsGeometry.unaryUnion(parts, p).simplify(0)
            ext3 = union.boundingBox()
            self.assertEqual(ext, ext3)

        lyr = QgsRasterLayer(enmap.as_posix())
        ARRAY = rasterArray(lyr, bands=[1])
        self.assertEqual(ARRAY.shape, (1, lyr.height(), lyr.width()))
        ARRAY = ARRAY.reshape((np.prod(ARRAY.shape)))

        uA = np.unique(ARRAY)

        M2P = QgsMapToPixel(lyr.rasterUnitsPerPixelX(),
                            lyr.extent().center().x(),
                            lyr.extent().center().y(),
                            lyr.width(), lyr.height(), 0)
        # regardless of the tile size, i.e. sampling rate, we should be able to
        # reconstruct all pixels of a raster image
        for i, tileSize in enumerate([26, 29,  # sub-pixel size
                                      30,  # exact pixel size
                                      33,  # lager than pixel
                                      60,  # pixel size multiply
                                      500,  # larger than image
                                      ]):
            iterator = ExtentTileIterator(lyr.extent(), tileSizeX=tileSize, tileSizeY=tileSize)
            parts = []
            for j, ext in enumerate(iterator):
                arr = rasterArray(lyr, rect=ext, bands=[1])

                if arr is None:
                    continue

                parts.append(arr.reshape((np.prod(arr.shape))))
            arr = np.concatenate(parts, axis=0)
            ua = np.unique(arr)
            self.assertTrue(np.array_equal(uA, ua))
            self.assertEqual(len(ARRAY), len(arr), msg=f'Invalid output with tileSize={tileSize}')

    def test_MapGeometryToPixel_Rotated(self):

        path = pathlib.Path(r'D:\Repositories\QGIS\tests\testdata\raster\rotated_rgb.png')

        if path.is_file():
            rl = QgsRasterLayer(path.as_posix())
            self.assertTrue(rl.isValid())

            ds: gdal.Dataset = gdal.Open(path.as_posix())

            gt = ds.GetGeoTransform()

            array = rasterArray(rl)
            mg2p = MapGeometryToPixel.fromRaster(rl)

            g = QgsGeometry.fromRect(rl.extent())
            mg2p.geometryPixelPositions(g)
            ay, ax = mg2p.geometryPixelPositions(g)
            all_profiles = array[:, ay, ax]
            self.assertEqual(all_profiles.shape, (rl.bandCount(), rl.width() * rl.height()))
            s = ""

    def test_MapGeometryToPixel(self):
        rl = QgsRasterLayer(enmap.as_posix())
        vlPoly = QgsVectorLayer(enmap_multipolygon.as_posix())
        vlPoint = QgsVectorLayer(enmap_pixel.as_posix())
        vlPointMulti = QgsVectorLayer(enmap_multipoint.as_posix())

        self.assertTrue(rl.crs() != vlPoly.crs())

        for mg2p in [MapGeometryToPixel.fromRaster(rl),
                     MapGeometryToPixel.fromExtent(rl.extent(),
                                                   rl.width(), rl.height(),
                                                   crs=rl.crs())
                     ]:
            ul = mg2p.px2geo(0, 0)
            self.assertEqual(ul.x(), rl.extent().xMinimum())
            self.assertEqual(ul.y(), rl.extent().yMaximum())

            lr = mg2p.px2geo(rl.width(), rl.height())
            self.assertEqual(lr.x(), rl.extent().xMaximum())
            self.assertEqual(lr.y(), rl.extent().yMinimum())

            self.assertEqual(rl.width(), mg2p.nSamples())
            self.assertEqual(rl.height(), mg2p.nLines())

        dp: QgsRasterDataProvider = rl.dataProvider()
        with MapGeometryToPixel.fromRaster(rl) as mg2p:
            array = rasterArray(rl)
            request = QgsFeatureRequest()
            request.setDestinationCrs(rl.crs(), QgsProject.instance().transformContext())
            for f in vlPoint.getFeatures(request):
                f: QgsFeature
                ay, ax = mg2p.geometryPixelPositions(f)
                by, bx = mg2p.geometryPixelPositions(f, burn_points=True)

                self.assertTrue(len(ay) == 1,
                                msg='Point geometry should return single pixel only')

                self.assertTrue(np.array_equal(ax, bx))
                self.assertTrue(np.array_equal(ay, by))

                profile1 = array[:, ay, ax][:, 0].astype(float).tolist()
                pt: QgsPointXY = f.geometry().asPoint()
                results = dp.identify(pt, QgsRaster.IdentifyFormatValue).results()
                profile2 = list(results.values())
                self.assertListEqual(profile1, profile2,
                                     msg=f'Wrong profile for point fid {f.id()}')

            for f in vlPointMulti.getFeatures(request):
                f: QgsFeature
                ay, ax = mg2p.geometryPixelPositions(f, all_touched=True)
                profiles = array[:, ay, ax]
                npx_ref = f.attribute('n_px')
                self.assertEqual(profiles.shape, (rl.bandCount(), npx_ref))

            for f in vlPoly.getFeatures(request):
                f: QgsFeature
                name = f.attribute('name')
                ay, ax = mg2p.geometryPixelPositions(f, all_touched=True)

                #  compare returned pixel indices with hand labeled in px_x and px_y
                ref_x = [int(p) for p in f.attribute('px_x').split(',')]
                ref_y = [int(p) for p in f.attribute('px_y').split(',')]

                # number of touched pixels
                n_px = f.attribute('n_px')
                self.assertEqual(n_px, len(ay),
                                 msg=f'Wrong number of touched pixel for feature "{name}"')
                for v in ax.tolist():
                    self.assertTrue(v in ref_x)
                for v in ay.tolist():
                    self.assertTrue(v in ref_y)

                npx_nat = f.attribute('n_px_nat')
                if isinstance(npx_nat, int):
                    ay, ax = mg2p.geometryPixelPositions(f, all_touched=False)
                    profiles = array[:, ay, ax]
                    self.assertEqual(profiles.shape, (rl.bandCount(), npx_nat))
                pass

    def test_snapGeoCoordinates(self):

        rl = QgsRasterLayer(enmap.as_posix())
        ext = rl.extent()
        m2p = QgsMapToPixel(rl.rasterUnitsPerPixelX(),
                            ext.center().x(), ext.center().y(),
                            rl.width(), rl.height(),
                            0)
        ul1 = QgsPointXY(ext.xMinimum(), ext.yMaximum())
        ul2 = snapGeoCoordinates([ul1], m2p)[0]
        self.assertEqual(ul1.x(), ul2.x() - 0.5 * rl.rasterUnitsPerPixelX())
        self.assertEqual(ul1.y(), ul2.y() + 0.5 * rl.rasterUnitsPerPixelY())

    def test_rasterize_features(self):

        rl = QgsRasterLayer(enmap.as_posix())
        dp: QgsRasterDataProvider = rl.dataProvider()
        vlPoly = QgsVectorLayer(enmap_multipolygon.as_posix())
        c = rl.extent().center()
        M2P = QgsMapToPixel(rl.rasterUnitsPerPixelX(),
                            c.x(), c.y(),
                            rl.width(), rl.height(), 0)

        ARRAY = rasterArray(rl)

        def checkPixelValues(f: QgsFeature, array: np.ndarray, md: Dict):
            self.assertEqual(array.ndim, 2)
            geo = md['geo']
            px = md['px']
            self.assertIsInstance(f, QgsFeature)
            nb, npx = array.shape
            self.assertEqual(npx, len(geo))
            self.assertEqual(npx, len(px))

            self.assertEqual(nb, rl.bandCount())

            for i in range(npx):
                cg: QgsPointXY = geo[i]
                cp: QPoint = px[i]

                arr1 = array[:, i]
                arr2 = ARRAY[:, cp.y(), cp.x()]
                ires: QgsRasterIdentifyResult = dp.identify(cg, QgsRaster.IdentifyFormatValue).results()
                arr3 = np.asarray(list(ires.values()))

                if not np.array_equal(arr1, arr2):
                    s = ""
                self.assertTrue(np.array_equal(arr1, arr2))
                self.assertTrue(np.array_equal(arr1, arr3))

        if True:
            feedback = QgsProcessingFeedback()

            vl = QgsVectorLayer(landcover.as_posix())
            for (f, array, md) in rasterizeFeatures(vl, rl, feedback=feedback):
                self.assertIsInstance(f, QgsFeature)
                self.assertIsInstance(array, np.ndarray)
                self.assertIsInstance(md, dict)
                self.assertEqual(array.ndim, 2)
                self.assertEqual(array.shape[0], rl.bandCount())
                checkPixelValues(f, array, md)

            self.assertEqual(feedback.progress(), 100)

        if True:
            feedback = QgsProcessingFeedback()

            vlPoints = QgsVectorLayer(enmap_pixel.as_posix())
            for (f, array, md) in rasterizeFeatures(vlPoints, rl, blockSize=4, feedback=feedback):
                self.assertIsInstance(f, QgsFeature)
                self.assertIsInstance(array, np.ndarray)
                self.assertIsInstance(md, dict)
                self.assertEqual(array.ndim, 2)
                self.assertEqual(array.shape, (rl.bandCount(), 1))
                checkPixelValues(f, array, md)

            self.assertEqual(feedback.progress(), 100)

        if True:
            feedback = QgsProcessingFeedback()
            for (f, array, md) in rasterizeFeatures(vlPoly, rl, blockSize=4, feedback=feedback):
                self.assertIsInstance(f, QgsFeature)
                self.assertIsInstance(array, np.ndarray)
                self.assertIsInstance(md, dict)
                self.assertEqual(array.ndim, 2)
                self.assertEqual(array.shape[0], rl.bandCount())
                checkPixelValues(f, array, md)

            self.assertEqual(feedback.progress(), 100)

    def test_block_size(self):

        ds = TestObjects.createRasterDataset(200, 300, 100, eType=gdal.GDT_Int16)

        for cache in [10,
                      2 * 100,
                      10 * 2 ** 20,
                      100 * 2 ** 20]:
            bs = optimize_block_size(ds, cache=cache)
            self.assertIsInstance(bs, list)
            self.assertTrue(len(bs) == 2)
            self.assertTrue(0 < bs[0] <= ds.RasterXSize)
            self.assertTrue(0 < bs[1] <= ds.RasterYSize)
            s = ""

    def test_osrSpatialReference(self):

        for input in ['EPSG:32633',
                      QgsCoordinateReferenceSystem('EPSG:32633')
                      ]:
            srs = osrSpatialReference(input)
            self.assertIsInstance(srs, osr.SpatialReference)
            self.assertTrue(srs.Validate() == ogr.OGRERR_NONE)

    def test_pixelSpatialCoordinates(self):

        lyrR = TestObjects.createRasterLayer()

        upperLeft = px2spatialPoint(lyrR, QPoint(0, 0))
        lowerRight = px2spatialPoint(lyrR, QPoint(lyrR.width() - 1, lyrR.height() - 1))
        resX = lyrR.extent().width() / lyrR.width()
        resY = lyrR.extent().height() / lyrR.height()
        self.assertIsInstance(upperLeft, SpatialPoint)

        self.assertAlmostEqual(upperLeft.x(), lyrR.extent().xMinimum() + 0.5 * resX, 5)
        self.assertAlmostEqual(upperLeft.y(), lyrR.extent().yMaximum() - 0.5 * resY, 5)
        self.assertAlmostEqual(lowerRight.x(), lyrR.extent().xMaximum() - 0.5 * resX, 5)
        self.assertAlmostEqual(lowerRight.y(), lyrR.extent().yMinimum() + 0.5 * resY, 5)

        upperLeftPx = spatialPoint2px(lyrR, upperLeft)
        lowerRightPx = spatialPoint2px(lyrR, lowerRight)
        self.assertIsInstance(upperLeftPx, QPoint)
        self.assertEqual(upperLeftPx, QPoint(0, 0))
        self.assertEqual(lowerRightPx, QPoint(lyrR.width() - 1, lyrR.height() - 1))
        s = ""

    def test_SpatialPoint_pixel_positions(self):

        layer = TestObjects.createRasterLayer(ns=10, nl=20, pixel_size=3.0)
        pointA = SpatialPoint(layer.crs(), layer.extent().center())
        pixelA = pointA.toPixelPosition(layer)

        pointB = SpatialPoint(pointA)
        self.assertEqual(pointA, pointB)
        self.assertNotEqual(id(pointA), id(pointB))
        self.assertEqual(pointA.asWkt(), pointB.asWkt())

        self.assertIsInstance(pixelA, QPoint)
        self.assertEqual(pixelA.x(), int(layer.width() * 0.5))
        self.assertEqual(pixelA.y(), int(layer.height() * 0.5))

        pointB = pointA.toCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
        pointA2 = pointB.toCrs(pointA.crs())

        # check raster corners
        e = layer.extent()
        c = layer.crs()
        dx = 0.5 * layer.rasterUnitsPerPixelX()
        dy = 0.5 * layer.rasterUnitsPerPixelY()
        geoCoords = [SpatialPoint(c, e.xMinimum() + dx, e.yMaximum() - dy),  # UL
                     SpatialPoint(c, e.xMaximum() - dx, e.yMaximum() - dy),  # UR
                     SpatialPoint(c, e.xMaximum() - dx, e.yMinimum() + dy),  # LR
                     SpatialPoint(c, e.xMinimum() + dx, e.yMinimum() + dy),  # LL
                     ]
        pxCoords = [QPoint(0, 0),
                    QPoint(layer.width() - 1, 0),
                    QPoint(layer.width() - 1, layer.height() - 1),
                    QPoint(0, layer.height() - 1)
                    ]

        for geoC, pxRef in zip(geoCoords, pxCoords):
            geoLL = geoC.toCrs(QgsCoordinateReferenceSystem('EPSG:4326'))
            pxGeo = geoC.toPixelPosition(layer)
            pxLL = geoLL.toPixelPosition(layer)
            self.assertEqual(pxGeo, pxRef)
            self.assertEqual(pxLL, pxRef)

            geoC2 = SpatialPoint.fromPixelPosition(layer, pxRef)
            resx, resy = layer.rasterUnitsPerPixelX() * 0.5, layer.rasterUnitsPerPixelY() * 0.5
            self.assertTrue(geoC.x() - resx <= geoC2.x() <= geoC.x() + resx)
            self.assertTrue(geoC.y() - resy <= geoC2.y() <= geoC.y() + resy)

        for x, y in zip([0, 1, 1, 0], [0, 0, 1, 1]):
            ptPx = SpatialPoint.fromPixelPosition(layer, x, y).toPixelPosition(layer)
            self.assertEqual(ptPx.x(), x)
            self.assertEqual(ptPx.y(), y)

        pt = SpatialPoint.fromPixelPosition(layer, -0.5, -0.5)
        self.assertFalse(layer.extent().contains(pt))
        px = pt.toPixel(layer)
        self.assertEqual(px, QPoint(-1, -1))
        s = ""
        s = ""

    def test_feature_symbol_scope(self):

        layers = [
            TestObjects.createVectorLayer(wkbType=QgsWkbTypes.NoGeometry),
            TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Point),
            TestObjects.createVectorLayer(wkbType=QgsWkbTypes.Polygon),
            TestObjects.createVectorLayer(wkbType=QgsWkbTypes.LineGeometry),
        ]

        for lyr in layers:
            assert lyr.featureCount() > 0
            renderer = lyr.renderer()

            for f in lyr.getFeatures():
                context = QgsExpressionContextUtils.createFeatureBasedContext(f, f.fields())
                scope1 = featureSymbolScope(f)
                scope2 = featureSymbolScope(f, renderer=renderer)
                scope3 = featureSymbolScope(f, context=context)
                scope4 = featureSymbolScope(f, renderer=renderer, context=context)

                break

    def test_aggregateArray(self):

        a1 = np.asarray([[1, 4, 1],
                         [1, 2, 3]])

        self.assertTrue(np.array_equal(aggregateArray('none', a1), a1))
        REF = [
            ('min', [1, 1]),
            ('max', [4, 3]),
            ('mean', [2, 2]),
            ('median', [1, 2]),
        ]
        for (a, result) in REF:
            aggr = aggregateArray(a, a1, axis=1).tolist()
            self.assertListEqual(aggr, result, msg=f'Wrong result for "{a}"')

    def test_rasterArray(self):

        lyr = QgsRasterLayer(enmap.as_posix())
        dp: QgsRasterDataProvider = lyr.dataProvider()
        ext = lyr.extent()

        resX = lyr.rasterUnitsPerPixelX()
        resY = lyr.rasterUnitsPerPixelY()

        if True:
            array = rasterArray(lyr)
            self.assertIsInstance(array, np.ndarray)
            nb, nl, ns = array.shape
            self.assertEqual(lyr.bandCount(), nb)
            self.assertEqual(lyr.width(), ns)
            self.assertEqual(lyr.height(), nl)

            extP0 = QgsRectangle(ext.xMinimum(), ext.yMaximum(),
                                 ext.xMinimum() + resX,
                                 ext.yMaximum() - resY)
            array = rasterArray(lyr, extP0, bands=[1])
            self.assertEqual(array.shape, (1, 1, 1))

        # cover pixel, but not the pixel center -> None
        extP1a = QgsRectangle(ext.xMinimum() + 0.1 * resX,
                              ext.yMaximum() - 0.1 * resY,
                              ext.xMinimum() + 0.45 * resX,
                              ext.yMaximum() - 0.45 * resY)
        extP1b = QgsRectangle(ext.xMaximum() - 0.1 * resX,
                              ext.yMinimum() + 0.1 * resY,
                              ext.xMaximum() - 0.45 * resX,
                              ext.yMinimum() + 0.45 * resY)

        for e in [extP1a, extP1b]:
            array = rasterArray(lyr, e, bands=[1])
            self.assertTrue(array is None)
            array = rasterArray(lyr, e.center(), bands=[1])
            self.assertIsInstance(array, np.ndarray)
            self.assertEqual(array.shape, (1, 1, 1))

        # cover pixel center -> return values
        c = QgsPointXY(ext.xMinimum() + 0.5 * resX,
                       ext.yMaximum() - 0.5 * resY)

        e = QgsRectangle(c.x() - 0.1 * resX, c.y() + 0.1 * resY,
                         c.x() + 0.1 * resX, c.y() - 0.1 * resY)

        arr1 = list(dp.identify(e.center(), QgsRaster.IdentifyFormatValue).results().values())
        arr2 = rasterArray(lyr, rect=e)
        self.assertIsInstance(arr2, np.ndarray)
        self.assertEqual(arr2.shape, (lyr.bandCount(), 1, 1))
        self.assertListEqual(arr1, arr2.squeeze().tolist())

        arr3 = rasterArray(lyr, rect=e.center())
        self.assertTrue(np.array_equal(arr2, arr3))
        s = ""

        lyrR = TestObjects.createRasterLayer(nb=12)

        ext: QgsRectangle = lyrR.extent()
        points = [QgsPointXY(ext.xMinimum(), ext.yMaximum()),
                  QgsPointXY(ext.xMaximum(), ext.yMaximum()),
                  QgsPointXY(ext.xMaximum(), ext.yMinimum()),
                  QgsPointXY(ext.xMinimum(), ext.yMinimum()),
                  ]

        for n in range(25):
            points.append(QgsPointXY(random.uniform(ext.xMinimum(), ext.xMaximum()),
                                     random.uniform(ext.yMinimum(), ext.yMaximum())))

        for i, p in enumerate(points):
            # create empty rectangle = single point
            rect = QgsRectangle(p.x(), p.y(), p.x(), p.y())
            arr1 = rasterArray(lyrR, rect)
            arr1 = arr1[:, 0, 0].tolist()
            ires: QgsRasterIdentifyResult = lyrR.dataProvider().identify(p, QgsRaster.IdentifyFormatValue).results()
            arr2 = list(ires.values())
            self.assertListEqual(arr1, arr2)

        ext = lyrR.extent()
        ul = SpatialPoint(lyrR.crs(), ext.xMinimum(), ext.yMaximum())
        lr = SpatialPoint(lyrR.crs(), ext.xMaximum(), ext.yMinimum())

        blockB = rasterArray(lyrR, ul=ul, lr=lr)
        blockA = rasterArray(lyrR, ul=QPoint(0, 0), lr=QPoint(lyrR.width() - 1, lyrR.height() - 1))
        blockC = rasterArray(lyrR, rect=QRect(0, 0, lyrR.width(), lyrR.height()))

        ds: gdal.Dataset = gdal.Open(lyrR.source())
        nb = ds.RasterCount
        ns = ds.RasterXSize
        nl = ds.RasterYSize

        block = lyrR.dataProvider().block(1, ext, ns, nl)
        band_array = rasterBlockArray(block)
        self.assertIsInstance(band_array, np.ndarray)
        self.assertTrue(band_array.shape == (nl, ns))

        for block in [blockA, blockB, blockC]:
            self.assertEqual(block.shape, (nb, nl, ns))

        for block in [blockA, blockB]:
            self.assertEqual(lyrR.bandCount(), nb)
            self.assertEqual(block.shape[0], nb)
            for b in range(nb):
                band = block[b, :, :]
                bandG = ds.GetRasterBand(b + 1).ReadAsArray()
                self.assertTrue(np.all(band == bandG))

        lyr1 = QgsRasterLayer(enmap.as_posix(), 'EnMAP')
        lyr2 = QgsRasterLayer(hymap.as_posix(), 'HyMAP')

        for lyr in [lyr1, lyr2]:
            ds: gdal.Dataset = gdal.Open(lyr.source())
            blockGDAL = ds.ReadAsArray()
            blockAll = rasterArray(lyr)
            self.assertTrue(np.all(blockGDAL == blockAll))
            self.assertEqual(blockGDAL.dtype, blockAll.dtype)

    def test_geo_coordinates(self):

        lyrR = TestObjects.createRasterLayer()

        gx1, gy1 = px2geocoordinates(lyrR)
        gx2, gy2 = px2geocoordinates(lyrR, 'EPSG:4326')
        s = ""

    def test_gdalDataset(self):

        ds = TestObjects.createRasterDataset()
        path = ds.GetDescription()
        ds1 = gdalDataset(path)
        self.assertIsInstance(ds1, gdal.Dataset)
        ds2 = gdalDataset(ds1)
        self.assertEqual(ds1, ds2)

    def test_maplayers(self):

        lyr = TestObjects.createRasterLayer()

        url = QUrl.fromLocalFile(lyr.source())

        inputs = [lyr, lyr.source(), gdal.Open(lyr.source()), url]

        for source in inputs:
            lyr = qgsRasterLayer(source)
            self.assertIsInstance(lyr, QgsRasterLayer)

    def test_UnitLookup(self):

        for u in ['nm', 'm', 'km', 'um', 'μm', u'μm']:
            self.assertTrue(UnitLookup.isMetricUnit(u), msg='Not detected as metric unit:{}'.format(u))
            bu = UnitLookup.baseUnit(u)
            self.assertIsInstance(bu, str)
            self.assertTrue(len(bu) > 0)

    def test_bandNames(self):

        ds = TestObjects.createRasterDataset()
        pathRaster = ds.GetDescription()

        validSources = [pathRaster,
                        QgsRasterLayer(pathRaster),
                        gdal.Open(pathRaster)]

        for src in validSources:
            if isinstance(src, QgsRasterLayer):
                self.assertTrue(src.isValid())
            names = displayBandNames(src, leadingBandNumber=True)
            self.assertIsInstance(names, list, msg='Unable to derive band names from {}'.format(src))
            self.assertTrue(len(names) > 0)

    def test_coordinateTransformations(self):

        ds = TestObjects.createRasterDataset(300, 500)
        lyr = QgsRasterLayer(ds.GetDescription())

        self.assertEqual(ds.GetGeoTransform(), layerGeoTransform(lyr))

        self.assertIsInstance(ds, gdal.Dataset)
        self.assertIsInstance(lyr, QgsRasterLayer)
        gt = ds.GetGeoTransform()
        crs = QgsCoordinateReferenceSystem(ds.GetProjection())

        self.assertTrue(crs.isValid())

        geoCoordinateUL = QgsPointXY(gt[0], gt[3])
        shiftToCenter = QgsVector(gt[1] * 0.5, gt[5] * 0.5)
        geoCoordinateCenter = geoCoordinateUL + shiftToCenter
        pxCoordinate = geo2px(geoCoordinateUL, gt)
        pxCoordinate2 = geo2px(geoCoordinateUL, lyr)
        self.assertEqual(pxCoordinate.x(), 0)
        self.assertEqual(pxCoordinate.y(), 0)
        self.assertAlmostEqual(px2geo(pxCoordinate, gt), geoCoordinateCenter)

        self.assertEqual(pxCoordinate, pxCoordinate2)

        spatialPoint = SpatialPoint(crs, geoCoordinateUL)
        pxCoordinate = geo2px(spatialPoint, gt)
        self.assertEqual(pxCoordinate.x(), 0)
        self.assertEqual(pxCoordinate.y(), 0)
        self.assertAlmostEqual(px2geo(pxCoordinate, gt), geoCoordinateUL + shiftToCenter)

    def test_createQgsField(self):

        values = [1, 2.3, 'text',
                  np.int8(1),
                  np.int16(1),
                  np.int32(1),
                  np.int64(1),
                  np.uint8(1),
                  np.uint(1),
                  np.uint16(1),
                  np.uint32(1),
                  np.uint64(1),
                  float,
                  np.float16(1),
                  np.float32(1),
                  np.float64(1),
                  QByteArray(),
                  ]

        for v in values:
            # print('Create QgsField for {}'.format(type(v)))
            field = createQgsField('field', v)
            self.assertIsInstance(field, QgsField)

    def test_appendItemsToMenu(self):
        B = QMenu()

        action = B.addAction('Do something')
        menuA = QMenu()
        appendItemsToMenu(menuA, B)

        self.assertTrue(action in menuA.children())

    def test_value2string(self):

        valueSet = [[1, 2, 3],
                    1,
                    '',
                    None,
                    np.zeros((3, 3,))
                    ]

        for i, values in enumerate(valueSet):
            print('Test {}:{}'.format(i + 1, values))
            s = value2str(values, delimiter=';')
            self.assertIsInstance(s, str)

    def test_savefilepath(self):

        valueSet = ['dsdsds.png',
                    'foo\\\\\\?<>bar',
                    None,
                    r"_bound method TimeSeriesDatum.date of TimeSeriesDatum(2014-01-15,_class 'timeseriesviewer.timeseries.SensorInstrument'_ LS)_.Map View 1.png"
                    ]

        for i, text in enumerate(valueSet):
            s = filenameFromString(text)
            print('Test {}:"{}"->"{}"'.format(i + 1, text, s))
            self.assertIsInstance(s, str)

    def test_selectMapLayersDialog(self):

        lyrR = TestObjects.createRasterLayer()
        lyrV = TestObjects.createVectorLayer()
        layers = [lyrR, lyrV]
        QgsProject.instance().addMapLayers(layers)
        d = SelectMapLayersDialog()
        d.addLayerDescription('Any Type', QgsMapLayerProxyModel.All)
        layers2 = d.mapLayers()
        self.assertIsInstance(layers2, list)
        self.assertTrue(len(layers2) == 1)
        for lyr in layers2:
            self.assertTrue(lyr in layers)

        d.addLayerDescription('A Vector Layer', QgsMapLayerProxyModel.VectorLayer)
        d.addLayerDescription('A Raster Layer', QgsMapLayerProxyModel.RasterLayer)

        self.showGui(d)

        QgsProject.instance().removeAllMapLayers()

    def test_picture_config(self):

        # relative paths
        expected = {'DocumentViewer': 1, 'DocumentViewerHeight': 0, 'DocumentViewerWidth': 300, 'FileWidget': True,
                    'FileWidgetButton': False, 'FileWidgetFilter': '',
                    'PropertyCollection': {
                        'name': NULL,
                        'type': 'collection',
                        'properties': {
                            'propertyRootPath': {
                                'active': True,
                                'expression': "layer_property(@layer, 'path')",
                                'type': 3}
                        },

                    },
                    'RelativeStorage': 2,
                    'StorageAuthConfigId': NULL,
                    'StorageMode': 0,
                    'StorageType': NULL}
        self.assertEqual(expected, create_picture_viewer_config(True, 300))

        # absolute paths
        expected = {'DocumentViewer': 1, 'DocumentViewerHeight': 0, 'DocumentViewerWidth': 300, 'FileWidget': True,
                    'FileWidgetButton': False, 'FileWidgetFilter': '',
                    'PropertyCollection': {'name': NULL,
                                           'properties': {
                                               'propertyRootPath': {
                                                   'active': False,
                                                   'type': 1,
                                                   'val': NULL}},
                                           'type': 'collection'},
                    'RelativeStorage': 0, 'StorageAuthConfigId': NULL, 'StorageMode': 0, 'StorageType': NULL}
        self.assertDictEqual(expected, create_picture_viewer_config(False, 300))

    def test_defaultBands(self):

        ds = TestObjects.createRasterDataset(nb=10)
        self.assertIsInstance(ds, gdal.Dataset)

        self.assertListEqual([1, 2, 3], defaultBands(ds))
        self.assertListEqual([1, 2, 3], defaultBands(ds.GetDescription()))

        ds.SetMetadataItem('default bands', '{4,3,1}', 'ENVI')
        self.assertListEqual([4, 3, 1], defaultBands(ds))

        ds.SetMetadataItem('default_bands', '{4,3,1}', 'ENVI')
        self.assertListEqual([4, 3, 1], defaultBands(ds))

    def test_relativePath(self):

        refDir = '/data/foo/'
        absPath = '/data/foo/bar/file.txt'
        relPath = relativePath(absPath, refDir).as_posix()
        self.assertEqual(relPath, 'bar/file.txt')

        if os.sep == '\\':
            refDir = r'C:\data\foo'
            absPath = r'C:\data\foo\bar\file.txt'
            relPath = relativePath(absPath, refDir)
            self.assertEqual(relPath.as_posix(), 'bar/file.txt')

            refDir = r'D:\data\foo'
            absPath = r'C:\data\foo\bar\file.txt'
            relPath = relativePath(absPath, refDir)
            self.assertEqual(relPath, pathlib.Path(absPath))
        else:

            refDir = '/data/foo/bar/sub/sub/sub'
            absPath = '/data/foo/bar/file.txt'
            relPath = relativePath(absPath, refDir)
            self.assertEqual(relPath.as_posix(), '../../../file.txt')
        # self.assertEqual((pathlib.Path(refDir) / relPath).resolve(), pathlib.Path(absPath))

    def test_nextColor(self):

        c = QColor('#ff012b')
        for i in range(500):
            c = nextColor(c, mode='con')
            self.assertIsInstance(c, QColor)
            self.assertTrue(c.name() != '#000000')

        c = QColor('black')
        for i in range(500):
            c = nextColor(c, mode='cat')
            self.assertIsInstance(c, QColor)
            self.assertTrue(c.name() != '#000000')


if __name__ == "__main__":
    unittest.main(buffer=False)
