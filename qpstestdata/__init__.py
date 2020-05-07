import pathlib
enmap = (pathlib.Path(__file__).parent / 'enmap.tif').as_posix()
hymap = (pathlib.Path(__file__).parent / 'hymap.tif').as_posix()
timestack = (pathlib.Path(__file__).parent / '2010-2020_001-365_HL_TSA_LNDLG_NBR_TSS.tif').as_posix()
speclib = (pathlib.Path(__file__).parent / 'speclib.sli').as_posix()
speclib_labeled = (pathlib.Path(__file__).parent / 'library_berlin.sli').as_posix()
testvectordata = (pathlib.Path(__file__).parent / 'testvectordata.gpkg').as_posix()
landcover = testvectordata + '|layername=landcover'
enmap_pixel = testvectordata + '|layername=enmap_pixel'
ndvi_ts = (pathlib.Path(__file__).parent / 'ndvi_ts.tif').as_posix()

DIR_ECOSIS = (pathlib.Path(__file__).parent /  'ecosis').as_posix()
DIR_SPECCHIO = (pathlib.Path(__file__).parent /  'specchio').as_posix()
ecosis_csv = (pathlib.Path(__file__).parent / 'ecosis.csv').as_posix()
DIR_ASD_BIN = (pathlib.Path(__file__).parent / 'asd' / 'bin').as_posix()
DIR_ASD_TXT = (pathlib.Path(__file__).parent / 'asd' / 'txt').as_posix()
DIR_ARTMO = (pathlib.Path(__file__).parent /  'artmo').as_posix()