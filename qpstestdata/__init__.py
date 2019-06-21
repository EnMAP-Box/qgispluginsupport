from os.path import join, dirname
enmap = join(dirname(__file__), 'enmap.tif')
hymap = join(dirname(__file__), 'hymap.tif')
speclib = join(dirname(__file__), 'speclib.sli')
testvectordata = join(dirname(__file__), 'testvectordata.gpkg')
landcover = testvectordata + '|layername=landcover'
enmap_pixel = testvectordata + '|layername=enmap_pixel'
