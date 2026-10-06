import os
import re
from pathlib import Path
from typing import List

import json

SCRIPT_DIR = Path(__file__).parent / 'json'

with open(os.path.join(SCRIPT_DIR, 'bands.json'), 'r', encoding='utf-8') as f:
    BANDS = json.load(f)

with open(os.path.join(SCRIPT_DIR, 'constants.json'), 'r', encoding='utf-8') as f:
    CONSTANTS = json.load(f)

with open(os.path.join(SCRIPT_DIR, 'external_variables.json'), 'r', encoding='utf-8') as f:
    EXTERNAL_VARIABLES = json.load(f)

with open(os.path.join(SCRIPT_DIR, 'spectral-indices-dict.json'), 'r', encoding='utf-8') as f:
    SPECTRAL_INDICES = json.load(f)

# let short and common name be used to access the band defintion
for (short_name, b) in list(BANDS.items()):
    if short_name != b['short_name']:
        raise Exception(f'Wrong shortname: {short_name}')
    for k in ['long_name', 'common_name']:
        alias = b[k]
        if k in BANDS:
            raise Exception(f'{k} already used as alias: {alias}')
        BANDS[alias] = b

ALL_BANDS = set(BANDS.keys())
ALL_CONSTANTS = set()
ALL_EXTERNAL_VARS = set()

for category in CONSTANTS.values():
    ALL_CONSTANTS.update(category.keys())

for category in EXTERNAL_VARIABLES.values():
    ALL_EXTERNAL_VARS.update(category.keys())

ALL_VARIABLES = ALL_BANDS | ALL_CONSTANTS | ALL_EXTERNAL_VARS

V1_BAND_NAME_PATTERN = re.compile(r'\bR([a-z]+(?:_[a-z]+)?|\d+)\b')


def required_bands(formula: str) -> List[str]:
    pattern = r'\b([A-Za-z][A-Za-z0-9_]*)\b'
    matches = re.findall(pattern, formula)

    found = []
    for match in matches:
        if match in ALL_VARIABLES:
            found.append(match)

    v1_matches = V1_BAND_NAME_PATTERN.findall(formula)
    for match in v1_matches:
        v1_band_name = 'R' + match
        found.append(v1_band_name)

    return list(set(found))
