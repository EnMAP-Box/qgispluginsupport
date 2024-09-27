from pathlib import Path

_ROOT = Path(__file__).parents[1]
_QPS = _ROOT / 'qps'
DIR_TESTDATA = _ROOT / 'qpstestdata'

# from qps
enmap = _QPS / 'enmap.tif'
testvectordata = _QPS / 'testvectordata.geojson'
landcover = testvectordata
enmap_polygon = testvectordata
enmap_pixel = _QPS / 'testvectorpixelcenter.geojson'
enmap_multipolygon = _QPS / 'testvectordata_multipolygon.geojson'
enmap_multipoint = _QPS / 'testvectordata_multipoint.geojson'

# speclibs
speclib_geojson = DIR_TESTDATA / 'geojson' / 'speclib.geojson'

# from qpstestdata
hymap = DIR_TESTDATA / 'hymap.tif'
envi_bsq = DIR_TESTDATA / 'envi' / 'envi'
envi_hdr = DIR_TESTDATA / 'envi' / 'envi.hdr'
envi_sli = DIR_TESTDATA / 'envi' / 'speclib.sli'
envi_sli_hdr = DIR_TESTDATA / 'envi' / 'speclib.hdr'

# SVC spectral profiles
DIR_SVC = DIR_TESTDATA / 'svc'
svc_sig = DIR_SVC / 'HR.020824.0000.sig'
svc_sig_jpg = DIR_SVC / 'HR.020824.0000.sig.jpg'

DIR_SED = DIR_TESTDATA / 'spectralevolution'
spectral_evolution_raw = DIR_SED / 'darwin.raw'
spectral_evolution_sed = DIR_SED / 'darwin.sed'

ndvi_ts = DIR_TESTDATA / 'ndvi_ts.tif'

DIR_ECOSIS = DIR_TESTDATA / 'ecosis'

DIR_SPECCHIO = DIR_TESTDATA / 'specchio'
ecosis_csv = DIR_ECOSIS / 'excel_csv_example.csv'

DIR_ASD_BIN = DIR_TESTDATA / 'asd' / 'bin'
DIR_ASD_AS7 = DIR_TESTDATA / 'asd' / 'as7'
DIR_ASD_TXT = DIR_TESTDATA / 'asd' / 'txt'
DIR_ASD_GPS = DIR_TESTDATA / 'asd' / 'gps'
asd_with_gps = DIR_ASD_GPS / 'ww00045.asd'

DIR_ARTMO = DIR_TESTDATA / 'artmo'

del _ROOT, _QPS, Path
