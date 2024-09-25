import datetime
import unittest

from PyQt5.QtCore import QDate, QDateTime, QTime
from osgeo.gdal import UseExceptions

from qgis.core import QgsField, QgsFields, QgsProject, QgsVectorDataProvider, QgsVectorFileWriter, QgsVectorLayer, edit
from qps.fieldvalueconverter import GenericFieldValueConverter, GenericPropertyTransformer, NATIVE_TYPES, \
    collect_native_types
from qps.qgisenums import QMETATYPE_QDATE, QMETATYPE_QDATETIME, QMETATYPE_QSTRING, \
    QMETATYPE_QTIME, \
    QMETATYPE_QVARIANTMAP
from qps.testing import TestCase, TestObjects

# start_app()
UseExceptions()
s = ""


class GenericFieldValueConverterTests(TestCase):
    def test_something(self):
        self.assertEqual(True, False)  # add assertion here

    def test_GenericPropertyTransformer(self):

        dtgPy = datetime.datetime.now()
        dtgQt = QDateTime.currentDateTime()

        # convert to QDateTime
        for v in [str(dtgPy), dtgPy, dtgPy.date(),
                  dtgQt, dtgQt.toString(), dtgQt.date()]:
            result = GenericPropertyTransformer.toDateTime(v)
            self.assertIsInstance(result, QDateTime, msg=f'Unable to convert {v} to QDateTime')

        # convert to QDate
        for v in [str(dtgPy), dtgPy, dtgPy.date(),
                  dtgQt, dtgQt.toString(), dtgQt.date(), dtgQt.date().toString()]:
            result = GenericPropertyTransformer.toDate(v)
            self.assertIsInstance(result, QDate, msg=f'Unable to convert {v} to QDate')

        # convert to QTime
        for v in [str(dtgPy), dtgPy, dtgPy.time(), dtgPy.time().isoformat(),
                  dtgQt, dtgQt.time(), dtgQt.toString(), dtgQt.time().toString()]:
            result = GenericPropertyTransformer.toTime(v)
            self.assertIsInstance(result, QTime, msg=f'Unable to convert {v} to QTime')

    def test_collect_native_types(self):

        ntypinfo = collect_native_types()
        self.assertIsInstance(ntypinfo, dict)
        for p in ['CSV', 'GPKG', 'GeoJSON', 'ESRI Shapefile', 'memory']:
            self.assertTrue(p in ntypinfo)
            for info in ntypinfo[p]:
                self.assertIsInstance(info, QgsVectorDataProvider.NativeType)

    def test_findFileTypes(self):

        # QGIS 3.38
        # type 8 = QVariantMap
        # type 10 = QString
        # JSON Field: type = 8, subtype = 10, typeName = 'JSON'
        # map Field: type = 8, subtype = 0, typeName = 'map'
        #

        fields = QgsFields()
        fields.append(QgsField('json', type=QMETATYPE_QVARIANTMAP, subType=QMETATYPE_QSTRING, typeName='JSON'))
        fields.append(QgsField('map', type=QMETATYPE_QVARIANTMAP, subType=0, typeName='map'))
        fields.append(QgsField('text', type=QMETATYPE_QSTRING))

        for driverName in ['memory', 'GeoJSON', 'GPKG', 'ESRI Shapefile', 'CSV', 'SQLite',
                           QgsVectorFileWriter.driverForExtension('.kml')
                           ]:
            targetFields = GenericFieldValueConverter.compatibleTargetFields(fields, driverName)
            self.assertIsInstance(targetFields, QgsFields)
            nativeTypes = NATIVE_TYPES[driverName]

            for f in targetFields:
                found = False
                for t in nativeTypes:
                    if (f.type() == t.mType and
                            f.subType() == t.mSubType and
                            f.typeName() == t.mTypeName):
                        found = True
                        break
                self.assertTrue(found, msg=f'Field {f} not compatible with native types of driver "{driverName}"')

    def test_findsuitableFieldTypes(self):

        lyr: QgsVectorLayer = TestObjects.createSpectralLibrary(n=2)
        with edit(lyr):
            lyr.addAttribute(QgsField('datetime', type=QMETATYPE_QDATETIME))
            lyr.addAttribute(QgsField('time', type=QMETATYPE_QTIME))
            lyr.addAttribute(QgsField('date', type=QMETATYPE_QDATE))
            lyr.addAttribute(QgsField('map', type=QMETATYPE_QVARIANTMAP))

            dtg = QDateTime.currentDateTime()
            f1 = lyr.getFeature(lyr.allFeatureIds()[0])
            f1.setAttribute('datetime', dtg)
            f1.setAttribute('time', dtg.time())
            f1.setAttribute('date', dtg.date())
            f1.setAttribute('map', dict(foo='bar', number=42))

            self.assertTrue(lyr.updateFeature(f1))

        DIR_TEST = self.createTestOutputDirectory()

        for ext in ['.gpkg',
                    '.shp',
                    '.geojson',
                    '.csv']:

            path = DIR_TEST / f'example{ext}'

            driver = QgsVectorFileWriter.driverForExtension(ext)

            dstFields = GenericFieldValueConverter.compatibleTargetFields(lyr.fields(), driver)
            self.assertIsInstance(dstFields, QgsFields)
            for f in dstFields:
                self.assertIsInstance(f, QgsField)

            options = QgsVectorFileWriter.SaveVectorOptions()
            options.actionOnExistingFile = QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteFile
            # options.feedback = feedback
            # options.datasourceOptions = datasourceOptions
            # options.layerOptions = layerOptions
            options.fileEncoding = 'UTF-8'
            options.skipAttributeCreation = False
            options.driverName = driver

            converter = GenericFieldValueConverter(lyr.fields(), dstFields)
            options.fieldValueConverter = converter

            success, msg, lyrpath, lyrname = QgsVectorFileWriter.writeAsVectorFormatV3(lyr, path.as_posix(),
                                                                                       transformContext=QgsProject.instance().transformContext(),
                                                                                       options=options,
                                                                                       )

            self.assertEqual(success, QgsVectorFileWriter.WriterError.NoError, msg=f'{path.name}: {msg}')
            s = ""


if __name__ == '__main__':
    unittest.main()
