# QGIS Plugin Support (QPS) 
![build status](https://img.shields.io/bitbucket/pipelines/jakimowb/qgispluginsupport.svg)




This is a small library to support the creation of QGIS Plugins. 

OPS is used in other project like:

EnMAP-Box https://bitbucket.org/hu-geomatics/enmap-box

EO Time Series Viewer https://bitbucket.org/jakimowb/eo-time-series-viewer

Virtual Raster Builder https://bitbucket.org/jakimowb/virtual-raster-builder


## Usage ##


1. Copy the qgs folder into your source code, e.g. ``mymodule/qps``

2. Call the QPS package ``initAll``. It will call other rountines to, e.g. register widgets in QGIS

For example, this is how you can use the QPS SpectralLibrary widget:

```python
from mymodule.qps.testing import initQgisApplication
QGIS_APP = initQgisApplication()


from mymodule.qps import initAll 
from mymodule.qps.speclib.spectrallibraries import SpectralLibraryWidget

initAll()
widget = SpectralLibraryWidget()
widget.show()

QGIS_APP.exec_()
```



## License

QPS is released under the GNU Public License (GPL) Version 3 or above.
Developing QPS under this license means that you can (if you want to) inspect
and modify the source code and guarantees that you, our happy user will always
have access to an EnMAP-Box program that is free of cost and can be freely
modified.


