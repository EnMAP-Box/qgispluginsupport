from os.path import join, dirname
enmap = join(dirname(__file__), 'enmap.tif')
hymap = join(dirname(__file__), 'hymap.tif')
speclib = join(dirname(__file__), 'speclib.sli')
testvectordata = join(dirname(__file__), 'testvectordata.gpkg')
landcover = testvectordata + '|layername=landcover'
enmap_pixel = testvectordata + '|layername=enmap_pixel'


DIR_ECOSIS = join(dirname(__file__), 'ecosis')
DIR_SPECCHIO = join(dirname(__file__), 'specchio')
ecosis_csv = join(DIR_ECOSIS, 'ecosis.csv')
DIR_ASD_BIN = join(dirname(__file__), *['asd', 'bin'])
DIR_ASD_TXT = join(dirname(__file__), *['asd', 'txt'])