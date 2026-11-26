# QGIS Plugin Support Skill

## Description

This skill provides guidance and assistance for developing, testing, and maintaining QGIS plugins using the qgispluginsupport repository structure and tools.

## Available Commands

## Python Environment Resolution

Always determine the active PyCharm project Python interpreter dynamically before running Python, pytest, or module checks.

- Do not hardcode a path to `python` or `venv/bin/python`.
- On Linux/macOS, determine the interpreter by running:
  ```bash
  PYTHON_BIN=$(grep -oE '<option name="project-jdk-name" value="[^"]+"' .idea/misc.xml | cut -d'"' -f4)
  ```
  If this returns an absolute path, use `$PYTHON_BIN`. If it returns a venv name (e.g., `Python 3.11 (my-env)`), check `.idea/misc.xml` or `.idea/*.iml` for the exact SDK home path, or run `which python` inside the PyCharm terminal environment.
- Execute Python commands using the resolved interpreter path:
  ```bash
  <resolved-python-path> -m pytest
  ```

### Running Tests
- Run all tests: `bash runtests.sh`
- Run specific test file: `bash runtests.sh tests/speclib/test_<testname>.py`
- Run tests with coverage: `bash runtests.sh --cov`

**Important**: Unit tests must be run using the Python interpreter configured in PyCharm.

**CI Environment**: The `runtests.sh` script automatically sets `CI=True` and `QT_QPA_PLATFORM=offscreen` to ensure tests run in non-interactive environments without blocking GUI elements.

**How to use the correct interpreter:**

1. **Determine the PyCharm interpreter dynamically**:
   ```bash
   PYTHON_BIN=$(grep -oE '<option name="project-jdk-name" value="[^"]+"' .idea/misc.xml | cut -d'"' -f4)
   echo "PyCharm interpreter: $PYTHON_BIN"
   ```

2. **If using Conda environments**, determine the path from the SDK name:
   ```bash
   # Check for qps_latest environment
   CONDA_BASE=$(conda info --base)
   PYTHON_BIN="$CONDA_BASE/envs/qps_latest/bin/python"
   ```

3. **Using the resolved interpreter**:
   ```bash
   PYTHON_EXECUTABLE="$PYTHON_BIN" bash runtests.sh
   # Or directly:
   "$PYTHON_BIN" -m pytest --no-cov-on-fail
   ```

4. **Using PyCharm's built-in terminal**: Open the terminal in PyCharm (which automatically uses the project interpreter) and run:
   ```bash
   bash runtests.sh
   ```

5. **For pytest directly in PyCharm**: Configure the test runner to use the project interpreter (found in PyCharm's Run Configuration settings)

**Verify the interpreter before running tests:**
```bash
# Determine the interpreter dynamically
PYTHON_BIN=$(grep -oE '<option name="project-jdk-name" value="[^"]+"' .idea/misc.xml | cut -d'"' -f4)
"$PYTHON_BIN" --version
"$PYTHON_BIN" -c "from qgis.core import Qgis; print(f'QGIS version: {Qgis.QGIS_VERSION}')"
```

**QGIS version must be >= 4.0**. Run the following to verify:
```bash
PYTHON_BIN=$(grep -oE '<option name="project-jdk-name" value="[^"]+"' .idea/misc.xml | cut -d'"' -f4)
"$PYTHON_BIN" -c "from qgis.core import Qgis; import sys; sys.exit(0 if Qgis.QGIS_VERSION.startswith('4') else 1)" && echo "QGIS version check passed" || echo "QGIS version check failed - QGIS 4.x required"
```

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

### Running Tests
- Use `bash runtests.sh` which respects `PYTHON_EXECUTABLE`
- Determine the PyCharm interpreter dynamically: `grep -oE '<option name="project-jdk-name" value="[^"]+"' .idea/misc.xml | cut -d'"' -f4`
- For Conda environments, the interpreter is typically `~/miniforge3/envs/qps_latest/bin/python`

**CI Environment**: The `runtests.sh` script automatically sets `CI=True`, `QT_QPA_PLATFORM=offscreen`, and `QGIS_CONTINUOUS_INTEGRATION_RUN=true` to ensure tests run in non-interactive environments without blocking GUI elements. When running tests manually (not using `runtests.sh`), ensure these environment variables are set.

**Verify QGIS version before running tests:**
```bash
# Determine the interpreter dynamically
PYTHON_BIN=$(grep -oE '<option name="project-jdk-name" value="[^"]+"' .idea/misc.xml | cut -d'"' -f4)
"$PYTHON_BIN" -c "from qgis.core import Qgis; print(f'QGIS {Qgis.QGIS_VERSION}')"
```
QGIS version must be >= 4.0

### Running Tests in CI/Environment
**Important**: When running unit tests in CI or any non-interactive environment, set `CI=True` as an environment variable to prevent GUI elements from blocking tests.

```bash
# Set CI environment variable before running tests
CI=True python -m pytest tests/
# Or
CI=True bash runtests.sh
```

**Why**: Without `CI=True`, GUI elements (e.g., dialogs, canvas rendering) may attempt to open and block the test execution. The `CI=True` variable signals the test framework to use offscreen rendering and skip interactive operations.

## Unit Test Best Practices

### QgsProject Management
**Always use a local `QgsProject` instance in unit tests, never add layers to the global `QgsProject.instance()`:**

```python
# Correct: Use a local project instance
p = QgsProject()
p.addMapLayers([layer1, layer2])
# ... test logic ...
p.removeAllMapLayers()  # Clean up

# Incorrect: Do not use global project instance
QgsProject.instance().addMapLayers([layer1, layer2])  # AVOID THIS
```

**Reason**: Using the global project instance can cause tests to interfere with each other, leading to:
- Unpredictable test results
- Memory leaks from accumulated layers
- Race conditions in CI/CD environments

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
from qgis.core import QgsProject

start_app()

class MyTests(TestCase):
    def test_example(self):
        # Create a local project instance (NOT QgsProject.instance())
        self.project = QgsProject()
        
        # Create test data
        speclib = TestObjects.createSpectralLibrary()
        self.project.addMapLayers([speclib])
        
        # Test functionality
        self.assertIsNotNone(speclib)
        
    def tearDown(self):
        # Clean up local project (not the global instance)
        self.project.removeAllMapLayers()
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

- QGIS version: Currently using QGIS 3.44.15 (compatibility note: some tests may require QGIS 4.x)
- Python version: 3.14
- PyQtGraph Qt library: PyQt6 (must match QGIS Qt version)

**Compatibility Note**: The `qpspluginsupport` repository has some tests that require QGIS 4.x features (e.g., `QgsProcessingAlgorithmWidgetBase`). Tests in `tests/speclib/test_speclib_plotting.py` that rely on `SpectralLibraryWidget` may not run on QGIS 3.44. To run tests:
1. Check QGIS version: `python -c "from qgis.core import Qgis; print(Qgis.QGIS_VERSION)"`
2. QGIS 4.x required for full test coverage
3. For QGIS 3.44, tests that use `SpectralProfilePlotModel` directly (without full widgets) may still work

## QGIS C++ API Reference

The C++ definitions for the QGIS API can be found in a parallel repository structure:

```
<parent>/
├── qgispluginsupport/      # This repository (plugin support)
└── QGIS/                   # QGIS main repository
    ├── src/               # QGIS C++ source code
    │   ├── core/          # QGIS core classes (QgsVectorLayer, QgsProcessingAlgorithm, etc.)
    │   ├── gui/           # QGIS GUI classes
    │   ├── python/        # Python bindings
    │   └── ...
    └── ...
```

When working in this repository at `<parent>/qgispluginsupport`:
- The QGIS C++ source code is located at `<parent>/QGIS/src`
- QGIS Python API documentation in this repository references C++ classes from the QGIS repository
- For C++ development, you may need to build QGIS from the `<parent>/QGIS` source

Use the QGIS C++ API documentation and source code when:
- Understanding the underlying implementation of QGIS classes
- Debugging issues that require stepping through C++ code
- Contributing to QGIS itself
