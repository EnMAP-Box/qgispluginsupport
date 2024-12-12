from qgis.core import QgsFeature, QgsGeometry, QgsPointXY
from qgis.core import QgsVectorLayer, edit
from qgis.gui import QgsDualView, QgsMapCanvas, QgsGui
from qgis.testing import start_app

app = start_app()
QgsGui.editorWidgetRegistry().initEditors()


class TestCanvas(QgsMapCanvas):
    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

        self.zoom_fids = set()
        self.pan_fids = set()
        self.flash_fids = set()

    def panToFeatureIds(self, layer, ids, alwaysRecenter: bool = True):
        self.pan_fids = self.pan_fids.union(ids)

    def flashFeatureIds(self, layer, ids):
        self.flash_fids = self.flash_fids.union(ids)

    def zoomToFeatureIds(self, layer, ids):
        self.zoom_fids = self.zoom_fids.union(ids)


canvas = TestCanvas()

n_features = 10

uri = "point?crs=epsg:4326&field=name:string"
layer = QgsVectorLayer(uri, "Scratch point layer", "memory")
with edit(layer):
    for i in range(n_features):
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(i, i)))
        f.setAttribute('name', f'Point {i + 1}')
        layer.addFeature(f)

dv = QgsDualView()
canvas.setLayers([layer])
dv.init(layer, canvas)
dv.setView(QgsDualView.ViewMode.AttributeEditor)

# seems there is no way to enable the zoom or pan button from python
# however, the "Highlight current feature on map" action is activate by default

feature_ids = layer.allFeatureIds()
for fid in feature_ids:
    layer.select([fid])

dv.show()

# set True to test manually
if True:
    app.exec_()
    print(f'flashed feature ids: {canvas.flash_fids}')
    print(f'zoomed feature ids: {canvas.zoom_fids}')
    print(f'panned feature ids: {canvas.pan_fids}')
else:
    assert len(canvas.flash_fids) > 0
