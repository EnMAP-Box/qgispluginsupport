# Create exemplary files with wavelength information
import datetime
import json
import os
from pathlib import Path
from typing import Union

import numpy as np
import pystac
import pystac.extensions.eo
from osgeo import gdal_array
from osgeo.gdal import Dataset, Band, VersionInfo
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


def create_test_datasets(output_dir: Union[str, Path]):
    output_dir = Path(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    array = np.arange(np.prod(shape)).reshape(shape)

    def create_dataset(filename: str, format='GTiff'):
        path = Path(output_dir) / filename
        ds: Dataset = gdal_array.SaveArray(array, path.as_posix(), format=format)
        ds.SetSpatialRef(sref)
        ds.SetGeoTransform(gt)
        return ds

    if True:
        ds = create_dataset('gdal_no_info.tif')
        ds = create_dataset('gdal_wl_only.tif')
        writeBandMetadata(ds, 'IMAGERY', 'CENTRAL_WAVELENGTH_UM', envi_wl)

        ds = create_dataset('gdal_wl_fwhm.tif')
        writeBandMetadata(ds, 'IMAGERY', 'CENTRAL_WAVELENGTH_UM', envi_wl)
        writeBandMetadata(ds, 'IMAGERY', 'FWHM_UM', envi_fwhm)

        # classic ENVI dataset with wl and wlu
        # see https://www.nv5geospatialsoftware.com/docs/enviheaderfiles.html
        ds = create_dataset('envi_wl_fwhm.bsq', format='ENVI')
        writeDatasetMetadata(ds, 'ENVI', 'wavelength', wrapEnviList(envi_wl))
        writeDatasetMetadata(ds, 'ENVI', 'fwhm', wrapEnviList(envi_fwhm))
        writeDatasetMetadata(ds, 'ENVI', 'wavelength units', envi_wlu)
        writeDatasetMetadata(ds, 'ENVI', 'bbl', wrapEnviList(envi_bbl))

        # just as above, using tif with ENVI-style metadata at dataset level
        ds = create_dataset('enmapbox_envidomain_dslevel.tif')
        writeDatasetMetadata(ds, 'ENVI', 'wavelength', envi_wl)
        writeDatasetMetadata(ds, 'ENVI', 'wavelength units', envi_wlu)
        writeDatasetMetadata(ds, 'ENVI', 'bbl', [0, 1])

        # just as above, using tif with ENVI-style metadata at band level
        ds = create_dataset('enmapbox_envidomain_bandlevel.tif')
        writeBandMetadata(ds, 'ENVI', 'wavelength', envi_wl)
        writeBandMetadata(ds, 'ENVI', 'wavelength units', envi_wlu)
        writeBandMetadata(ds, 'ENVI', 'bbl', [0, 1])

    if True:
        # metadata stored in a STAC json
        ds = create_dataset('staclike.tif')
        path = Path(ds.GetDescription())
        bn = os.path.splitext(path.name)[0]
        path_json = path.parent / f'{bn}.stac.json'
        item = pystac.Item(id=bn,
                           geometry=None,
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

        # can we open it with GDAL?


if __name__ == '__main__':
    DIR = Path(__file__).parent
    create_test_datasets(DIR)
