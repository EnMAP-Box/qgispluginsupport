import pathlib

# from qps
enmap = (pathlib.Path(__file__).parents[1] / 'qps' / 'enmap.tif').as_posix()
testvectordata = \
    (pathlib.Path(__file__).parents[1] / 'qps' / 'testvectordata.geojson').as_posix()
landcover = testvectordata
enmap_pixel = (pathlib.Path(__file__).parents[1] / 'qps' / 'testvectorpixelcenter.geojson').as_posix()
enmap_polygon = testvectordata

# from qpstestdata
hymap = (pathlib.Path(__file__).parent / 'hymap.tif').as_posix()
envi_bsq = (pathlib.Path(__file__).parent / 'envi').as_posix()
speclib = (pathlib.Path(__file__).parent / 'speclib.sli').as_posix()
speclib_labeled = \
    (pathlib.Path(__file__).parent / 'library_berlin.sli').as_posix()
ndvi_ts = (pathlib.Path(__file__).parent / 'ndvi_ts.tif').as_posix()
geojson = (pathlib.Path(__file__).parent / 'geojson' / 'profiles.geojson').as_posix()

DIR_ECOSIS = (pathlib.Path(__file__).parent / 'ecosis').as_posix()
DIR_SPECCHIO = (pathlib.Path(__file__).parent / 'specchio').as_posix()
ecosis_csv = (pathlib.Path(__file__).parent / 'ecosis.csv').as_posix()
DIR_ASD_BIN = (pathlib.Path(__file__).parent / 'asd' / 'bin').as_posix()
DIR_ASD_AS7 = (pathlib.Path(__file__).parent / 'asd' / 'as7').as_posix()
DIR_ASD_TXT = (pathlib.Path(__file__).parent / 'asd' / 'txt').as_posix()
DIR_ARTMO = (pathlib.Path(__file__).parent / 'artmo').as_posix()
