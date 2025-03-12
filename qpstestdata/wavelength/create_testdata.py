# Create exemplary files with wavelength information
import datetime
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

rx_image_files = re.compile(r'\.(tiff?|bsq)$')


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


def create_stac_item(path_img: Union[str, Path], stac_root: Union[str, Path]) -> pystac.Item:
    """
    :param path_img: path of raster image
    :param stac_root: path of root into which the final stac.json(s) will be stored
    :return:
    """
    path_img = Path(path_img)
    stac_root = Path(stac_root)
    assert path_img.is_file()
    assert stac_root.is_dir()
    path_rel = path_img.relative_to(stac_root)

    ds: Dataset = Open(path_img.as_posix())
    assert isinstance(ds, Dataset)

    infoOptions = InfoOptions(format='json')
    infos = Info(ds, options=infoOptions)
    del ds
    cc = infos['cornerCoordinates']
    # bbox = [bounds.left, bounds.bottom, bounds.right, bounds.top]
    bbox = [min([c[0] for c in cc.values()]),
            min([c[1] for c in cc.values()]),
            max([c[0] for c in cc.values()]),
            max([c[1] for c in cc.values()])
            ]

    item = pystac.Item(id=path_img.name,
                       geometry=infos.get('wgs84Extent'),
                       bbox=bbox,
                       # collection='MyCollection',
                       datetime=datetime.datetime.now(tz=datetime.timezone.utc),
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

    asset = pystac.Asset(
        title=path_img.name,
        href=path_rel.as_posix(),
        media_type=pystac.MediaType.GEOTIFF,
        roles=['data'],
    )
    item.add_asset(path_img.name, asset)
    eo_on_asset = EOExtension.ext(item.assets[path_img.name])
    eo_on_asset.apply(bands=eo_ext.bands)

    pystac.validation.validate(item)
    return item


def create_stac_item_collection(output_dir: Union[str, Path], path_json: Union[str, Path]) -> pystac.ItemCollection:
    path_json = Path(path_json)
    stac_root = path_json.parent
    assert stac_root.is_dir()
    items = []
    for e in os.scandir(output_dir):
        if e.is_file() and rx_image_files.search(e.name):
            items.append(create_stac_item(e.path, stac_root))

    spatial_extent = pystac.SpatialExtent(bboxes=[item.bbox for item in items])
    dates = sorted([item.datetime for item in items])
    temporal_extent = pystac.TemporalExtent(intervals=[dates[0], dates[-1]])

    collection_extent = pystac.Extent(spatial=spatial_extent, temporal=temporal_extent)

    collection = pystac.Collection(id='MyCollection',
                                   description='Test files',
                                   extent=collection_extent,
                                   )
    collection.add_items(items)
    collection.normalize_hrefs(path_json.as_posix())
    # collection.catalog_type = pystac.CatalogType.RELATIVE_PUBLISHED
    # collection.normalize_and_save(root_href=path_json.as_posix(), catalog_type=pystac.CatalogType.SELF_CONTAINED)
    collection.validate()

    collection.validate_all()

    collection.save_object(path_json.as_posix())

    return collection


def dataset_summary(output_dir: Union[str, Path]) -> str:
    lines = ['# Wavelength Info Example Datasets\n\n',
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

    # write table
    lines.append('')
    for c1, c2 in zip(col1, col2):
        lines.append(f"| {c1} | {c2} |")
    lines.append('')
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
                        'ENVI BSQ with missing wavelength units, expect nm',
                        format='ENVI', )
    writeDatasetMetadata(ds, 'ENVI', 'wavelength', wrapEnviList(envi_wl))

    # only central wavelength - expect micrometers
    ds = create_dataset('envi_wl_implicit_um.bsq',
                        'ENVI BSQ with missing wavelength units, expect micrometers',
                        format='ENVI', )
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

    del ds  # Important! Ensures that all infos are written
    if True:
        # collect all image in a STAC API ItemCollection
        path_json = output_dir / 'stac.json'
        collection = create_stac_item_collection(output_dir, path_json)
        pystac.validation.validate(collection)

    summary = dataset_summary(output_dir)

    with open(output_dir / 'readme.md', 'w') as file:
        file.write(summary)


def read_stac():
    path = Path(__file__).parent / 'stac.json'
    # ds: Dataset = gdal.Open(path.as_posix())
    ds1: Dataset = gdal.Open(f'STACIT:"{path.as_posix()}":asset=image')
    s = ""


if __name__ == '__main__':
    DIR = Path(__file__).parent
    create_test_datasets(DIR)
    # read_stac()
