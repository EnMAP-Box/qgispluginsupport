# QGIS Plugin Support Skill

## Description

This skill provides guidance and assistance for developing, testing, and maintaining QGIS plugins using the qgispluginsupport repository structure and tools.

## Available Commands

### Running Tests
- Run all tests: `bash runtests.sh`
- Run specific test file: `bash runtests.sh tests/speclib/test_<testname>.py`
- Run tests with coverage: `bash runtests.sh --cov`

### Code Quality
- Run flake8: `flake8 qps/ tests/`
- Run bandit: `bandit -r .`

### Development
- Initialize QGIS resources: `python runfirst.py`
- Check URLS: `bash check_urls.sh`

## Common Tasks

### Creating a New Test File
1. Create test file in `tests/<module>/test_<module>.py`
2. Import required modules: `start_app()`, `TestCase`, `TestObjects`
3. Create test class extending `TestCase`
4. Add test methods with descriptive names starting with `test_`
5. Clean up in `tearDown()` method

### Adding a New QGIS Processing Algorithm
1. Create algorithm class extending `QgsProcessingAlgorithm`
2. Implement `createInstance()`, `name()`, `displayName()`, `groupId()`, `group()`
3. Implement `initAlgorithm()` to define parameters and outputs
4. Implement `processAlgorithm()` with the actual processing logic
5. Register the algorithm with the algorithm provider

### Working with Spectral Libraries
- Use `TestObjects.createSpectralLibrary()` to create test spectral libraries
- Use `spectrallibraryrasterdataprovider.createRasterLayers()` for creating example layers
- Use `SpectralProcessingContextGenerator` for processing context management

## Project Structure

```
qgispluginsupport/
├── qps/                    # Main source code
│   └── speclib/           # Spectral library functionality
│       ├── core/          # Core spectral library classes
│       ├── gui/           # GUI components
│       ├── io/            # Input/output handlers
│       └── processing/    # Processing algorithms
├── tests/                 # Test files
│   └── speclib/          # Spectral library tests
├── examples/              # Example plugins and scripts
└── scripts/               # Utility scripts
```

## Common Patterns

### Test Class Structure
```python
import unittest
from qps.testing import TestCase, start_app, TestObjects

start_app()

class MyTests(TestCase):
    def test_example(self):
        # Create test data
        speclib = TestObjects.createSpectralLibrary()
        
        # Test functionality
        self.assertIsNotNone(speclib)
        
    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()
        super().tearDown()

if __name__ == '__main__':
    unittest.main(buffer=False)
```

### Creating a Spectral Processing Context
```python
from qps.speclib.gui.spectralprocessingcontextgenerator import SpectralProcessingContextGenerator

generator = SpectralProcessingContextGenerator(speclib)
context = generator.processingContext()
widget_context = generator.createWidgetContext()
```

## Notes

- QGIS version: Currently using QGIS 4.2 (Qt6)
- Python version: 3.14
- PyQtGraph Qt library: PyQt6 (must match QGIS Qt version)
