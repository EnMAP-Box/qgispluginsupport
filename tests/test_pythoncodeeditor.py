import unittest

from qgis.core import QgsFeature
from qps.editors.pythoncodeeditor import PythonCodeWidget, PythonCodeDialog
from qps.testing import TestCase, start_app, TestObjects

start_app()


class PythonCodeEditorTestCases(TestCase):

    def test_dialog(self):
        lyr = TestObjects.createVectorLayer()
        lyr.setDisplayExpression("format('%1 %2', $id, \"level_2\")")
        w = PythonCodeDialog()
        w.setHelpText('<h1>Modify profile values</h1>'
                      'Set y to modify the array of profile values<br>'
                      'Set x to modify the array of x values')
        w.codeEditor().setText('# b(1)')
        w.setHelpText(None)

        s = ""
        # w.setCode('b(1)')
        # w.setHelpText('<h1>This is a help text</h1>')

        tt = 'More info on code status'

        def onCodeChanged(d: dict):
            code: str = d[w.VALKEY_CODE]
            feature: QgsFeature = d[w.VALKEY_FEATURE]
            self.assertIsInstance(code, str)
            self.assertIsInstance(feature, QgsFeature)
            attributes = feature.attributeMap()

            # 1. Compile code
            code = ['import numpy as np', code]
            error = None
            compiled_code = None
            try:
                compiled_code = compile('\n'.join(code), f'<band expression: "{code}">', 'exec')
            except Exception as ex:
                error = str(ex)

            if not error:
                # 2. execute code
                try:
                    kwds = {'f': attributes.copy()}

                    exec(compiled_code, kwds)
                    assert 'y' in kwds, 'Missing y in kwds'

                except Exception as ex:
                    error = str(ex)
            d[w.VALKEY_ERROR] = error

            if error:
                d[w.VALKEY_PREVIEW_TEXT] = '<b><span style="color:red">error</span></b>'
                d[w.VALKEY_PREVIEW_TOOLTIP] = f'<span style="color:red">{error}</span>'
            else:
                results = kwds['y']
                d[w.VALKEY_PREVIEW_TEXT] = f'{results}'
                d[w.VALKEY_PREVIEW_TOOLTIP] = f'Reuslting value: {results}'
                pass

        w.validationRequest.connect(onCodeChanged)
        w.setLayer(lyr)

        # epw.setExpressionText('b(1)')
        self.showGui(w)

    def test_PythonExpressionWidget(self):
        w = PythonCodeWidget()

        def onValidationRequest(data: dict):
            expr = data.get('expression')
            self.assertIsInstance(expr, str)

        w.validationRequest.connect(onValidationRequest)
        w.codeChanged.connect(lambda expr: print(f"Expression changed: {expr}"))

        self.showGui(w)

    def test_validation(self):

        is_ok = ['foo', 'broken"python', '1+3']
        errMsg = 'MyError'

        def onValidateRequest(data: dict):

            expr = data.get('expression')
            self.assertIsInstance(expr, str)
            self.assertTrue(data['is_valid'] is None)
            self.assertTrue(data['error'] is None)

            data['is_valid'] = expr in is_ok
            if expr not in is_ok:
                data['error'] = errMsg

        w = PythonCodeWidget()
        w.validationRequest.connect(onValidateRequest)
        w.setCode('1+3')
        b, err = w.isValidExpression()
        self.assertTrue(b and err is None)

        w.setCode('foo"')
        b, err = w.isValidExpression()
        s = ""
        self.assertTrue(b is False and isinstance(err, str))

        w.setCode('foo')

        for expr in ['foo', '1+2', 'broken"python']:
            w.setCode(expr)
            b, err = w.isValidExpression()
            if expr in is_ok:
                self.assertTrue(b and err is None)
            else:
                self.assertTrue(b is False and err == errMsg)


if __name__ == '__main__':
    unittest.main()
