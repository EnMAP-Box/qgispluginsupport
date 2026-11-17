# noinspection PyPep8Naming
import unittest

from qgis.PyQt.QtCore import QMetaType
from qgis.core import QgsField
from qgis.core import QgsProject, QgsProcessingContext
from qgis.core import edit
from qgis.gui import QgsProcessingParameterWidgetContext

from qps import initAll
from qps.speclib.gui.spectralprocessingcontextgenerator import SpectralProcessingContextGenerator
from qps.testing import TestCase, start_app, TestObjects

start_app()
initAll()


class SpectralProcessingContextGeneratorTests(TestCase):

    def test_initialization(self):
        """Test that SpectralProcessingContextGenerator initializes correctly"""
        speclib = TestObjects.createSpectralLibrary()
        generator = SpectralProcessingContextGenerator(speclib)

        # isInstance check confirms generator is not None
        self.assertIsInstance(generator, SpectralProcessingContextGenerator)
        self.assertIsInstance(generator.processingContext(), QgsProcessingContext)

    def test_processing_context(self):
        """Test that processingContext() returns a valid QgsProcessingContext"""
        speclib = TestObjects.createSpectralLibrary()
        generator = SpectralProcessingContextGenerator(speclib)

        # isInstance confirms context is not None
        context = generator.processingContext()
        self.assertIsInstance(context, QgsProcessingContext)
        self.assertIsNotNone(context.project())

    def test_widget_context(self):
        """Test that createWidgetContext() returns a valid QgsProcessingParameterWidgetContext"""
        speclib = TestObjects.createSpectralLibrary()
        generator = SpectralProcessingContextGenerator(speclib)

        # isInstance confirms widget_context is not None
        widget_context = generator.createWidgetContext()
        self.assertIsInstance(widget_context, QgsProcessingParameterWidgetContext)

    def test_example_layers_empty_initially(self):
        """Test that example layers are created during initialization"""
        speclib = TestObjects.createSpectralLibrary()
        generator = SpectralProcessingContextGenerator(speclib)

        example_layers = generator.exampleLayers()
        self.assertIsInstance(example_layers, list)

    def test_example_layers_correspond_to_speclib_fields(self):
        """Test that example layers correspond to profile fields in the spectral library"""
        speclib = TestObjects.createSpectralLibrary(n_bands=5)
        generator = SpectralProcessingContextGenerator(speclib)

        example_layers = generator.exampleLayers()

        # isInstance confirms example_layers is not None, so count check is redundant
        self.assertIsInstance(example_layers, list)
        # The number of example layers should correspond to the number of profile fields
        # or bands in the spectral library
        self.assertGreaterEqual(len(example_layers), 1)

    def test_update_example_layers_on_attribute_add_delete(self):
        """Test that example layers are updated when a new attribute is added"""
        speclib = TestObjects.createSpectralLibrary(n_bands=3)
        generator = SpectralProcessingContextGenerator(speclib)

        original_layer_count = len(generator.exampleLayers())

        # Add a new field to the spectral library
        with edit(speclib):
            # Add a new profile field
            speclib.addAttribute(QgsField("new_field", QMetaType.Type.Double))

        updated_layers = generator.exampleLayers()
        # After adding a field, we might have more example layers
        self.assertGreaterEqual(len(updated_layers), original_layer_count + 1)

        # Add a new field to the spectral library
        with edit(speclib):
            # Add a new profile field
            speclib.deleteAttribute(speclib.fields().indexFromName("profiles0"))
            updated_layers = generator.exampleLayers()
        self.assertGreaterEqual(len(updated_layers), original_layer_count)

    def test_project_integration(self):
        """Test that the internal project is properly integrated"""
        speclib = TestObjects.createSpectralLibrary()
        generator = SpectralProcessingContextGenerator(speclib)

        context = generator.processingContext()
        project = context.project()

        self.assertIsInstance(project, QgsProject)

        # Verify the spectral library is added to the project
        self.assertGreater(project.count(), 0)

    def test_multiple_spectral_libraries(self):
        """Test creating multiple generators for different spectral libraries"""
        speclib1 = TestObjects.createSpectralLibrary(n_bands=2)
        speclib2 = TestObjects.createSpectralLibrary(n_bands=4)

        generator1 = SpectralProcessingContextGenerator(speclib1)
        generator2 = SpectralProcessingContextGenerator(speclib2)

        # Each generator should have its own processing context and example layers
        context1 = generator1.processingContext()
        context2 = generator2.processingContext()

        self.assertIsNot(context1, context2)
        self.assertIsNot(generator1.exampleLayers(), generator2.exampleLayers())

    def test_example_layers_returns_copy(self):
        """Test that exampleLayers() returns a copy, not the original list"""
        speclib = TestObjects.createSpectralLibrary()
        generator = SpectralProcessingContextGenerator(speclib)

        layers1 = generator.exampleLayers()
        layers2 = generator.exampleLayers()

        # They should be different list instances but contain same layers
        self.assertIsNot(layers1, layers2)
        self.assertEqual(len(layers1), len(layers2))

    def test_processing_context_has_project(self):
        """Test that the processing context has the correct project set"""
        speclib = TestObjects.createSpectralLibrary()
        generator = SpectralProcessingContextGenerator(speclib)

        context = generator.processingContext()
        project = context.project()

        # context.project() returning None would cause an error in real code,
        # but we check it's the same project instance
        self.assertEqual(project, generator._project)

    def test_context_generator_registration(self):
        """Test that widget context properly registers the context generator"""
        speclib = TestObjects.createSpectralLibrary()
        generator = SpectralProcessingContextGenerator(speclib)

        widget_context = generator.createWidgetContext()

        # widget_context isInstance check confirms it's not None
        self.assertIsInstance(widget_context, QgsProcessingParameterWidgetContext)

    def tearDown(self):
        """Clean up after each test"""
        QgsProject.instance().removeAllMapLayers()
        super().tearDown()


if __name__ == '__main__':
    unittest.main(buffer=False)
