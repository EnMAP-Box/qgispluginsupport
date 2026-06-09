# Developer Guide for QPS (QGIS Plugin Support)

This document provides essential information for advanced developers working on the QPS project.

## 1. Build and Configuration

QPS is designed to be integrated as a submodule or a package within other QGIS plugins.

### Environment Setup
To develop or test QPS, you need a environment with QGIS and its Python dependencies (GDAL, NumPy) installed.

- **conda environment**: run tests using the conda environment in .conda/qps_latest.yml. 
  Junie should always use this conda environment when running terminal commands.
  ```bash
  conda env create -f .conda/qps_latest.yml
  conda activate qps_latest
  ```
  
- **PYTHONPATH**: Ensure that the project root and the QGIS `processing` plugin path are in your `PYTHONPATH`.
  ```bash
  export PYTHONPATH=".:/usr/share/qgis/python/plugins:$PYTHONPATH"
  ```
- **Qt Platform**: For headless environments or CI, use the offscreen platform:
  ```bash
  export QT_QPA_PLATFORM=offscreen
  ```

### Resource Compilation
QPS uses the Qt resource system. If you modify `.qrc` files, you may need to recompile them.
```python
from qps.setup import compileQPSResources
compileQPSResources()
```

## 2. Testing

### Configuration
Tests require a running `QgsApplication`. QPS provides utilities in `qps.testing` to handle this.

### Running Tests
Use `pytest` to run the tests. A helper script `runtests.sh` is provided to set up the environment variables automatically.

**Run all tests:**
```bash
./runtests.sh
```

**Run a specific test file:**
```bash
./runtests.sh tests/test_example.py
```

### Adding New Tests
1. Inherit from `qps.testing.TestCase`.
2. Use `qps.testing.start_app()` in `setUpClass` to initialize the QGIS application.
3. Place test files in the `tests/` directory with the `test_*.py` prefix.

### Demonstration Test
Here is a simple example of a test using the QGIS API:

```python
import unittest
from qps.testing import TestCase, start_app
from qgis.core import QgsVectorLayer

class DemoTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        start_app()

    def test_vector_layer(self):
        """A simple test to demonstrate QGIS API usage within QPS tests."""
        layer = QgsVectorLayer("Point?field=id:integer", "test_layer", "memory")
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.name(), "test_layer")
```

## 3. Development Guidelines

### Code Style
- Follow PEP 8.
- Use explicit imports (avoid `from module import *`).
- QPS follows QGIS naming conventions where appropriate when interacting with the QGIS API, but generally adheres to standard Python snake_case for internal logic.
- use flake8 to check code style
- use bandit to check security issues

### UI Development
- UI files are located in `qps/ui/`.
- Use `qps.utils.loadUi` to load `.ui` files dynamically.
- Resource files are often prefixed with `:/` for Qt resource paths.

### Headless Testing
Always ensure tests can run with `QT_QPA_PLATFORM=offscreen`. Use `self.showGui(widget)` within `TestCase` which respects the `CI` environment variable to skip GUI display during automated runs.
