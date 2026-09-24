import unittest

from qgis.core import QgsExpression, QgsExpressionContext, QgsProject

from qps.expressionfunctions import ReadSpectralProfile
from qps.testing import start_app, TestCase
from qps.utils import file_search
from qpstestdata import DIR_ASD_BIN, DIR_SVC, DIR_SED

start_app()


class ReadSpectralProfileTests(TestCase):
    def test_read_spectral_profile(self):
        f = self.registerFunction(ReadSpectralProfile())
        self.assertIsInstance(f, ReadSpectralProfile)
        context = QgsExpressionContext()

        asd_files = list(file_search(DIR_ASD_BIN, '*.asd'))
        svc_files = list(file_search(DIR_SVC, '*.sig'))
        sed_files = list(file_search(DIR_SED, '*.sed'))

        for file in [asd_files[0], svc_files[0], sed_files[0]]:
            exp = QgsExpression(f"{f.NAME}('{file}')")
            self.assertTrue(exp.prepare(context), msg=exp.parserErrorString())
            data = exp.evaluate(context)
            self.assertTrue(exp.evalErrorString() == '', msg=exp.evalErrorString())
            self.assertIsInstance(data, dict)

        QgsProject.instance().removeAllMapLayers()

    def test_read_spectral_profile_with_null(self):
        f = ReadSpectralProfile()
        self.registerFunction(f)

        context = QgsExpressionContext()

        exp = QgsExpression(f"{f.NAME}(NULL, 'asd')")
        self.assertTrue(exp.prepare(context), msg=exp.parserErrorString())
        result = exp.evaluate(context)
        self.assertTrue(result is None)

        QgsProject.instance().removeAllMapLayers()

    def test_read_spectral_profile_with_missing_file(self):
        f = ReadSpectralProfile()
        self.registerFunction(f)

        context = QgsExpressionContext()

        exp = QgsExpression(f"{f.NAME}('/path/to/missing/file.asd')")
        self.assertTrue(exp.prepare(context), msg=exp.parserErrorString())
        result = exp.evaluate(context)
        self.assertTrue(result is None)
        self.assertTrue(exp.evalErrorString() != '', msg='Should have error for missing file')

        QgsProject.instance().removeAllMapLayers()


if __name__ == '__main__':
    unittest.main()
