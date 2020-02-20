from ..utils import *
from osgeo import gdal, ogr, osr
import PyQt5.pyrcc_main

DIR_QGIS_REPO = os.environ.get('DIR_QGIS_REPO')

DIR_REPO = findUpwardPath(__file__, '.git')
if not DIR_REPO is None:
    DIR_REPO = dn(DIR_REPO)


def remove_shortcutVisibleInContextMenu(rootDir):
    """
    This routine searches for *.ui files and removes the shortcutVisibleInContextMenu <property> from which causes errors with Qt < 5.10.
    :param rootDir: str
    """

    uiFiles = file_search(rootDir, '*.ui', recursive=True)

    regex = re.compile(r'<property name="shortcutVisibleInContextMenu">[^<]*<bool>true</bool>[^<]*</property>', re.MULTILINE)


    for p in uiFiles:
        assert isinstance(p, str)
        assert os.path.isfile(p)

        with open(p, encoding='utf-8') as f:
            xml = f.read()

        if 'shortcutVisibleInContextMenu' in xml:
            print('remove "shortcutVisibleInContextMenu" properties from {}'.format(p))
            xml = regex.sub('', xml)

            with open(p, 'w', encoding='utf-8') as f:
                f.write(xml)


def rasterize_vector_labels(pathRef, pathDst, pathShp, label_field, band_ref=1, label_layer=0):
    drvMemory = ogr.GetDriverByName('Memory')
    drvMEM = gdal.GetDriverByName('MEM')

    dsShp = drvMemory.CopyDataSource(ogr.Open(pathShp),'')
    dsRef = gdal.Open(pathRef)

    assert label_layer < dsShp.GetLayerCount()
    lyr_tmp1 = dsShp.GetLayerByIndex(label_layer)
    lyr_name1 = lyr_tmp1.GetName()
    lyr_def1 = lyr_tmp1.GetLayerDefn()
    field_names1 = [lyr_def1.GetFieldDefn(f).GetName() for f  in range(lyr_def1.GetFieldCount())]
    assert label_field in field_names1, 'field {} does not exist. possible names are: {}'.format(label_field, ','.join(field_names1))
    fieldDef = lyr_def1.GetFieldDefn(field_names1.index(label_field))

    IS_CATEGORICAL = fieldDef.GetType() == ogr.OFTString
    label_names = None
    if IS_CATEGORICAL:
        #label_names = dsRef.GetRasterBand(band_ref).GetCategoryNames()
        label_names = set()
        for feat in lyr_tmp1:
            value = str(feat.GetField(label_field)).strip()
            if len(value) > 0:
                label_names.add(value)
            #get label names from values
        lyr_tmp1.ResetReading()
        label_names = sorted(list(label_names))
        if not 'unclassified' in label_names:
            label_names.insert(0, 'unclassified')
        label_values = list(range(len(label_names)))


    # transform geometries into target reference system
    for name in [lyr.GetName() for lyr in dsShp if lyr.GetName() != lyr_name1]:
        dsShp.Delete(name)
    lyr_name2 = lyr_name1 + '2'
    srs = osr.SpatialReference()
    srs.ImportFromWkt(dsRef.GetProjection())

    trans = None
    if not srs.IsSame(lyr_tmp1.GetSpatialRef()):
        trans = osr.CoordinateTransformation(lyr_tmp1.GetSpatialRef(), srs)
    lyr_tmp2 = dsShp.CreateLayer(lyr_name2, srs=srs, geom_type=ogr.wkbPolygon)


    if IS_CATEGORICAL:
        lyr_tmp2.CreateField(ogr.FieldDefn(label_field, ogr.OFTInteger))
        no_data = 0
    else:
        lyr_tmp2.CreateField(ogr.FieldDefn(label_field, fieldDef.GetType()))
        no_data = dsRef.GetRasterBand(band_ref).GetNoDataValue()

    n = 0
    for feature_src in lyr_tmp1:
        value = feature_src.GetField(label_field)
        if value is None:
            continue

        if IS_CATEGORICAL:
            if value in label_names:
                value = label_values[label_names.index(value)]
            elif value not in label_values:
                print('Not found in prediction labels: {}'.format(value))

        if value is not None:
            geom = feature_src.GetGeometryRef().Clone()
            if trans:
                geom.Transform(trans)

            feature_tmp = ogr.Feature(lyr_tmp2.GetLayerDefn())
            feature_tmp.SetGeometry(geom)
            feature_tmp.SetField(label_field, value)
            lyr_tmp2.CreateFeature(feature_tmp)
            lyr_tmp2.SyncToDisk()
            n += 1

    lyr_tmp2.ResetReading()
    ns = dsRef.RasterXSize
    nl = dsRef.RasterYSize



    dsRasterTmp = drvMEM.Create('', ns, nl, eType=gdal.GDT_Int32)
    dsRasterTmp.SetProjection(dsRef.GetProjection())
    dsRasterTmp.SetGeoTransform(dsRef.GetGeoTransform())
    band_ref = dsRasterTmp.GetRasterBand(1)
    assert type(band_ref) is gdal.Band
    if IS_CATEGORICAL:
        band_ref.Fill(0)  # by default = unclassified = 0
    elif no_data is not None:
        band_ref.Fill(no_data)
        band_ref.SetNoDataValue(no_data)

    # print('Burn geometries...')
    # http://www.gdal.org/gdal__alg_8h.html for details on options
    options = ['ATTRIBUTE={}'.format(label_field)
        , 'ALL_TOUCHED=TRUE']
    err = gdal.RasterizeLayer(dsRasterTmp, [1], lyr_tmp2, options=options)
    assert err in [gdal.CE_None, gdal.CE_Warning], 'Something failed with gdal.RasterizeLayer'

    band_ref = dsRasterTmp.GetRasterBand(1)
    validated_labels = band_ref.ReadAsArray()
    if IS_CATEGORICAL:
        #set classification info
        import matplotlib.cm
        label_colors = list()
        cmap = matplotlib.cm.get_cmap('brg', n)
        for i in range(n):
            if i == 0:
                c = (0,0,0, 255)
            else:
                c = tuple([int(255*c) for c in cmap(i)])
            label_colors.append(c)

        CT = gdal.ColorTable()
        names = list()
        for value in sorted(label_values):
            i = label_values.index(value)
            names.append(label_names[i])
            CT.SetColorEntry(value, label_colors[i])

        band_ref.SetCategoryNames(names)
        band_ref.SetColorTable(CT)

        s = ""
    drvDst = dsRef.GetDriver()
    drvDst.CreateCopy(pathDst, dsRasterTmp)


def getDOMAttributes(elem):
    assert isinstance(elem, QDomElement)
    values = dict()
    attributes = elem.attributes()
    for a in range(attributes.count()):
        attr = attributes.item(a)
        values[str(attr.nodeName())] = attr.nodeValue()
    return values


def compileResourceFiles(dirRoot:str, targetDir:str=None, suffix:str= '_rc.py'):
    """
    Searches for *.ui files and compiles the *.qrc files they use.
    :param dirRoot: str, root directory, in which to search for *.qrc files or a list of *.ui file paths.
    :param targetDir: str, output directory to write the compiled *.py files to.
           Defaults to the *.qrc's directory
    """
    # find ui files
    if not isinstance(dirRoot, pathlib.Path):
        dirRoot = pathlib.Path(dirRoot)
    assert dirRoot.is_dir(), '"dirRoot" is not a directory: {}'.format(dirRoot)
    dirRoot = dirRoot.resolve()

    ui_files = list(file_search(dirRoot, '*.ui', recursive=True))

    qrc_files = []
    qrc_files_skipped = []
    doc = QDomDocument()

    for ui_file in ui_files:
        qrc_dir = pathlib.Path(ui_file).parent
        doc.setContent(QFile(ui_file))
        includeNodes = doc.elementsByTagName('include')
        for i in range(includeNodes.count()):
            attr = getDOMAttributes(includeNodes.item(i).toElement())
            if 'location' in attr.keys():
                location = attr['location']
                qrc_path = (qrc_dir / pathlib.Path(location)).resolve()
                if not qrc_path.exists():
                    info = ['Broken *.qrc location in {}'.format(ui_file),
                            ' `location="{}"`'.format(location)]
                    print('\n'.join(info), file=sys.stderr)
                    continue

                elif not qrc_path.as_posix().startswith(dirRoot.as_posix()):
                    # skip resource files out of the root directory
                    if not qrc_path in qrc_files_skipped:
                        qrc_files_skipped.append(qrc_path)

                    continue
                elif qrc_path not in qrc_files:
                    qrc_files.append(qrc_path)

    if len(qrc_files) == 0:
        print('Did not find any *.qrc files in {}'.format(dirRoot), file=sys.stderr)
        return

    print('Compile {} *.qrc files:'.format(len(qrc_files)))
    for qrcFile in qrc_files:
        compileResourceFile(qrcFile, targetDir=targetDir, suffix=suffix)

    if len(qrc_files_skipped) > 0:
        print('Skipped *.qrc files (out of root directory):')
        for qrcFile in qrc_files_skipped:
            print(qrcFile.as_posix())

def compileResourceFile(pathQrc, targetDir=None, suffix:str='_rc.py', compressLevel=7, compressThreshold=100):
    """
    Compiles a *.qrc file
    :param pathQrc:
    :return:
    """
    if not isinstance(pathQrc, pathlib.Path):
        pathQrc = pathlib.Path(pathQrc)

    assert isinstance(pathQrc, pathlib.Path)
    assert pathQrc.name.endswith('.qrc')

    if targetDir is None:
        targetDir = pathQrc.parent
    elif not isinstance(targetDir, pathlib.Path):
        targetDir = pathlib.Path(targetDir)

    assert isinstance(targetDir, pathlib.Path)
    targetDir = targetDir.resolve()


    cwd = pathlib.Path(pathQrc).parent

    pathPy = targetDir / (os.path.splitext(pathQrc.name)[0] + suffix)

    last_cwd = os.getcwd()
    os.chdir(cwd)

    cmd = 'pyrcc5 -compress {} -o {} {}'.format(compressLevel, pathPy, pathQrc)
    cmd2 = 'pyrcc5 -no-compress -o {} {}'.format(pathPy.as_posix(), pathQrc.name)
    #print(cmd)

    if True:
        last_level = PyQt5.pyrcc_main.compressLevel
        last_threshold = PyQt5.pyrcc_main.compressThreshold

        # increase compression level and move to *.qrc's directory
        PyQt5.pyrcc_main.compressLevel = compressLevel
        PyQt5.pyrcc_main.compressThreshold = compressThreshold

        assert PyQt5.pyrcc_main.processResourceFile([pathQrc.name], pathPy.as_posix(), False)

        # restore previous settings
        PyQt5.pyrcc_main.compressLevel = last_level
        PyQt5.pyrcc_main.compressThreshold = last_threshold
    else:
        print(cmd2)
        os.system(cmd2)

    os.chdir(last_cwd)


def fileNeedsUpdate(file1, file2):
    """
    Returns True if file2 does not exist or is older than file1
    :param file1:
    :param file2:
    :return:
    """
    if not os.path.exists(file2):
        return True
    else:
        if not os.path.exists(file1):
            return True
        else:
            return os.path.getmtime(file1) > os.path.getmtime(file2)


def compileQGISResourceFiles(qgis_repo:str, target:str=None):
    """
    Searches for *qrc file in QGIS repository, compile them into <DIR_REPO>/qgisresources
    :param qgis_repo: str, path to local QGIS repository
    :param target: str, path to directory that contains the compiled QGIS resources. By default it will be
            `<REPOSITORY_ROOT>/qgisresources`
    """
    if not isinstance(qgis_repo, pathlib.Path):
        qgis_repo = pathlib.Path(qgis_repo)
    assert isinstance(qgis_repo, pathlib.Path)
    assert qgis_repo.is_dir()
    assert (qgis_repo / 'images' /'images.qrc').is_file(), '{} is not the QGIS repository root'.format(qgis_repo.as_posix())

    if target is None:
        target = DIR_REPO / 'qgisresources'

    if not isinstance(target, pathlib.Path):
        target = pathlib.Path(target)

    os.makedirs(target, exist_ok=True)
    compileResourceFiles(qgis_repo, targetDir=target)

