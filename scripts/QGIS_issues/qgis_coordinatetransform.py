from qgis.core import QgsCoordinateReferenceSystem, QgsPointXY, QgsCoordinateTransform, QgsProject
import numpy as np
crsSrc = QgsCoordinateReferenceSystem('EPSG:4326')
crsDst = QgsCoordinateReferenceSystem('EPSG:32633')
transform = QgsCoordinateTransform(crsSrc, crsDst, QgsProject.instance())
assert transform.isValid()

point = QgsPointXY(12.0, 52.0)
# this works well
print(transform.transform(point))

# but how to transform a list/array of coordinates?
transform.transformCoords(1, np.asarray([12.0]), np.asarray([52.0]), np.asarray([0.0]))
transform.transformCoords(1, ((12.0,), (52.0,), (0.0,)))
transform.transformCoords(1, ([12.0,], [52.0,], [0.0,]))
# TypeErrors in order of transformCoord calls:
# QgsCoordinateTransform.transformCoords(): argument 2 has unexpected type 'numpy.ndarray'
# QgsCoordinateTransform.transformCoords(): argument 2 has unexpected type 'tuple'
# QgsCoordinateTransform.transformCoords(): argument 2 has unexpected type 'list'


# How can I transform multiple coordinates with one call?
# from QGIS API docs: https://qgis.org/pyqgis/master/core/QgsCoordinateTransform.html#qgis.core.QgsCoordinateTransform.transformCoords
"""
transformCoords(self, 
                numPoint: int, 
                direction: QgsCoordinateTransform.TransformDirection = QgsCoordinateTransform.ForwardTransform) 
                -> Tuple[float, float, float]

    Transform an array of coordinates to the destination CRS. 
    If the direction is ForwardTransform then coordinates are transformed from source to destination, 
    otherwise points are transformed from destination to source CRS.

    Parameters:
            numPoint (int) – number of coordinates in arrays
            x – array of x coordinates to transform
            y – array of y coordinates to transform
            z – array of z coordinates to transform
            direction (QgsCoordinateTransform.TransformDirection = QgsCoordinateTransform.ForwardTransform) 
            – transform direction (defaults to ForwardTransform)

    Return type
        Tuple[float, float, float]
    """