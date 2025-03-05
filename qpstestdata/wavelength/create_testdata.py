# Create exemplary files with wavelength information
import datetime
import json
import os
import re
from pathlib import Path
from typing import Union

import numpy as np
import pystac
import pystac.extensions.eo
from osgeo import gdal_array, gdal
from osgeo.gdal import Dataset, Band, VersionInfo, Open, Info, InfoOptions
from osgeo.osr import SpatialReference, UseExceptions
from pystac.extensions.eo import EOExtension

UseExceptions()

# mini dataset with 2 bands
version = VersionInfo('')
envi_wl = [400, 500]
envi_wlu = 'nm'
envi_fwhm = [10, 20]
envi_bbl = [0, 1]

settings = {
    'missing.tif': {},
    'envistyle_wl.tif': {
        'dsMD': {'ENVI':
                     {'wavelength': envi_wl}}
    },
}

# somewhere around null-island
gt = [0, 0.25, 0,
      0, 0, -0.25]
sref = SpatialReference()
sref.ImportFromEPSG(4326)
sref.Validate()
shape = (2, 2, 5)  # bands, heigth, width


def writeDatasetMetadata(ds: Dataset, domain: str, key: str, values: Union[str, list]):
    if isinstance(values, list):
        values = ','.join([str(v) for v in values])
    ds.SetMetadataItem(key, values, domain)


def writeBandMetadata(ds: Dataset, domain: str, key: str, values: list):
    for b, value in zip(range(ds.RasterCount), values):
        band: Band = ds.GetRasterBand(b + 1)
        band.SetMetadataItem(key, str(value), domain)


def wrapEnviList(values: list):
    values = ','.join([str(v) for v in values])
    return f'{{{values}}}'


def dataset_summary(output_dir: Union[str, Path]) -> str:
    rx_image_files = re.compile(r'\.(tiff?|bsq)$')

    lines = ['# Wavelength Info Example Datasets',
             '',
             'Do not modify images manually, as they are created by create_testdata.py']

    col1 = ['Dataset']
    col2 = ['Notes']
    for item in os.scandir(output_dir):
        if item.is_file() and rx_image_files.search(item.name):
            ds: Dataset = Open(item.path)

            info = ds.GetMetadataItem('description')
            if info is None:
                info = 'tbd.'
            col1.append(item.name)
            col2.append(info)

    def format_cols(col: list) -> list:
        l = max([len(s) for s in col])
        values = [s.ljust(l) for s in col]
        # make 1st entry a markdown header
        values.insert(1, '-' * l)

        return values

    col1 = format_cols(col1)
    col2 = format_cols(col2)

    for c1, c2 in zip(col1, col2):
        lines.append(f"| {c1} | {c2} |")

    return '\n'.join(lines)


def create_test_datasets(output_dir: Union[str, Path]):
    output_dir = Path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    array = np.arange(np.prod(shape)).reshape(shape)

    def create_dataset(filename: str, description=None, format='GTiff'):
        path = Path(output_dir) / filename
        ds: Dataset = gdal_array.SaveArray(array, path.as_posix(), format=format)
        ds.SetSpatialRef(sref)
        ds.SetGeoTransform(gt)
        if description:
            ds.SetMetadataItem('description', description)
        return ds

    # no wavelength info
    ds = create_dataset('gdal_no_info.tif',
                        'no wavelength info')

    # only central wavelength
    ds = create_dataset('gdal_wl_only.tif',
                        'gdal 3.10+ with IMAGERY:CENTRAL_WAVELENGTH_UM')
    writeBandMetadata(ds, 'IMAGERY', 'MYINFO', 'test')
    writeBandMetadata(ds, 'IMAGERY', 'CENTRAL_WAVELENGTH_UM', [v / 1000 for v in envi_wl])

    ds = create_dataset('gdal_wl_fwhm.tif',
                        'gdal 3.10+ with IMAGERY:CENTRAL_WAVELENGTH_UM and IMAGERY:FWHM_UM')

    writeBandMetadata(ds, 'IMAGERY', 'CENTRAL_WAVELENGTH_UM', envi_wl)
    writeBandMetadata(ds, 'IMAGERY', 'FWHM_UM', envi_fwhm)

    # classic ENVI dataset with wl and wlu
    # see https://www.nv5geospatialsoftware.com/docs/enviheaderfiles.html
    ds = create_dataset('envi_wl_fwhm.bsq',
                        'classic ENVI BSQ with wavelength, wavelength units, fwhm, and bbl',
                        format='ENVI')
    writeDatasetMetadata(ds, 'ENVI', 'wavelength', wrapEnviList(envi_wl))
    writeDatasetMetadata(ds, 'ENVI', 'fwhm', wrapEnviList(envi_fwhm))
    writeDatasetMetadata(ds, 'ENVI', 'wavelength units', envi_wlu)
    writeDatasetMetadata(ds, 'ENVI', 'bbl', wrapEnviList(envi_bbl))

    # only central wavelength - expect nanometers
    ds = create_dataset('envi_wl_implicit_nm.bsq',
                        'ENVI BSQ with missing wavelength units, expect nm')
    writeDatasetMetadata(ds, 'ENVI', 'wavelength', wrapEnviList(envi_wl))

    # only central wavelength - expect micrometers
    ds = create_dataset('envi_wl_implicit_um.bsq',
                        'ENVI BSQ with missing wavelength units, expect micrometers')
    writeDatasetMetadata(ds, 'ENVI', 'wavelength', wrapEnviList([v / 1000 for v in envi_wl]))

    # just as above, using tif with ENVI-style metadata at dataset level
    ds = create_dataset('enmapbox_envidomain_dslevel.tif',
                        'tif with ENVI domain at dataset level')
    writeDatasetMetadata(ds, 'ENVI', 'wavelength', envi_wl)
    writeDatasetMetadata(ds, 'ENVI', 'wavelength units', envi_wlu)
    writeDatasetMetadata(ds, 'ENVI', 'bbl', [0, 1])

    # just as above, using tif with ENVI-style metadata at band level
    ds = create_dataset('enmapbox_envidomain_bandlevel.tif',
                        'tif with ENVI domain at band level')
    writeBandMetadata(ds, 'ENVI', 'wavelength', envi_wl)
    writeBandMetadata(ds, 'ENVI', 'wavelength units', envi_wlu)
    writeBandMetadata(ds, 'ENVI', 'bbl', [0, 1])

    if True:
        # metadata stored in a STAC json
        ds = create_dataset('staclike.tif', 'dataset with metadata stored in *.stack.json')
        path = Path(ds.GetDescription())

        infoOptions = InfoOptions(format='json')
        infos = Info(ds, options=infoOptions)
        del ds
        s = ""
        bn = os.path.splitext(path.name)[0]
        path_json = path.parent / f'{bn}.stac.json'
        item = pystac.Item(id=bn,
                           geometry=infos['wgs84Extent'],
                           bbox=None,
                           datetime=datetime.datetime.today(),
                           properties={})
        EOExtension.add_to(item)
        bands = []
        for b, (wl, fwhm) in enumerate(zip(envi_wl, envi_fwhm)):
            bands.append({
                'name': f'Band {b + 1} name',
                'description': f'This is band {b + 1}',
                'center_wavelength': wl / 100,
                'full_width_half_max': fwhm / 100,
            })

        eo_ext = EOExtension.ext(item, add_if_missing=True)
        eo_ext.bands = [pystac.extensions.eo.Band.create(**band) for band in bands]

        item.add_asset("image",
                       pystac.Asset(
                           href=path.name,
                           media_type=pystac.MediaType.GEOTIFF,
                           roles=['data'],
                       ))
        item_json = item.to_dict()
        with open(path_json, 'w') as f:
            json.dump(item_json, f, indent=2)

    summary = dataset_summary(output_dir)

    with open(output_dir / 'readme.md', 'w') as file:
        file.write(summary)


def read_stac():
    p0 = Path(__file__).parent / 'tmp/test.json'
    p1 = Path(__file__).parent / 'staclike.stac.json'

    assert p0.is_file()
    assert p1.is_file()
    # see https://gdal.org/en/stable/drivers/raster/stacit.html
    os.chdir(p0.parent)
    ds0: Dataset = gdal.Open(p0.name)
    ds0.RasterYSize

    os.chdir(p1.parent)
    ds1: Dataset = gdal.Open(f'STACIT:"{p1.name}":asset=image')
    s = ""


if __name__ == '__main__':
    DIR = Path(__file__).parent
    # read_stac()
    create_test_datasets(DIR)
