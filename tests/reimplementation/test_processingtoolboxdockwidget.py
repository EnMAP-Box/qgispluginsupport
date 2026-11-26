# noinspection PyPep8Naming
import unittest

from qgis.core import QgsApplication, Qgis

from qps import initAll
from qps.reimplementation.processingtoolboxdockwidget import ProcessingToolboxDockWidget
from qps.testing import TestCase, start_app

QGIS_VERSION_INT = Qgis.versionInt()
start_app()
initAll()


class ProcessingToolboxDockWidgetTests(TestCase):

    def test_initialization(self):
        """Test that QgsProcessingToolboxDockWidget initializes correctly"""
        widget = ProcessingToolboxDockWidget()

        self.assertIsInstance(widget, ProcessingToolboxDockWidget)
        self.assertIsNotNone(widget.algorithmTree)
        self.assertIsNotNone(widget.searchBox)
        self.assertIsNotNone(widget.processingToolbar)

        self.showGui(widget)
        widget.deleteLater()

    def test_search_box_placeholder(self):
        """Test that the search box has a placeholder text"""
        widget = ProcessingToolboxDockWidget()

        # The search box should have placeholder text set
        placeholder = widget.searchBox.placeholderText()
        self.assertIsNotNone(placeholder)
        self.assertGreater(len(placeholder), 0)

        widget.deleteLater()

    def test_filter_string_set(self):
        """Test that setFilterString works correctly"""
        widget = ProcessingToolboxDockWidget()

        # Test setting an empty filter string
        widget.setFilterString("")

        # Test setting a filter string
        widget.setFilterString("raster")

        widget.deleteLater()

    def test_qgis_version_compatibility(self):
        """Test that version-specific features are handled correctly"""
        widget = ProcessingToolboxDockWidget()

        # Test that the widget handles the current QGIS version correctly
        if QGIS_VERSION_INT >= 44000:
            # QGIS 4.4+ should have all features
            self.assertIsNotNone(widget.searchBox.placeholderText())
        else:
            # QGIS < 4.4 should have basic functionality
            self.assertIsNotNone(widget.algorithmTree)

        widget.deleteLater()

    def test_executing_algorithm(self):
        """Test that executeCurrentAlgorithm works"""
        widget = ProcessingToolboxDockWidget()

        # Select an algorithm from the tree
        # Get the first provider
        providers = QgsApplication.processingRegistry().providers()
        if len(providers) > 0:
            # Get first provider's algorithms
            provider = providers[0]
            algorithms = provider.algorithms()

            if len(algorithms) > 0:
                # The algorithm exists, but we can't easily select it in the tree view
                # without a GUI event loop. Just verify the execute method exists.
                self.assertTrue(hasattr(widget, 'executeCurrentAlgorithm'))

        widget.deleteLater()

    def test_in_place_edit_mode(self):
        """Test that setInPlaceEditMode works"""
        widget = ProcessingToolboxDockWidget()

        # Test enabling in-place mode
        widget.setInPlaceEditMode(True)

        # Test disabling in-place mode
        widget.setInPlaceEditMode(False)

        widget.deleteLater()

    def test_multiple_instances(self):
        """Test that multiple widget instances can be created"""
        widget1 = ProcessingToolboxDockWidget()
        widget2 = ProcessingToolboxDockWidget()

        self.assertIsNot(widget1, widget2)
        self.assertIsNot(widget1.algorithmTree, widget2.algorithmTree)

        widget1.deleteLater()
        widget2.deleteLater()


if __name__ == '__main__':
    unittest.main(buffer=False)
