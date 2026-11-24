import unittest

from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import (QgsFeature, QgsProject, edit)
from qgis.core import QgsField
from qgis.gui import QgsAttributeDialog

from qps.reimplementation.featureaction import QgsFeatureAction
from qps.testing import start_app, TestCase, TestObjects
from qps.vectorlayertools import VectorLayerTools

start_app()


class TestFeatureAction(TestCase):
    """
    Test cases for QgsFeatureAction class.
    """

    def setUp(self):
        """Set up test fixtures before each test method."""
        self.layer = TestObjects.createVectorLayer()
        with edit(self.layer):
            self.layer.addAttribute(QgsField('teststring', QMetaType.Type.QString))
        self.feature = self.createTestFeature()
        self.action_id = 'my_action_id'
        self.assertTrue(self.layer.isValid())

    def tearDown(self):
        """Clean up after each test method."""
        QgsProject.instance().removeAllMapLayers()
        super().tearDown()

    def test_constructor(self):
        """Test QgsFeatureAction constructor."""
        action_name = 'Test Action'

        f = self.createTestFeature()
        action_id = 'my_action_id'
        action = QgsFeatureAction(action_name, f, self.layer, action_id, -1, None)

        self.assertIsInstance(action, QgsFeatureAction)
        self.assertEqual(action.text(), action_name)
        self.assertIsNotNone(action.mLayer)
        self.assertEqual(action.mLayer.id(), self.layer.id())
        self.assertIsNotNone(action.mFeature)
        self.assertEqual(action.mFeature.id(), f.id())
        self.assertEqual(action.mActionId, action_id)
        self.assertEqual(action.mIdx, -1)
        self.assertFalse(action.mFeatureSaved)
        self.assertFalse(action.mForceSuppressFormPopup)

    def createTestFeature(self) -> QgsFeature:
        f = QgsFeature(self.layer.fields())
        f.setAttribute('teststring', 'Test Feature')
        return f

    def test_setVectorLayerTools(self):
        """Test setVectorLayerTools method."""

        vlt = VectorLayerTools()

        f = self.createTestFeature()
        action = QgsFeatureAction('Test', f, self.layer, 'myid', -1, None)
        action.setVectorLayerTools(vlt)
        self.assertEqual(action.mVectorLayerTools, vlt)

    def test_setAttributeEditorContext(self):
        """Test setAttributeEditorContext method."""
        from qgis.gui import QgsAttributeEditorContext
        f = self.createTestFeature()
        action = QgsFeatureAction('Test', f, self.layer, 'myid', -1, None)
        context = QgsAttributeEditorContext()
        action.setAttributeEditorContext(context)
        self.assertEqual(action.mAttributeEditorContext, context)

    # def test_execute(self):
    #     """Test execute method - runs action on layer."""
    #     # Create a feature action and execute it
    #     action = QgsFeatureAction('Test Action', self.feature, self.layer, self.action_id, -1, None)
    #
    #     # This should not raise an exception
    #     # Note: The actual action execution depends on layer actions being configured
    #     try:
    #         action.execute()
    #     except Exception:
    #         # It is OK if it fails if no action exists with this ID
    #         pass  # Expected behavior

    def test_newDialog_returns_QgsAttributeDialog(self):
        """Test that newDialog returns a QgsAttributeDialog."""

        p = QWidget()
        action = QgsFeatureAction('Test Action', self.feature, self.layer, self.action_id, -1, parent=p)
        t = VectorLayerTools()
        action.setVectorLayerTools(t)

        dialog = action.newDialog(cloneFeatures=False)
        self.assertTrue(dialog.feature() == self.feature)

        dialog = action.newDialog(cloneFeatures=True)
        self.assertTrue(dialog.feature() == self.feature)

        self.assertIsInstance(dialog, QgsAttributeDialog)
        self.assertEqual(dialog.parent(), p)

    def test_viewFeatureForm(self):
        """Test viewFeatureForm method."""
        action = QgsFeatureAction('Test Action', self.feature, self.layer, self.action_id, -1, None)

        highlight = None  # Can be None or QgsHighlight instance
        result = action.viewFeatureForm(highlight)

        # Should return True if dialog was created successfully
        self.assertTrue(result)

    def test_editFeature_showModal(self):
        """Test editFeature with showModal=True."""
        action = QgsFeatureAction('Test Action', self.feature, self.layer, self.action_id, -1, None)

        result = action.editFeature(showModal=not TestCase.runsInCI())

        self.assertTrue(result)

    def test_editFeature_nonModal(self):
        """Test editFeature with showModal=False."""
        with edit(self.layer):
            parent = QWidget()
            action = QgsFeatureAction('Test Action', self.feature, self.layer, self.action_id, -1, parent)
            result = action.editFeature(showModal=not TestCase.runsInCI())

        self.assertTrue(result)

    def test_addFeature(self):
        """Test addFeature method."""
        # Ensure layer is editable
        self.layer.startEditing()

        action = QgsFeatureAction('Test Action', self.feature, self.layer, self.action_id, -1, None)

        # Try to add a new feature
        result = action.addFeature(
            defaultAttributeValues={},
            showModal=False
        )

        # Result should be True if feature was processed
        self.assertTrue(result)

        # Cleanup
        self.layer.rollBack()

    def test_addFeature_with_default_values(self):
        """Test addFeature with default attribute values."""
        self.layer.startEditing()

        action = QgsFeatureAction('Test Action', self.feature, self.layer, self.action_id, -1, None)

        # Get field index for testing
        fields = self.layer.fields()
        if fields.count() > 0:
            idx = fields.indexFromName('teststring')
            result = action.addFeature(
                defaultAttributeValues={idx: 'Default Value'},
                showModal=not TestCase.runsInCI()
            )

            self.assertTrue(result)

        self.layer.rollBack()

    def test_setForceSuppressFormPopup(self):
        """Test setForceSuppressFormPopup method."""
        action = QgsFeatureAction('Test Action', self.feature, self.layer, self.action_id, -1, None)

        self.assertFalse(action.mForceSuppressFormPopup)

        action.setForceSuppressFormPopup(True)

        self.assertTrue(action.mForceSuppressFormPopup)

    def test_onFeatureSaved(self):
        """Test onFeatureSaved method."""
        action = QgsFeatureAction('Test Action', self.feature, self.layer, self.action_id, -1, None)

        # Create a new feature for saving
        new_feature = QgsFeature(self.layer.fields())
        new_feature.setGeometry(self.feature.geometry())
        new_feature.setAttributes(['Saved Feature'])

        # Create a mock attribute form
        dialog = action.newDialog(False)
        form = dialog.attributeForm()

        action.onFeatureSaved(new_feature, form)

        # Verify feature was saved
        self.assertTrue(action.mFeatureSaved)

    def test_lastUsedValues_static_variable(self):
        """Test that sLastUsedValues static variable exists and is a dict."""
        self.assertIsInstance(QgsFeatureAction.sLastUsedValues, dict)


if __name__ == '__main__':
    unittest.main(buffer=False)
