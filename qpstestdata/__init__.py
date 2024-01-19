import pathlib

_ROOT = pathlib.Path(__file__).parents[1]
_QPS = _ROOT / 'qps'
_TESTDATA = _ROOT / 'qpstestdata'

# from qps
enmap = _QPS / 'enmap.tif'
testvectordata = _QPS / 'testvectordata.geojson'
landcover = testvectordata
enmap_pixel = _QPS / 'testvectorpixelcenter.geojson'
enmap_polygon = testvectordata
enmap_multipolygon = _QPS / 'testvectordata_multipolygon.geojson'
enmap_multipoint = _QPS / 'testvectordata_multipoint.geojson'

# speclibs
speclib_geojson = _TESTDATA / 'geojson' / 'speclib.geojson'

# from qpstestdata
hymap = _TESTDATA / 'hymap.tif'
envi_bsq = _TESTDATA / 'envi' / 'envi'
envi_hdr = _TESTDATA / 'envi' / 'envi.hdr'
envi_sli = _TESTDATA / 'envi' / 'speclib.sli'
envi_sli_hdr = _TESTDATA / 'envi' / 'speclib.hdr'

ndvi_ts = _TESTDATA / 'ndvi_ts.tif'
geojson = _TESTDATA / 'geojson' / 'profiles.geojson'

DIR_ECOSIS = _TESTDATA / 'ecosis'
DIR_SPECCHIO = _TESTDATA / 'specchio'
ecosis_csv = _TESTDATA / 'excel_csv_example.csv'
DIR_ASD_BIN = _TESTDATA / 'asd' / 'bin'
DIR_ASD_AS7 = _TESTDATA / 'asd' / 'as7'
DIR_ASD_TXT = _TESTDATA / 'asd' / 'txt'
DIR_ARTMO = _TESTDATA / 'artmo'

del _ROOT, _QPS, _TESTDATA
