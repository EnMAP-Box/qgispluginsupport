import unittest, pathlib
import xml.etree.ElementTree as ET
from qps.testing import start_app
from qps.resources import *
from qps import QPS_RESOURCE_FILE

class ResourceTests(unittest.TestCase):

    def test_qrc(self):

        pathQRC = pathlib.Path(__file__).parents[1] / 'qps' / 'qpsresources.qrc'
        qrcDir = pathQRC.parent
        self.assertTrue(pathQRC.is_file())


        tree = ET.parse(pathQRC)
        root = tree.getroot()
        self.assertEqual(root.tag, 'RCC')
        for child in root:
            if child.tag == 'qresource':
                prefix = child.attrib['prefix']
                for fileTag in child:
                    if fileTag.tag == 'file':
                        resource_path = qrcDir / pathlib.Path(fileTag.text)
                        resource_uri = ':{}/{}'.format(prefix, fileTag.text)
                        self.assertTrue(resource_path.is_file(), msg='File does not exist: {}'.format(resource_path))

    @unittest.skipIf(not QPS_RESOURCE_FILE.is_file(), '{} does not exist'.format(QPS_RESOURCE_FILE))
    def test_rc(self):
        from qgis.PyQt.QtWidgets import QWidget
        from qgis.PyQt.QtGui import QIcon

        app = start_app(resources=[QPS_RESOURCE_FILE])

        r = ':qps/ui/icons/speclib.svg'
        self.assertIsInstance(r, str)
        resources = list(scanResources())

        self.assertTrue(r in resources, '"{}" not loaded to resource system'.format(r))
        w = QWidget()
        w.setWindowIcon(QIcon(r))
        w.show()

    def test_resource_browser(self):

        app = start_app(resources=[QPS_RESOURCE_FILE])

        B = ResourceBrowser()

        B.show()

        app.exec_()
        if not os.environ.get('CI'):
            app.exec_()

if __name__ == '__main__':

    unittest.main()

