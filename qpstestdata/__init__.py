from pathlib import Path

_ROOT = Path(__file__).parents[1]
_QPS = _ROOT / 'qps'
DIR_TESTDATA = _ROOT / 'qpstestdata'

# from qps
enmap = (_QPS / 'enmap.tif').as_posix()
testvectordata = (_QPS / 'testvectordata.geojson').as_posix()
landcover = testvectordata
enmap_polygon = testvectordata
enmap_pixel = (_QPS / 'testvectorpixelcenter.geojson').as_posix()
enmap_multipolygon = (_QPS / 'testvectordata_multipolygon.geojson').as_posix()
enmap_multipoint = (_QPS / 'testvectordata_multipoint.geojson').as_posix()

# speclibs
speclib_geojson = (DIR_TESTDATA / 'geojson' / 'speclib.geojson').as_posix()

# from qpstestdata
hymap = (DIR_TESTDATA / 'hymap.tif').as_posix()
envi_bsq = (DIR_TESTDATA / 'envi' / 'envi').as_posix()
envi_hdr = (DIR_TESTDATA / 'envi' / 'envi.hdr').as_posix()
envi_sli = (DIR_TESTDATA / 'envi' / 'speclib.sli').as_posix()
envi_sli_hdr = (DIR_TESTDATA / 'envi' / 'speclib.hdr').as_posix()

# SVC spectral profiles
DIR_SVC = (DIR_TESTDATA / 'svc')
svc_sig = DIR_SVC / 'HR.020824.0000.sig'
svc_sig_jpg = DIR_SVC / 'HR.020824.0000.sig.jpg'

DIR_SED = (DIR_TESTDATA / 'spectralevolution')
ndvi_ts = (DIR_TESTDATA / 'ndvi_ts.tif').as_posix()

DIR_ECOSIS = DIR_TESTDATA / 'ecosis'
DIR_SPECCHIO = DIR_TESTDATA / 'specchio'
ecosis_csv = (DIR_ECOSIS / 'excel_csv_example.csv').as_posix()
DIR_ASD_BIN = DIR_TESTDATA / 'asd' / 'bin'
DIR_ASD_AS7 = DIR_TESTDATA / 'asd' / 'as7'
DIR_ASD_TXT = DIR_TESTDATA / 'asd' / 'txt'
DIR_ARTMO = DIR_TESTDATA / 'artmo'

del _ROOT, _QPS, Path
