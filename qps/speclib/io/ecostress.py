from pathlib import Path
from typing import Union, List, Tuple

from qgis.PyQt.QtCore import QMetaType
from qgis.core import QgsFields, QgsField, QgsFeature
from ..core.spectralprofile import SpectralProfileFileReader, encodeProfileValueDict, ProfileEncoding


class ECOSTRESSSpectralProfileReader(SpectralProfileFileReader):
    _fields = SpectralProfileFileReader.standardFields()
    for k in [SpectralProfileFileReader.KEY_Reference,
              SpectralProfileFileReader.KEY_ReferenceTime]:
        _fields.remove(_fields.lookupField(k))

    def __init__(self, *args, **kwds):
        super().__init__(*args, **kwds)

    @classmethod
    def id(cls) -> str:
        return 'ECOSTRESS'

    @classmethod
    def shortHelp(cls) -> str:
        info = ('NASA JPL ECOSTRESS Spectral Library '
                '(<a href="https://speclib.jpl.nasa.gov/library">https://speclib.jpl.nasa.gov/library</a>)')
        return info

    @classmethod
    def canReadFile(cls, path: Union[str, Path]) -> bool:
        path = Path(path)

        if path.name.endswith('spectrum.txt'):
            return True

        return False

    def readDataLines(self, path: Path) -> Tuple[dict, dict]:

        with open(path, 'r') as f:
            lines = f.readlines()

        metadata = {}
        data = {}

        # State tracking
        in_data_section = False
        current_key = None
        current_value = []

        for line in lines:
            line = line.rstrip('\n')

            # Check if this is a data line (starts with a number or whitespace followed by number)
            stripped = line.strip()
            if stripped and not in_data_section:
                # Try to parse as data line
                parts = stripped.split()
                if len(parts) >= 2:
                    try:
                        x_val = float(parts[0])
                        y_val = float(parts[1])
                        # This looks like data, so we've entered the data section
                        in_data_section = True
                        data[x_val] = y_val
                        continue
                    except ValueError:
                        pass  # Not a data line, continue as metadata

            if in_data_section:
                # We're in the data section
                if stripped:
                    parts = stripped.split()
                    if len(parts) >= 2:
                        try:
                            x_val = float(parts[0])
                            y_val = float(parts[1])
                            data[x_val] = y_val
                        except ValueError:
                            # Not a valid data line, skip
                            pass
            else:
                # We're in the metadata section
                if ':' in line:
                    # Save previous key-value if exists
                    if current_key is not None:
                        metadata[current_key] = '\n'.join(current_value).strip()

                    # Start new key-value pair
                    key, value = line.split(':', 1)
                    current_key = key.strip()
                    current_value = [value.strip()]
                elif current_key is not None and line.strip():
                    # Continuation of previous value (multiline)
                    current_value.append(line.strip())
                elif not line.strip() and current_key is not None:
                    # Empty line - save current key-value and reset
                    metadata[current_key] = '\n'.join(current_value).strip()
                    current_key = None
                    current_value = []

        # Save last metadata entry if exists
        if current_key is not None:
            metadata[current_key] = '\n'.join(current_value).strip()

        return metadata, data

    def asFeatures(self) -> List[QgsFeature]:

        path = self.path()
        MD, DATA = self.readDataLines(path)

        path_ancilliary = path.parent / path.name.replace('spectrum.txt', 'ancillary.txt')
        if path_ancilliary.is_file():
            MD2, _ = self.readDataLines(path_ancilliary)
            MD.update(MD2)

        sorted_keys = sorted(DATA.keys())
        x = [float(k) for k in sorted_keys]
        y = [float(DATA[k]) for k in sorted_keys]

        xUnit = MD.get('X Units', None)
        if xUnit == 'Wavelength (micrometers)':
            xUnit = 'μm'

        yUnit = MD.get('Y Units', None)

        fields = QgsFields(self._fields)
        to_int = ['Number of X Values']
        to_float = ['Fist X Value', 'Last X Value']
        to_skip = ['X Units', 'Y Units', 'Name']

        for k in MD.keys():
            if k in to_int:
                fields.append(QgsField(k, QMetaType.Type.Int))
            elif k in to_float:
                fields.append(QgsField(k, QMetaType.Type.Double))
            elif k not in to_skip:
                fields.append(QgsField(k, QMetaType.Type.QString))

        f = QgsFeature(fields)

        profileData = {'x': x, 'y': y, 'xUnit': xUnit, 'yUnit': yUnit}

        dump = encodeProfileValueDict(profileData, ProfileEncoding.Dict)
        f.setAttribute(self.KEY_Target, dump)
        f.setAttribute(self.KEY_Name, MD.get('Name', ''))
        f.setAttribute(self.KEY_Path, str(path))

        fieldnames = fields.names()
        for k, v in MD.items():
            if k not in fieldnames:
                continue
            if k in to_int:
                f.setAttribute(k, int(v))
            elif k in to_float:
                f.setAttribute(k, float(v))
            elif k not in to_skip:
                f.setAttribute(k, str(v))

        features = [f]

        return features
