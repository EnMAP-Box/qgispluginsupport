"""
Example for Workaround for https://github.com/qgis/QGIS/issues/45228
"""
from qgis.core import QgsVectorLayer, QgsFeature
from qgis.testing import TestCase

class Tests(TestCase):

    def testCommitChangesReportsDeletedFeatureIDs(self):
        """
        Tests if commitChanges emits "featuresDeleted" with all deleted feature IDs,
        e.g. in case (negative) temporary FIDs are converted into (positive) persistent FIDs.
        """
        temp_fids = []

        def onFeaturesDeleted(deleted_fids):
            self.assertEqual(len(deleted_fids), len(temp_fids),
                             msg=f'featuresDeleted returned {len(deleted_fids)} instead of 2 deleted feature IDs: '
                                 f'{deleted_fids}')
            for d in deleted_fids:
                self.assertTrue(d in temp_fids)

        layer = QgsVectorLayer("point?crs=epsg:4326&field=name:string", "Scratch point layer", "memory")
        layer.featuresDeleted.connect(onFeaturesDeleted)

        layer.startEditing()
        layer.beginEditCommand('add 2 features')
        layer.addFeature(QgsFeature(layer.fields()))
        layer.addFeature(QgsFeature(layer.fields()))
        layer.endEditCommand()
        temp_fids.extend(layer.allFeatureIds())

        layer.commitChanges()

