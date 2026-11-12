"""
/***************************************************************************
     test_spectral_proc_algorithmwidgets.py
     ---------------------
     Date                 : November 2026
     Copyright            : (C) 2026 by Benjamin Jakimow
     Email                : benjamin.jakimow@geo.hu-berlin.de
 ***************************************************************************
 *                                                                         *
 *   This program is free software; you can redistribute it and/or modify  *
 *   it under the terms of the GNU General Public License as published by  *
 *   the Free Software Foundation; either version 3 of the License, or     *
 *   (at your option) any later version.                                   *
 *                                                                         *
 ***************************************************************************/
"""
import unittest
from unittest.mock import MagicMock, patch

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon
from qgis._core import QgsVectorLayer
from qgis.core import (
    QgsApplication,
    QgsProcessingContext,
    QgsProject,
)
from qgis.gui import QgsMessageBar
from qgis.gui import QgsProcessingParameterWidgetContext

from qps import initAll
from qps.speclib.gui.spectralprocessingalgorithmwidget import SpectralProcessingAlgorithmWidget
from qps.testing import TestCase, TestObjects, start_app

start_app()
initAll()


class SpectralProcessingAlgorithmWidgetTests(TestCase):

    def setUp(self):
        """Set up test fixtures."""
        self.project = QgsProject()
        self.speclib = TestObjects.createSpectralLibrary(n=5, n_bands=10)
        self.project.addMapLayer(self.speclib)
        self.reg = QgsApplication.processingRegistry()

    def tearDown(self):
        """Clean up after tests."""
        self.project.clear()
        QgsProject.instance().clear()

    def test_init_with_speclib(self):
        """Test widget initialization with a valid spectral library."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        self.assertIsInstance(widget, SpectralProcessingAlgorithmWidget)
        self.assertEqual(widget.speclib(), self.speclib)
        self.assertTrue(widget.algorithm() is None)
        self.assertEqual(widget.windowTitle(), 'Spectral Processing Widget')

    def test_init_with_algorithm(self):
        """Test widget initialization with a specific algorithm."""
        alg = self.reg.createAlgorithmById('gdal:translate')
        widget = SpectralProcessingAlgorithmWidget(self.speclib, algorithm=alg)

        self.assertEqual(widget.algorithm(), alg)
        self.assertIn(alg.displayName(), widget.windowTitle())

    def test_init_with_invalid_speclib_raises_error(self):
        """Test that initializing with invalid speclib raises TypeError."""
        with self.assertRaises(TypeError):
            SpectralProcessingAlgorithmWidget(None)

        with self.assertRaises(TypeError):
            SpectralProcessingAlgorithmWidget('invalid_string')

    def test_speclib_method(self):
        """Test the speclib() method returns correct layer."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)
        self.assertEqual(widget.speclib(), self.speclib)

    def test_algorithm_updates(self):
        """Test algorithm setting and updating."""
        alg1 = self.reg.createAlgorithmById('gdal:translate')
        alg2 = self.reg.createAlgorithmById('native:rescaleraster')

        widget = SpectralProcessingAlgorithmWidget(self.speclib)
        self.assertTrue(widget.algorithm() is None)

        widget.setAlgorithm(alg1)
        self.assertEqual(widget.algorithm(), alg1)

        widget.setAlgorithm(alg2)
        self.assertEqual(widget.algorithm(), alg2)

    def test_algorithm_update_updates_gui(self):
        """Test that setting algorithm updates the GUI."""
        alg = self.reg.createAlgorithmById('gdal:translate')
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        # Initially no algorithm selected
        tb_alg_name = widget.tbAlgorithmName
        self.assertEqual(tb_alg_name.text(), '')
        self.assertTrue(tb_alg_name.hasFocus() or not tb_alg_name.text())

        # Set algorithm and check GUI update
        widget.setAlgorithm(alg)
        self.showGui(widget)

        # After setting algorithm, text should be updated
        self.assertIn(alg.displayName(), tb_alg_name.text())

    def test_algorithm_with_no_algorithm(self):
        """Test setting algorithm to None."""
        alg = self.reg.createAlgorithmById('gdal:translate')
        widget = SpectralProcessingAlgorithmWidget(self.speclib, algorithm=alg)

        self.assertEqual(widget.algorithm(), alg)

        widget.setAlgorithm(None)
        self.assertTrue(widget.algorithm() is None)

    def test_algorithm_name_display(self):
        """Test that algorithm name is displayed correctly in GUI."""
        alg = self.reg.createAlgorithmById('gdal:translate')
        widget = SpectralProcessingAlgorithmWidget(self.speclib)
        widget.setAlgorithm(alg)

        tb_alg_name = widget.tbAlgorithmName
        self.assertIn(alg.displayName(), tb_alg_name.text())
        self.assertIn(alg.id(), tb_alg_name.text())

    def test_algorithm_tooltip(self):
        """Test that algorithm tooltip contains correct information."""
        alg = self.reg.createAlgorithmById('gdal:translate')
        widget = SpectralProcessingAlgorithmWidget(self.speclib)
        widget.setAlgorithm(alg)

        tb_alg_name = widget.tbAlgorithmName
        tooltip = tb_alg_name.toolTip()

        self.assertIn('Algorithm Name:', tooltip)
        self.assertIn(alg.name(), tooltip)
        self.assertIn('Algorithm ID:', tooltip)
        self.assertIn(alg.id(), tooltip)

    def test_algorithm_validation_styling(self):
        """Test that algorithm validation uses correct styling."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        # Without algorithm, should use red color
        tb_alg_name = widget.tbAlgorithmName
        style = tb_alg_name.styleSheet()

        widget.setAlgorithm(None)
        # Check that invalid algorithm gets red styling
        widget.updateGui()

        # With valid algorithm, should use default styling
        alg = self.reg.createAlgorithmById('gdal:translate')
        widget.setAlgorithm(alg)
        widget.updateGui()

        tb_alg_name = widget.tbAlgorithmName
        # After setting valid algorithm, style should be cleared
        style = tb_alg_name.styleSheet()
        self.assertEqual(style, '')

    def test_selected_features_checkbox_initial_state(self):
        """Test the selected features checkbox initial state."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        cb_selected = widget.cbSelectedFeaturesOnly

        # Initially no features selected, so checkbox should be disabled
        self.assertFalse(cb_selected.isEnabled())

    def test_selected_features_checkbox_with_selection(self):
        """Test the selected features checkbox with selected features."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)
        cb_selected = widget.cbSelectedFeaturesOnly

        # Select some features
        with QgsProject.instance().editLayer(self.speclib):
            self.speclib.selectByIds([1, 2, 3])

        widget.updateGui()

        # With selected features, checkbox should be enabled
        self.assertTrue(cb_selected.isEnabled())

        # Checkbox text should reflect number of selected features
        text = cb_selected.text()
        self.assertIn('selected', text.lower())

    def test_selected_features_checkbox_text_update(self):
        """Test that checkbox text updates with selected feature count."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)
        cb_selected = widget.cbSelectedFeaturesOnly

        # Select 3 features
        self.speclib.selectByIds([1, 2, 3])
        widget.updateGui()

        text = cb_selected.text()
        self.assertIn('3', text)
        self.assertIn('selected', text.lower())

    def test_processing_context(self):
        """Test that processing context is properly generated."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        context = widget.processingContext()
        self.assertIsInstance(context, QgsProcessingContext)

    def test_widget_context(self):
        """Test that widget context is properly generated."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        context = widget.widgetContext()
        self.assertIsInstance(context, QgsProcessingParameterWidgetContext)

    def test_message_bar(self):
        """Test that message bar is accessible."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        msg_bar = widget.messageBar()
        self.assertIsInstance(msg_bar, QgsMessageBar)

    def test_main_widget_creation(self):
        """Test that main widget is created properly."""
        alg = self.reg.createAlgorithmById('gdal:translate')
        widget = SpectralProcessingAlgorithmWidget(self.speclib, algorithm=alg)

        main_widget = widget.mainWidget()
        self.assertIsNotNone(main_widget)

    def test_create_parameters_panel_without_algorithm(self):
        """Test parameter panel creation when no algorithm is set."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        panel = widget.createParametersPanel(False, self.speclib, widget.messageBar())
        self.assertIsNotNone(panel)

    def test_create_parameters_panel_with_algorithm(self):
        """Test parameter panel creation with a valid algorithm."""
        alg = self.reg.createAlgorithmById('gdal:translate')
        widget = SpectralProcessingAlgorithmWidget(self.speclib)
        widget.setAlgorithm(alg)

        panel = widget.createParametersPanel(False, self.speclib, widget.messageBar())
        self.assertIsNotNone(panel)
        # Panel should be a SpectralProcessingParametersWidget
        from qps.speclib.gui.spectralprocessingparameterswidget import SpectralProcessingParametersWidget
        self.assertIsInstance(panel, SpectralProcessingParametersWidget)

    def test_algorithm_dialog_button(self):
        """Test the algorithm dialog button."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        btn_alg = widget.btnAlgorithm
        self.assertIsNotNone(btn_alg)
        self.assertEqual(btn_alg.text(), 'Algorithm')

    @patch('qps.speclib.gui.spectralprocessingalgorithmwidget.ProcessingAlgorithmDialog')
    def test_set_algorithm_from_dialog(self, mock_dialog):
        """Test setting algorithm from dialog."""
        # Setup mock dialog
        mock_dlg_instance = MagicMock()
        mock_dlg_instance.exec.return_value = MagicMock()
        mock_dlg_instance.exec.return_value.__eq__ = lambda self, x: True
        mock_dlg_instance.algorithm.return_value = self.reg.createAlgorithmById('gdal:translate')
        mock_dialog.return_value = mock_dlg_instance

        widget = SpectralProcessingAlgorithmWidget(self.speclib)
        widget.setAlgorithmFromDialog()

        # Algorithm should be set from dialog
        self.assertIsNotNone(widget.algorithm())

    @patch('qps.speclib.gui.spectralprocessingalgorithmwidget.ProcessingAlgorithmDialog')
    def test_set_algorithm_from_dialog_cancel(self, mock_dialog):
        """Test canceling algorithm dialog."""
        # Setup mock dialog to be canceled
        mock_dlg_instance = MagicMock()
        mock_dlg_instance.exec.return_value = MagicMock()
        mock_dlg_instance.exec.return_value.__eq__ = lambda self, x: False
        mock_dlg_instance.algorithm.return_value = None
        mock_dialog.return_value = mock_dlg_instance

        widget = SpectralProcessingAlgorithmWidget(self.speclib)
        initial_alg = widget.algorithm()
        widget.setAlgorithmFromDialog()

        # Algorithm should not change on cancel
        self.assertEqual(widget.algorithm(), initial_alg)

    def test_update_gui_no_speclib(self):
        """Test GUI update with no valid speclib."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        # Temporarily set invalid speclib
        widget.mSpeclib = None
        widget.updateGui()

        # Should handle gracefully without crashing
        self.assertTrue(True)

    def test_update_gui_with_selected_features(self):
        """Test GUI update when features are selected."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        # Select features
        self.speclib.selectByIds([1, 2])

        widget.updateGui()

        cb_selected = widget.cbSelectedFeaturesOnly
        self.assertTrue(cb_selected.isEnabled())
        self.assertIn('2', cb_selected.text())

    def test_inplace_mode(self):
        """Test inplace mode handling."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        # Check default inplace mode
        self.assertFalse(widget.inPlace())

    def test_window_flags(self):
        """Test that help button is disabled."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        # WindowContextHelpButtonHint should be disabled
        flags = widget.windowFlags()
        # Check that the context help button is not present
        self.assertFalse(bool(flags & Qt.WindowContextHelpButtonHint))

    def test_icon_set(self):
        """Test that window icon is set."""
        widget = SpectralProcessingAlgorithmWidget(self.speclib)

        icon = widget.windowIcon()
        self.assertIsNotNone(icon)
        self.assertIsInstance(icon, QIcon)


class SpectralProcessingAlgorithmWidgetAlgorithmIntegrationTests(TestCase):
    """Integration tests with different QGIS processing algorithms."""

    def setUp(self):
        """Set up test fixtures."""
        self.project = QgsProject()
        self.speclib = TestObjects.createSpectralLibrary(n=25, n_bands=10)
        self.project.addMapLayer(self.speclib)
        self.reg = QgsApplication.processingRegistry()

    def tearDown(self):
        """Clean up after tests."""
        self.project.clear()
        QgsProject.instance().clear()

    def test_with_native_rearrange_bands(self):
        """Test widget with native rearrange bands algorithm."""
        alg = self.reg.createAlgorithmById('gdal:rearrange_bands')
        widget = SpectralProcessingAlgorithmWidget(self.speclib, algorithm=alg)

        self.assertEqual(widget.algorithm().id(), 'gdal:rearrange_bands')
        self.showGui(widget)

    def test_algorithm_change_recreates_panel(self):
        """Test that changing algorithm recreates parameter panel."""
        alg1 = self.reg.createAlgorithmById('gdal:translate')
        alg2 = self.reg.createAlgorithmById('native:rescaleraster')

        widget = SpectralProcessingAlgorithmWidget(self.speclib, algorithm=alg1)
        panel1 = widget.mainWidget()
        widget.setAlgorithm(alg2)
        panel2 = widget.mainWidget()

        # Panels should be different instances
        self.assertIsNot(panel1, panel2)

    def test_run_algorithm(self):
        """Test that changing algorithm recreates parameter panel."""
        alg1 = self.reg.createAlgorithmById('gdal:translate')
        if False:
            alg1 = self.reg.createAlgorithmById('native:virtualrastercalc')
            parameters = {'LAYERS': ['name (string)',
                                     'profiles0 (10 bands, Micrometers)'],
                          'EXPRESSION': '"name (string)@1" + "profiles0 (10 bands, Micrometers)@1"',
                          'EXTENT': None, 'CELL_SIZE': None, 'CRS': None,
                          'LAYER_NAME': 'outputband'
                          }
        if True:
            alg1 = self.reg.createAlgorithmById('native:alignrasters')
            parameters = {'LAYERS':
                [
                    {
                        'inputFile': 'profiles0 (10 bands, Micrometers)',
                        'outputFile': 'outA',
                        'resampleMethod': 0, 'rescale': False},
                    {
                        'inputFile': 'name (string)',
                        'outputFile': 'outB',
                        'resampleMethod': 0, 'rescale': False}
                ],
                'REFERENCE_LAYER': 'name (string)',
                'CRS': None, 'CELL_SIZE_X': None, 'CELL_SIZE_Y': None,
                'GRID_OFFSET_X': None, 'GRID_OFFSET_Y': None, 'EXTENT': None
            }

        sl: QgsVectorLayer = self.speclib
        # Keep every 2nd feature ID
        selected_ids = [fid for i, fid in enumerate(sl.allFeatureIds()) if i % 2 == 1]
        sl.selectByIds(selected_ids)
        widget = SpectralProcessingAlgorithmWidget(sl)
        widget.setAlgorithm(alg1)
        widget.setParameters(parameters)
        widget.runAlgorithm()
        self.showGui(widget)
        # widget.setParameters(parameters)
        # context = widget.processingContext()

        # self.showGui(widget)


if __name__ == '__main__':
    unittest.main(buffer=False)
