import unittest

from qgis.PyQt.QtCore import QMetaType
from qgis.PyQt.QtWidgets import QHBoxLayout
from qgis.PyQt.QtWidgets import QWidget
from qgis.core import QgsFields, QgsField
from qgis.core import QgsProcessingParameterRasterDestination, QgsProcessingContext, QgsProcessing

from qps.speclib.gui.spectralprocessingrasterdestination import SpectralProcessingDestinationFieldWidget, \
    SpectralProcessingRasterDestination
from qps.testing import TestCase, start_app, TestObjects

start_app()


class SpectralProcessingRasterDestinationTests(TestCase):

    def test_initial_state(self):
        """Test initial widget state"""
        sl = TestObjects.createSpectralLibrary()

        widget = SpectralProcessingDestinationFieldWidget()
        widget.setFields(sl.fields())

        widget.show()  # needed to allow for visibility testing

        # Should be in text box mode by default
        self.assertTrue(widget.tbNewFieldName.isVisible())
        self.assertFalse(widget.cbFields.isVisible())
        self.assertTrue(widget.rbNewField.isChecked())
        self.assertFalse(widget.rbExistingField.isChecked())
        self.assertEqual(widget.value(), "")

    def test_text_box_mode(self):
        """Test text box mode functionality"""
        widget = SpectralProcessingDestinationFieldWidget()

        # Set text in text box
        widget.tbNewFieldName.setText("my_field")
        self.assertEqual(widget.value(), "my_field")

        # Clear text
        widget.tbNewFieldName.setText("")
        self.assertEqual(widget.value(), "")

    def test_combo_box_mode(self):
        """Test combo box mode functionality"""
        widget = SpectralProcessingDestinationFieldWidget()
        widget.show()
        # Create fields and set them
        fields = QgsFields()
        fields.append(QgsField('field1', QMetaType.Type.QString))
        fields.append(QgsField('field2', QMetaType.Type.Int))
        fields.append(QgsField('field3', QMetaType.Type.Double))

        widget.setFields(fields)

        # Switch to combo box mode
        widget.rbExistingField.setChecked(True)

        self.assertFalse(widget.tbNewFieldName.isVisible())
        self.assertTrue(widget.cbFields.isVisible())

        # Check combo box has items
        self.assertEqual(widget.cbFields.count(), 3)
        self.assertIn('field1', widget.cbFields.itemText(0))
        self.assertIn('field2', widget.cbFields.itemText(1))
        self.assertIn('field3', widget.cbFields.itemText(2))

        # Select a field
        widget.cbFields.setCurrentIndex(1)
        self.assertEqual(widget.value(), "field2")

    def test_toggle_modes(self):
        """Test toggling between text box and combo box modes"""
        widget = SpectralProcessingDestinationFieldWidget()

        # Set fields
        fields = QgsFields()
        fields.append(QgsField('test_field', QMetaType.Type.QString))
        widget.setFields(fields)

        # Start in text box mode
        widget.tbNewFieldName.setText("custom_field")
        self.assertEqual(widget.value(), "custom_field")

        # Switch to combo box
        widget.rbExistingField.setChecked(True)
        self.assertFalse(widget.tbNewFieldName.isVisibleTo(widget))
        self.assertTrue(widget.cbFields.isVisibleTo(widget))

        # Should still have the combo box with fields
        self.assertEqual(widget.cbFields.count(), 1)

        # Switch back to text box
        widget.rbNewField.setChecked(True)
        self.assertTrue(widget.tbNewFieldName.isVisibleTo(widget))
        self.assertFalse(widget.cbFields.isVisibleTo(widget))

    def test_set_value_with_existing_field(self):
        """Test setValue with a field that exists in combo box"""
        widget = SpectralProcessingDestinationFieldWidget()

        fields = QgsFields()
        fields.append(QgsField('existing_field', QMetaType.Type.QString))
        widget.setFields(fields)

        # Set value to existing field
        widget.setValue("existing_field")

        # Should be in combo box mode with correct field selected
        self.assertFalse(widget.rbNewField.isChecked())
        self.assertTrue(widget.rbExistingField.isChecked())
        self.assertEqual(widget.cbFields.currentText(), "existing_field")
        self.assertEqual(widget.value(), "existing_field")

    def test_set_value_with_new_field(self):
        """Test setValue with a field that doesn't exist in combo box"""
        widget = SpectralProcessingDestinationFieldWidget()

        fields = QgsFields()
        fields.append(QgsField('existing_field', QMetaType.Type.QString))
        widget.setFields(fields)

        # Set value to new field
        widget.setValue("new_field")

        # Should be in text box mode with correct text
        self.assertTrue(widget.rbNewField.isChecked())
        self.assertFalse(widget.rbExistingField.isChecked())
        self.assertEqual(widget.tbNewFieldName.text(), "new_field")
        self.assertEqual(widget.value(), "new_field")

    def test_value_persistence_after_mode_switch(self):
        """Test that value is maintained when switching modes"""
        widget = SpectralProcessingDestinationFieldWidget()

        fields = QgsFields()
        fields.append(QgsField('field1', QMetaType.Type.QString))
        fields.append(QgsField('field2', QMetaType.Type.QString))
        widget.setFields(fields)

        widget.tbNewFieldName.setText("new_field")
        widget.rbExistingField.setChecked(True)
        self.assertEqual(widget.value(), "field1")

        # Set text box to a field name
        widget.rbNewField.setChecked(True)
        self.assertEqual(widget.value(), "new_field")
        self.showGui(widget)

    def test_empty_fields(self):
        """Test with empty QgsFields"""
        widget = SpectralProcessingDestinationFieldWidget()

        fields = QgsFields()
        widget.setFields(fields)

        widget.rbExistingField.setChecked(True)
        self.assertEqual(widget.cbFields.count(), 0)
        self.assertEqual(widget.value(), "")

    def test_wrapper(self):
        destination = QgsProcessingParameterRasterDestination('output', 'test')
        parent = QWidget()
        layout = QHBoxLayout()
        sl = TestObjects.createSpectralLibrary()
        wrapper = SpectralProcessingRasterDestination(destination, parent=parent)
        wrapper.setFields(sl.fields())
        layout.addWidget(wrapper.createLabel())
        layout.addWidget(wrapper.createWidget())

        context = QgsProcessingContext()
        wrapper.setWidgetValue('newfield', context)
        pvalue = wrapper.parameterValue()
        # wvalue = wrapper.widgetValue()
        self.assertEqual(
            pvalue,
            f'{QgsProcessing.TEMPORARY_OUTPUT}_newfield.tif'
        )
        fn = sl.fields().names()[0]
        wrapper.setWidgetValue(fn, context)
        pvalue = wrapper.parameterValue()
        self.assertEqual(
            pvalue,
            f'{QgsProcessing.TEMPORARY_OUTPUT}_{fn}.tif'
        )
        parent.setLayout(layout)

        self.showGui(parent)


if __name__ == '__main__':
    unittest.main(buffer=False)
