# QGIS Plugin Support (QPS) 
[![❄ Flake8](https://github.com/EnMAP-Box/qgispluginsupport/actions/workflows/flake8.yml/badge.svg)](https://github.com/EnMAP-Box/qgispluginsupport/actions/workflows/flake8.yml)
[![Unit Tests](https://github.com/EnMAP-Box/qgispluginsupport/actions/workflows/python-tests.yml/badge.svg?branch=master)](https://github.com/EnMAP-Box/qgispluginsupport/actions/workflows/python-tests.yml)

The QGIS Plugin Support (QPS) library helps to develop QGIS plugins specifically for remote sensing applications.

This includes, for example
- Remote sensing specific metadata handling
- Spectral Libraries
- Interactive plotting
- Tools to test python code that uses the QGIS API

QPS is designed as python package that can be included as subpackage of other QGIS python plugins. This  


QPS is used in other projects, for example:
QPS is used in other project like:

EnMAP-Box https://bitbucket.org/hu-geomatics/enmap-box

EO Time Series Viewer https://bitbucket.org/jakimowb/eo-time-series-viewer

Virtual Raster Builder https://bitbucket.org/jakimowb/virtual-raster-builder

## Code Design

Ideally, QPS becomes obsolete by providing every feature  every feature  

## Installation ##

### Include as subtree

Add QPS as a substree:

   git subtree add --prefix enmapbox/qgispluginsupport git@github.com:EnMAP-Box/qgispluginsupport.git master

Push updates (replace with your fork):

   git subtree add --prefix enmapbox/qgispluginsupport git@github.com:EnMAP-Box/qgispluginsupport.git myupdates

### Copy and paste

1. Copy the qgs folder into your source code, e.g. ``mymodule/qps``, and ensure that the Qt resource files are compiled:

    ```python
    from mymodule.qps.setup import compileQPSResources
    compileQPSResources()
     ```

2. QPS uses the Qt resource system, e.g. to access icons. This requires to convert the ``qps/qpsresources.qrc`` file 
into a corresponding python module ``qps/qpsresources.py``.  


3. Now you can use the QPS python API. Keep in mind that some of its features need to be 
registered to a running Qt Application or the QGIS Application instance. 
This is preferably done in the ```__init__.py``` of 
your application, e.g. by calling:

    ```python
    from mymodule.qps import initAll 
    initAll()
    ```

## Dependencies

QPS depends on the following type of packages:
1. those available in a standard QGIS installation, i.e. QGIS python API, numpy, gdal, etc.
2. pyqtgraph. 
   QPS uses the fork https://github.com/EnMAP-Box/pyqtgraph branch qps_modifications
   These files are included as subtree
   git subtree add --prefix qps/pyqtgraph git@github.com:EnMAP-Box/pyqtgraph.git qps_modifications --squash
3. 



## Examples ###

Examples can be found in the `examples` folder.

### Spectral Library Widget ###

The following example shows you how to initialize (for testing) a mocked QGIS Application and to open the Spectral Library  Wdiget: 

```python
from mymodule.qps.testing import initQgisApplication
QGIS_APP = initQgisApplication()


from mymodule.qps import initAll 
from mymodule.qps.speclib.core import SpectralLibraryWidget
initAll()

widget = SpectralLibraryWidget()
widget.show()

QGIS_APP.exec_()
```

Note that the first two lines and the last line are not required if QGIS is already started. 

### QGIS Resource files

Many QGIS icons are available as resource strings. Based on the Qt reosurce system, theses icons
can be used in own QGIS plugins, which reduces the need to provide own `*.png` or `*.svg` files and 
reduces the plugin size. 

For development, you might load the QGIS repository `images/images.qrc` to your reosurce files in the Qt Designer.

1. Clone the QGIS Repository to access its `images/images.qrc` 
   To donwload the `/images` folder only, you can do a sparse checkout:
    
    
    ```
    mkdir QGIS_Images
    cd QGIS_Images
    git init
    git config core.sparseCheckout true
    git remote add -t master origin https://github.com/qgis/QGIS.git
    echo '/images/' > .git/info/sparse-checkout
    git pull origin master
    ```

2. Open the `images/images.qrc` to your Qt Designer / Qt Creator to visualize icons and copy & paste their resource
   paths. E.g. `':/images/icons/qgis_icon.svg'` for the QGIS icon.
   
 

### Example: unit tests

QPS helps to initialize QgsApplications and to test them without starting an entire QGIS Desktop Application.

See `tests/test_example.py`

```python
import os, pathlib, unittest
from qps.testing import TestCase, StartOptions, start_app

from qgis.PyQt.QtWidgets import QLabel
from qgis.PyQt.QtGui import QIcon, QPixmap
from qgis.PyQt.QtCore import QSize, QFile, QDir
from qgis.core import QgsApplication

qgis_images_resources = pathlib.Path(__file__).parents[1] / 'qgisresources' / 'images_rc.py'

class Example1(unittest.TestCase):

    @unittest.skipIf(not qgis_images_resources.is_file(), 'Resource file does not exist: {}'.format(qgis_images_resources))
    def test_startQgsApplication(self):
        """
        This example shows how to initialize a QgsApplication on TestCase start up
        """
        resource_path = ':/images/icons/qgis_icon.svg'
        self.assertFalse(QFile(resource_path).exists())

        # StartOptions:
        # Minimized = just the QgsApplication
        # EditorWidgets = initializes EditorWidgets to manipulate vector attributes
        # ProcessingFramework = initializes teh QGIS Processing Framework
        # PythonRunner = initializes a PythonRunner, which is required to run expressions on vector layer fields
        # PrintProviders = prints the QGIS data providers
        # All = EditorWidgets | ProcessingFramework | PythonRunner | PrintProviders

        app = start_app(options=StartOptions.Minimized, resources=[qgis_images_resources])
        self.assertIsInstance(app, QgsApplication)
        self.assertTrue(QFile(resource_path).exists())


class ExampleCase(TestCase):
    """
    This example shows how to run unit tests using a QgsApplication
    that has the QGIS resource icons loaded
    """
    @classmethod
    def setUpClass(cls) -> None:
        # this initializes the QgsApplication with resources from images loaded
        resources = []
        if qgis_images_resources.is_file():
            resources.append(qgis_images_resources)
        super().setUpClass(cleanup=True, options=StartOptions.Minimized, resources=resources)

    @unittest.skipIf(not qgis_images_resources.is_file(),
                     'Resource file does not exist: {}'.format(qgis_images_resources))
    def test_show_raster_icon(self):
        """
        This example show the QGIS Icon in a 200x200 px label.
        """
        icon = QIcon(':/images/icons/qgis_icon.svg')
        self.assertIsInstance(icon, QIcon)

        label = QLabel()
        label.setPixmap(icon.pixmap(QSize(200,200)))

        # In case the the environmental variable 'CI' is not set,
        # .showGui([list-of-widgets]) function will show and calls QApplication.exec_()
        # to keep the widget open
        self.showGui(label)



if __name__ == '__main__':

    unittest.main()

```

## Update pyqtgraph

Run the the following command to the qps internal [pyqtgraph](http://pyqtgraph.org) version
```
git read-tree --prefix=qps/externals/pyqtgraph/ -u pyqtgraph-0.11.0rc0:pyqtgraph
```



## License

QPS is released under the GNU Public License (GPL) Version 3 or above.
Developing QPS under this license means that you can (if you want to) inspect
and modify the source code and guarantees that you, our happy user will always
have access to an EnMAP-Box program that is free of cost and can be freely
modified.


