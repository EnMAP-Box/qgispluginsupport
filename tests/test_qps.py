"""
Tests to ensure repository structure
"""

import pathlib
import re
import unittest


DIR_QPS = pathlib.Path(__file__).parents[1] / 'qps'


class ResourceTests(unittest.TestCase):

    def test_testdata(self):

        import qpstestdata

        path_keys = [k for k in qpstestdata.__dict__.keys()
                     if not k.startswith('__') and k not in ['pathlib']]
        for k in path_keys:
            path = pathlib.Path(getattr(qpstestdata, k))
            if k.startswith('DIR'):
                self.assertTrue(path.is_dir(), msg=f'Unable to find directory "{k}" = {path}')
            else:
                self.assertTrue(path.is_file(), msg=f'Unable to find file "{k}" = {path}')

    def test_imports(self):
        """
        This test ensures that all imports of qps modules are relative.
        """
        self.assertTrue(DIR_QPS.is_dir())

        from qps.utils import file_search

        rxTest1 = re.compile(r'^ *from qps(\..*)? import.*')
        rxTest2 = re.compile(r'^ *import qps(\..*)?')

        self.assertTrue(rxTest1.search('from qps import xyz'))
        self.assertTrue(rxTest1.search('from qps.xyz import xyz'))
        self.assertTrue(rxTest2.search('import qps'))
        self.assertTrue(rxTest2.search('import qps.xyz'))

        rxTest3 = re.compile(r'(from|import) qgis[.]_[^3]+')

        errors = []
        for path in file_search(DIR_QPS, '*.py', recursive=True):
            path = pathlib.Path(path)
            with open(path, 'r', encoding='utf-8') as f:
                lastLine = None
                for i, line in enumerate(f.readlines()):
                    if rxTest3.search(line):
                        errors.append(f'File "{path}", line {i + 1}, "{line.strip()}"')
                    elif rxTest1.search(line) or rxTest2.search(line):
                        if path.name == 'utils.py' and rxTest2.search(line):
                            continue
                        if not (lastLine and 'except ImportError:' in lastLine):
                            errors.append(f'File "{path}", line {i + 1}, "{line.strip()}"')
                    lastLine = line
        self.assertTrue(len(errors) == 0, msg=f'{len(errors)} Absolute imports:\n' + '\n'.join(errors))


if __name__ == '__main__':
    unittest.main(buffer=False)
