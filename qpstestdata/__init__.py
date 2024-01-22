from pathlib import Path

_ROOT = Path(__file__).parents[1]
_QPS = _ROOT / 'qps'
_TESTDATA = _ROOT / 'qpstestdata'

# from qps
enmap = (_QPS / 'enmap.tif').as_posix()
testvectordata = (_QPS / 'testvectordata.geojson').as_posix()
landcover = testvectordata
enmap_polygon = testvectordata
enmap_pixel = (_QPS / 'testvectorpixelcenter.geojson').as_posix()
enmap_multipolygon = (_QPS / 'testvectordata_multipolygon.geojson').as_posix()
enmap_multipoint = (_QPS / 'testvectordata_multipoint.geojson').as_posix()

# speclibs
speclib_geojson = (_TESTDATA / 'geojson' / 'speclib.geojson').as_posix()

# from qpstestdata
hymap = (_TESTDATA / 'hymap.tif').as_posix()
envi_bsq = (_TESTDATA / 'envi' / 'envi').as_posix()
envi_hdr = (_TESTDATA / 'envi' / 'envi.hdr').as_posix()
envi_sli = (_TESTDATA / 'envi' / 'speclib.sli').as_posix()
envi_sli_hdr = (_TESTDATA / 'envi' / 'speclib.hdr').as_posix()

ndvi_ts = (_TESTDATA / 'ndvi_ts.tif').as_posix()

DIR_ECOSIS = _TESTDATA / 'ecosis'
DIR_SPECCHIO = _TESTDATA / 'specchio'
ecosis_csv = (DIR_ECOSIS / 'excel_csv_example.csv').as_posix()
DIR_ASD_BIN = _TESTDATA / 'asd' / 'bin'
DIR_ASD_AS7 = _TESTDATA / 'asd' / 'as7'
DIR_ASD_TXT = _TESTDATA / 'asd' / 'txt'
DIR_ARTMO = _TESTDATA / 'artmo'

del _ROOT, _QPS, _TESTDATA, Path
