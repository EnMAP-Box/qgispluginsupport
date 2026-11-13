import datetime
import json
import sys
import warnings
from json import JSONDecodeError
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from processing.tools.dataobjects import createContext
from qgis.PyQt.QtCore import pyqtSignal, Qt, QTimer, QMetaType
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (
    QCheckBox, QDialog, QGridLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
    QVBoxLayout, QWidget)
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.core import (
    Qgis, QgsApplication, QgsCoordinateTransformContext, QgsEditorWidgetSetup, QgsFeature, QgsField,
    QgsMapLayer, QgsPalettedRasterRenderer, QgsProcessingAlgorithm,
    QgsProcessingContext, QgsProcessingFeedback, QgsProcessingModelAlgorithm, QgsProcessingOutputDefinition,
    QgsProcessingOutputRasterLayer, QgsProcessingOutputVectorLayer,
    QgsProcessingParameterMultipleLayers, QgsProcessingParameterRasterDestination,
    QgsProcessingParameterRasterLayer, QgsProcessingRegistry, QgsProcessingUtils, QgsProject, QgsRasterBlockFeedback,
    QgsRasterDataProvider, QgsRasterFileWriter, QgsRasterLayer, QgsRasterPipe, QgsVectorLayer)
from qgis.core import QgsProcessingException
from qgis.gui import (
    QgsAbstractProcessingParameterWidgetWrapper, QgsMessageBar, QgsPanelWidget,
    QgsProcessingAlgorithmWidgetBase, QgsProcessingParametersGenerator, QgsProcessingParameterWidgetContext)

from .spectralprocessingalgorithmmodel import SpectralProcessingAlgorithmModel
from .spectralprocessingparameterswidget import SpectralProcessingParametersWidget
from .spectralprocessingrasterdestination import SpectralProcessingRasterDestination
from .. import EDITOR_WIDGET_REGISTRY_KEY, speclibSettings
from ..core import can_store_spectral_profiles, is_profile_field
from ..core.spectrallibrary import SpectralLibraryUtils
from ..core.spectrallibraryrasterdataprovider import (
    VectorLayerFieldRasterDataProvider
)
from ..core.spectralprofile import (
    encodeProfileValueDict, prepareProfileValueDict, ProfileEncoding
)
from ...qgsrasterlayerproperties import QgsRasterLayerSpectralProperties
from ...reimplementation.processingalgorithmdialog import ProcessingAlgorithmDialog
from ...utils import qgsRasterLayer, rasterArray, createQgsField


def has_raster_input(alg: QgsProcessingAlgorithm) -> bool:
    if not isinstance(alg, QgsProcessingAlgorithm):
        return False
    for input in alg.parameterDefinitions():
        if isinstance(input, QgsProcessingParameterRasterLayer):
            return True
    return False


def has_raster_output(alg: QgsProcessingAlgorithm) -> bool:
    if not isinstance(alg, QgsProcessingAlgorithm):
        return False

    for output in alg.outputDefinitions():
        if isinstance(output, QgsProcessingOutputRasterLayer):
            return True
    return False


def has_raster_io(alg: QgsProcessingAlgorithm) -> bool:
    return has_raster_input(alg) and has_raster_output(alg)


def _deprecated_warning(cls_name: str, msg: str = ""):
    warnings.warn(
        f"{cls_name} is deprecated.{(' ' + msg) if msg else ''}",
        DeprecationWarning,
        stacklevel=2,
    )


class SpectralProcessingWidget(QgsProcessingAlgorithmWidgetBase):
    """
    .. deprecated:: Use :class:`SpectralProcessingAlgorithmWidget` instead.
    """
    sigSpectralProcessingModelChanged = pyqtSignal()
    sigAboutToBeClosed = pyqtSignal()

    sigOutputsCreated = pyqtSignal(dict)

    def __init__(self, *args,
                 speclib: Optional[QgsVectorLayer] = None,
                 algorithmId: Optional[str] = None,
                 parameters: Optional[dict] = None,
                 parent: Optional[QWidget] = None,
                 **kwds):
        _deprecated_warning("SpectralProcessingWidget", "Use SpectralProcessingAlgorithmWidget instead.")
        if parent is None:
            parent = QMainWindow()
        super().__init__(parentWindow=parent)
        self._parent = parent
        self.setWindowFlag(Qt.WindowType.WindowContextHelpButtonHint, False)
        # QgsProcessingContextGenerator.__init__(self)
        self.mWidgetName = 'Spectral Processing Widget'
        self.setWindowTitle(self.mWidgetName)
        self.setWindowIcon(QIcon(r':/qps/ui/icons/profile_processing.svg'))
        self.btnAlgorithm: QPushButton = QPushButton('Algorithm')
        self.btnAlgorithm.setIcon(QIcon(':/images/themes/default/processingAlgorithm.svg'))
        self.btnAlgorithm.clicked.connect(self.onSetAlgorithm)

        self.mTemporaryRaster: List[str] = []
        self.tbAlgorithmName: QLineEdit = QLineEdit()
        self.tbAlgorithmName.setPlaceholderText('Select a raster processing algorithm / model')
        self.tbAlgorithmName.setReadOnly(True)
        self.tbAlgorithmName.setAutoFillBackground(True)
        self.tbAlgorithmName.setSizePolicy(QSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred))

        self.cbSelectedFeaturesOnly = QCheckBox('Only process selected features')

        self.mTopGrid = QGridLayout()
        self.mTopGrid.addWidget(self.btnAlgorithm, 0, 0)
        self.mTopGrid.addWidget(self.tbAlgorithmName, 0, 1)
        self.mTopGrid.addWidget(self.cbSelectedFeaturesOnly, 1, 0, 1, 2)

        # self.btnAlgorithm.clicked.connect(self.actionSetAlgorithm.trigger)
        self.layout().insertLayout(0, self.mTopGrid)
        self.mProcessingAlgorithmModel: SpectralProcessingAlgorithmModel = SpectralProcessingAlgorithmModel(self)

        self.mSpeclib: Optional[QgsVectorLayer] = None
        self.mAlg: Optional[QgsProcessingAlgorithm] = None
        self.mPanelWidget: Optional[SpectralProcessingParametersWidget] = None
        self.mProcessingFeedback: QgsProcessingFeedback = QgsProcessingFeedback()
        self.mProcessingContext: QgsProcessingContext = createContext(self.mProcessingFeedback)
        self.mProcessingContext.setTransformContext(QgsProject.instance().transformContext())
        self.mProcessingFeedback.progressChanged.connect(self.setPercentage)
        self.mProcessingWidgetContext: QgsProcessingParameterWidgetContext = QgsProcessingParameterWidgetContext()

        self.mProcessingAlgParametersStore: dict = dict()

        # self.mProcessingModelWrapper: SpectralProcessingModelCreatorAlgorithmWrapper = None

        self.mTestProfile = QgsFeature()
        self.mCurrentFunction: Optional[QgsProcessingAlgorithm] = None

        self.updateGui()

        if isinstance(speclib, QgsVectorLayer):
            self.setSpeclib(speclib)

            # load default values from last start
            settings = speclibSettings()
            K = self.__class__.__name__
            if algorithmId is None:
                algorithmId = settings.value(f'{K}/algorithmId', None)

            if algorithmId:
                alg: QgsProcessingAlgorithm = QgsApplication.processingRegistry().algorithmById(algorithmId)
                if isinstance(alg, QgsProcessingAlgorithm):
                    self.setAlgorithm(alg)
                    context = self.processingContext()

                    if not isinstance(parameters, dict):
                        try:
                            parJson = settings.value(f'{K}/algorithmParameters', '')
                            parameters = json.loads(parJson)
                        except (JSONDecodeError, Exception):
                            parameters = None

                    if isinstance(parameters, dict):
                        wrapper = self.processingModelWrapper()
                        for k, value in parameters.items():
                            w = wrapper.mWrappers.get(k)
                            if isinstance(w, QgsAbstractProcessingParameterWidgetWrapper):
                                w.setWidgetValue(value, context)

    @staticmethod
    def resetSettings():
        """
        Resets all settings which may have been derived from QSettings
        """
        settings = speclibSettings()
        K = SpectralProcessingWidget.__name__
        settings.setValue(f'{K}/algorithmId', None)
        settings.value(f'{K}/algorithmParameters', None)

    def close(self):

        # save settings

        settings = speclibSettings()
        K = self.__class__.__name__
        alg = self.algorithm()
        if isinstance(alg, QgsProcessingAlgorithm):
            settings.setValue(f'{K}/algorithmId', self.algorithm().id())
            try:
                parameters = self.processingModelWrapper().createProcessingParameters()
                parameters2 = dict()
                for k, v in parameters.items():
                    if isinstance(v, QgsMapLayer):
                        v = v.name()
                    if isinstance(v, (str, int, float, list)):
                        parameters2[k] = v
                settings.setValue(f'{K}/algorithmParameters', json.dumps(parameters2, ensure_ascii=False))
            except Exception as ex:
                print(f'Unable to save last settings: {ex}', file=sys.stderr)

        self.sigAboutToBeClosed.emit()
        super().close()

    def setMainMessageBar(self, messageBar):
        self.mProcessingWidgetContext.setMessageBar(messageBar)

    def onSetAlgorithm(self):

        d = ProcessingAlgorithmDialog(self)
        d.setAlgorithmModel(self.mProcessingAlgorithmModel)

        if d.exec() == QDialog.DialogCode.Accepted:
            alg = d.algorithm()
            if isinstance(alg, QgsProcessingAlgorithm):
                self.setAlgorithm(alg)

    def processingAlgorithm(self) -> QgsProcessingAlgorithm:
        return self.algorithm()

    def processingContext(self) -> QgsProcessingContext:
        return self.mProcessingContext

    def processingParameterWidgetContext(self) -> QgsProcessingParameterWidgetContext:
        return self.mProcessingWidgetContext

    def processingFeedback(self) -> QgsProcessingFeedback:
        return self.mProcessingFeedback

    def runAlgorithm(self, fail_fast: bool = False) -> None:
        """
        Runs the QgsProcessingAlgorithm with the specified settings
        """

        self.mTemporaryRaster.clear()

        TEMP_FOLDER = QgsProcessingUtils.generateTempFilename('')
        processingContext: QgsProcessingContext = self.processingContext()
        # LAST_TEMP_FOLDER = processingContext.temporaryFolder()
        self.mProcessingFeedback.setProgress(int(0))
        wrapper = self.processingModelWrapper()
        if not isinstance(wrapper, SpectralProcessingParametersWidget):
            return None

        speclib: QgsVectorLayer = self.speclib()
        if not speclib.isEditable():
            self.log(f'Spectral Library "{speclib.name()}" is not editable', isError=True)
            self.showLog()
            return None

        alg: QgsProcessingAlgorithm = wrapper.algorithm()
        parameters = None
        try:
            rasterblockFeedback = QgsRasterBlockFeedback()

            processingContext.setTemporaryFolder(TEMP_FOLDER)
            processingFeedback: QgsProcessingFeedback = processingContext.feedback()
            # todo: set more context variables
            # processingContext.setFeedback(processingFeedback)

            parameters: Dict[str, Any] = wrapper.createProcessingParameters()
            # self.tabWidget.setCurrentWidget(self.tabLog)

            # save parameters
            self.log(f'Save parameters for {alg.id()}')
            self.mProcessingAlgParametersStore[alg.id()] = parameters

            transformContext = processingContext.transformContext()
            # copy and replace input raster's with temporary data sets
            # that contain spectral profiles

            # Calculate feature intersection, i.e.
            self.log('Calculate feature intersection')

            affected_features = set()
            n_raster_inputs = 0
            if self.selectedFeaturesOnly():
                affected_features.update(speclib.selectedFeatureIds())

            # collect vector field raster layers
            vectorfieldrasterlayers: Dict[str, QgsRasterLayer] = {}
            required_layers = {}

            def add_vectorfieldrasterlayer(lyr, paramter_key: str):
                if (
                    isinstance(lyr, QgsRasterLayer)
                    and isinstance(lyr.dataProvider(), VectorLayerFieldRasterDataProvider)  # noqa: W503
                ):
                    vectorfieldrasterlayers[lyr.id()] = (lyr, paramter_key)

            for k, v in parameters.items():
                k: str
                param = alg.parameterDefinition(k)
                if isinstance(param, QgsProcessingParameterMultipleLayers):
                    for layer_id in v:
                        lyr = processingContext.getMapLayer(layer_id)
                        if isinstance(lyr, QgsMapLayer):
                            required_layers[layer_id] = lyr
                        add_vectorfieldrasterlayer(processingContext.getMapLayer(layer_id), k)
                elif isinstance(param, QgsProcessingParameterRasterLayer):
                    add_vectorfieldrasterlayer(v, k)

            n_raster_inputs = len(vectorfieldrasterlayers)
            for (lyr, k) in vectorfieldrasterlayers.values():

                dp: VectorLayerFieldRasterDataProvider = lyr.dataProvider()
                fids = dp.activeFeatureIds()
                if len(affected_features) == 0:
                    affected_features.update(fids)
                else:
                    affected_features.intersection_update(fids)

            if n_raster_inputs > 0 and len(affected_features) == 0:
                self.log('Feature ID of selected spectral profile images do not overlap', isError=True)
                return None

            activeFeatures = list(self.speclib().getFeatures(sorted(affected_features)))
            activeFeatureIDs = [f.id() for f in activeFeatures]

            if len(activeFeatureIDs) == 0:
                self.log('No active features to process', isError=True)
                # return None
            else:
                self.log(f'Process {len(affected_features)} features')

            parametersHard = parameters.copy()
            self.log('Make virtual raster(s) permanent')

            # vectorfieldrasterlayers_new_ids = {}
            for lid, (lyr, k) in vectorfieldrasterlayers.items():
                dp: VectorLayerFieldRasterDataProvider = lyr.dataProvider().clone()
                dp.setActiveFeatures(activeFeatures, dp.activeField())
                file_name = QgsProcessingUtils.generateTempFilename(f'{k}.tif', processingContext)
                self.writeTemporaryRaster(dp, file_name, rasterblockFeedback, transformContext)
                lyr.setDataSource(file_name, '', 'gdal')

            self.log('Define output raster locations')
            for k, v in parametersHard.items():
                param = alg.parameterDefinition(k)

                if isinstance(param, QgsProcessingParameterRasterDestination):
                    file_name = QgsProcessingUtils.generateTempFilename(v, processingContext)
                    parametersHard[k] = file_name

            from processing.gui.AlgorithmExecutor import execute as executeAlg

            self.log(f'Execute algorithm: {alg.id()} ...')
            processingFeedback.pushInfo('Input parameters:')
            processingFeedback.pushConsoleInfo(str(parametersHard))
            t0 = datetime.datetime.now()
            ok, results = executeAlg(alg,
                                     parametersHard,
                                     context=processingContext,
                                     feedback=processingFeedback,
                                     catch_exceptions=not fail_fast)

            if ok:

                OUTPUTS: Dict[str, Tuple[QgsProcessingOutputDefinition, Any]] = dict()
                OUT_RASTERS = dict()
                for parameter in alg.outputDefinitions():
                    parameter: QgsProcessingOutputDefinition
                    if parameter.name() not in results.keys():
                        processingFeedback.pushWarning(f'Missing result value for parameter "{parameter.name()}"')
                        continue

                    result_value = results[parameter.name()]
                    OUTPUTS[parameter.name()] = (parameter, result_value)

                    if isinstance(parameter, QgsProcessingOutputRasterLayer):
                        # try 1:
                        if isinstance(result_value, QgsRasterLayer):
                            lyr = result_value
                        else:
                            lyr = processingContext.getMapLayer(result_value)

                        if lyr is None:
                            lyr = processingContext.temporaryLayerStore().mapLayer(result_value)
                        if lyr is None:
                            lyr = QgsRasterLayer(result_value)

                        if not isinstance(lyr, QgsRasterLayer):
                            info = f'{parameter.name()} : {result_value}'
                            self.log(info, isError=True)
                            continue

                        if not lyr.isValid():
                            info = f'{parameter.name()} : {lyr.error().message()}'
                            self.log(info, isError=True)
                            continue

                        tmp = rasterArray(lyr)
                        nb, nl, ns = tmp.shape

                        target_field_name = lyr.name()
                        if target_field_name == '':
                            target_field_name = SpectralProcessingRasterDestination.pathToFieldName(lyr.source())

                        target_field_index = speclib.fields().lookupField(target_field_name)
                        if target_field_index == -1:
                            # create a new field

                            if nb > 1:
                                # create spectral profile fields
                                field: QgsField = SpectralLibraryUtils.createProfileField(target_field_name)
                                if not speclib.dataProvider().supportedType(field):
                                    field = SpectralLibraryUtils.createProfileField(target_field_name,
                                                                                    encoding=ProfileEncoding.Text)
                            else:
                                # create standard field
                                field = createQgsField(target_field_name, tmp[0, 0, 0])
                                # field: QgsField = QgsField(name=target_field_name,
                                #                            type=numpyToQgisDataType(tmp.dtype))
                                if not speclib.dataProvider().supportedType(field):
                                    field = QgsField(
                                        name=target_field_name,
                                        type=QMetaType.Type.Double
                                    )

                            speclib.beginEditCommand(f'Add field {field.name()}')
                            if not (SpectralLibraryUtils.addAttribute(speclib, field)):
                                raise AssertionError
                            speclib.endEditCommand()

                            target_field_index = speclib.fields().lookupField(target_field_name)

                        if target_field_index >= 0:
                            # if necessary, change editor widget type to SpectralProfile
                            target_field: QgsField = speclib.fields().at(target_field_index)
                            if (
                                nb > 0 and can_store_spectral_profiles(target_field)
                                and not is_profile_field(target_field)  # noqa: W503
                            ):
                                setup = QgsEditorWidgetSetup(EDITOR_WIDGET_REGISTRY_KEY, {})
                                speclib.setEditorWidgetSetup(target_field_index, setup)
                                target_field = speclib.fields().at(target_field_index)

                            OUT_RASTERS[parameter.name()] = (lyr, tmp, target_field)

                    elif isinstance(parameter, QgsProcessingOutputVectorLayer):
                        # todo: append vector output to speclib
                        pass

                if len(OUT_RASTERS) > 0:
                    # available_fids = speclib.allFeatureIds()
                    speclib.beginEditCommand('Add raster processing results')
                    # reload active features to include new fields
                    activeFeatures = list(speclib.getFeatures(activeFeatureIDs))
                    # write raster values to features
                    for parameterName, (lyr, tmp, target_field) in OUT_RASTERS.items():
                        self.log(f'Write values to field {target_field.name()}...')

                        spectralProperties = QgsRasterLayerSpectralProperties.fromRasterLayer(lyr)
                        wl = spectralProperties.wavelengths()
                        wlu = spectralProperties.wavelengthUnits()
                        bbl = spectralProperties.badBands(default=1)

                        # wavelength needs to be defined for all bands
                        if any([w is None for w in wl]):
                            wl = None

                        # choose the 1st wavelength unit for the entire profile
                        for w in wlu:
                            if w not in [None, '']:
                                wlu = w

                        # no need to save a bad-band-list (bbl) if it is True for all bands (default)
                        if all([b == 1 for b in bbl]):
                            bbl = None

                        target_field: QgsField
                        target_field_index: int = speclib.fields().lookupField(target_field.name())

                        is_profile = is_profile_field(target_field)
                        for i, feature in enumerate(activeFeatures):
                            feature: QgsFeature
                            value = None
                            if is_profile:
                                pixel_profile = tmp[:, 0, i]
                                pdict = prepareProfileValueDict(
                                    x=wl, xUnit=wlu, y=pixel_profile, bbl=bbl
                                )
                                value = encodeProfileValueDict(pdict, target_field)
                            else:
                                value = float(tmp[0, 0, i])
                                if target_field.type() == QMetaType.Type.QString:
                                    value = str(value)
                            if not (speclib.changeAttributeValue(feature.id(), target_field_index, value)):
                                raise AssertionError
                            # assert feature.setAttribute(target_field_index, value)

                    self.log(f'Update {len(activeFeatures)} features')
                    speclib.endEditCommand()

                if len(OUTPUTS) > 0:
                    self.sigOutputsCreated.emit(OUTPUTS)

            processingFeedback.pushInfo(f'Execution completed in {datetime.datetime.now() - t0}')
            processingFeedback.pushInfo('Results:')
            processingFeedback.pushConsoleInfo(str(results))
            self.log(processingFeedback.htmlLog(), isError=not ok)

        except QgsProcessingException as ex1:
            if fail_fast:
                raise ex1
            msg = f'{ex1}'
            self.log(msg, isError=True, escapeHtml=False)
            # self.tabWidget.setCurrentWidget(self.tabLog)
            # self.highlightParameterWidget(ex1.parameter, ex1.widget)

        except Exception as ex3:
            if fail_fast:
                raise ex3
            msg = f'{ex3}'
            self.log(msg, isError=True, escapeHtml=False)
            mbar: QgsMessageBar = self.messageBar()
            if isinstance(mbar, QgsMessageBar):
                mbar.pushMessage(msg, level=Qgis.MessageLevel.Critical)

        self.log('Done')
        self.setPercentage(0)
        self.showLog()
        # self.processingFeedback().setProgress(int(100))

    def temporaryRaster(self) -> List[str]:
        """
        Returns a list of all files which have been written by writeTemporaryRaster
        when calling runAlgorithm()
        """
        return self.mTemporaryRaster[:]

    def writeTemporaryRaster(
        self,
        dp: QgsRasterDataProvider,
        file_name: str,
        rasterblockFeedback: QgsRasterBlockFeedback,
        transformContext: QgsCoordinateTransformContext,
        layer_name: Optional[str] = None,
    ):
        """
        Writes a temporary raster file from a QgsRasterDataProvider.
        file_name: str a string with the temporary raster file name
        """
        file_writer = QgsRasterFileWriter(file_name)

        if not (dp.xSize() > 0):
            raise AssertionError
        if not (dp.ySize() > 0):
            raise AssertionError
        if not (dp.bandCount() > 0):
            raise AssertionError

        pipe = QgsRasterPipe()
        if not pipe.set(dp):
            self.log(f'Cannot set pipe provider to write {file_name}', isError=True)
        else:
            self.log(f'Write {file_name}')
        error = file_writer.writeRaster(
            pipe,
            dp.xSize(),
            dp.ySize(),
            dp.extent(),
            dp.crs(),
            transformContext,
            rasterblockFeedback
        )

        del file_writer
        if error != QgsRasterFileWriter.WriterError.NoError:
            from ..core.spectrallibraryrasterdataprovider import LUT_RASTERFILEWRITER_ERRORS
            errMsg = LUT_RASTERFILEWRITER_ERRORS.get(error, 'unknown')
            raise Exception(f'Unable to write {file_name}\n'
                            f'QgsRasterFileWriterError: {errMsg}')

        layer: QgsRasterLayer = qgsRasterLayer(file_name)
        if layer_name is not None:
            layer.setName(layer_name)

        # write additional metadata
        if isinstance(dp, VectorLayerFieldRasterDataProvider):

            if dp.bandCount() > 1:
                spectral_settings = dp.rasterMetaData().copy()
                props = QgsRasterLayerSpectralProperties.fromMap(spectral_settings)
                props.writeToSource(layer, write_envi=True)

            # write a classification
            else:
                colorTable = dp.colorTable(1)
                if len(colorTable) > 0:
                    # set a categorical raster renderer with class names and colors
                    classData = QgsPalettedRasterRenderer.colorTableToClassData(colorTable)
                    renderer = QgsPalettedRasterRenderer(layer.dataProvider(), 1, classData)
                    layer.setRenderer(renderer)
                    layer.saveDefaultStyle(QgsMapLayer.StyleCategory.AllStyleCategories)

        del layer

        self.mTemporaryRaster.append(file_name)

    def messageBar(self) -> QgsMessageBar:
        return self.mProcessingWidgetContext.messageBar()

    def log(
        self,
        text: str,
        showLogPanel: bool = False,
        isError: bool = False,
        escapeHtml: bool = False
    ):
        self.setInfo(text, isError=isError, escapeHtml=escapeHtml)
        if isError or showLogPanel:
            self.showLog()

    def highlightParameterWidget(self, parameter, widget):
        self.showParameters()

        wrapper: SpectralProcessingParametersWidget = self.processingModelWrapper()
        if isinstance(wrapper, SpectralProcessingParametersWidget):
            css = widget.styleSheet()
            widget.setStyleSheet('background-color: rgba(255, 0, 0, 150);')
            QTimer.singleShot(1000, lambda *args, w=widget, c=css: w.setStyleSheet(c))

    def createProcessingParameters(self, flags=None):
        if flags is None and Qgis.versionInt() >= 32400:
            flags = QgsProcessingParametersGenerator.Flags()

        if self.mainWidget() is None:
            return {}
        try:
            return self.mainWidget().createProcessingParameters(flags)
        except QgsProcessingException as ex:
            print(ex, sys.stderr)
        # except InvalidParameterValue as e:
        #     self.flag_invalid_parameter_value(e.parameter.description(), e.widget)
        # except InvalidOutputExtension as e:
        #    self.flag_invalid_output_extension(e.message, e.widget)
        return {}

    def setAlgorithm(self, alg: Union[str, Path, QgsProcessingAlgorithm]):

        if isinstance(alg, str):
            reg: QgsProcessingRegistry = QgsApplication.instance().processingRegistry()
            a = reg.algorithmById(alg)
            if isinstance(a, QgsProcessingAlgorithm):
                alg = a
            else:
                alg = Path(alg)

        if isinstance(alg, Path):
            if not (alg.is_file()):
                raise AssertionError(f'Not a model file: {alg}')
            m = QgsProcessingModelAlgorithm()
            m.fromFile(alg.as_posix())
            alg = m

        if not (isinstance(alg, QgsProcessingAlgorithm)):
            raise AssertionError

        super().setAlgorithm(alg.create())
        self.mAlg = alg
        w = self.getParametersPanel(alg, self)
        # mw = self.mainWidget()
        # if isinstance(mw, QWidget):
        #    mw.setParent(None)
        if isinstance(w, QgsPanelWidget):
            self.setMainWidget(w)
        # self.mProcessingModelWrapper = w
        self.mPanelWidget = w
        self.updateGui()

    def getParametersPanel(
        self,
        alg: QgsProcessingAlgorithm,
        parent: QWidget
    ) -> SpectralProcessingParametersWidget:
        if isinstance(self.mSpeclib, QgsVectorLayer):
            panel = SpectralProcessingParametersWidget(
                alg,
                self.mSpeclib,
                processingContext=self.mProcessingContext,
                parent=self
            )
        else:
            panel = QgsPanelWidget()
            if not panel.layout():
                panel.setLayout(QVBoxLayout())
            panel.layout().addWidget(QLabel('Missing spectral library'))
        return panel

    def processingModelWrapper(self) -> SpectralProcessingParametersWidget:
        # return self.mProcessingModelWrapper
        return self.mPanelWidget

    def selectedFeaturesOnly(self) -> bool:
        return self.cbSelectedFeaturesOnly.isEnabled() and self.cbSelectedFeaturesOnly.isChecked()

    def setSpeclib(self, speclib: QgsVectorLayer):
        if isinstance(self.mSpeclib, QgsVectorLayer):
            self.mSpeclib.willBeDeleted.disconnect(self.close)

        if not (isinstance(speclib, QgsVectorLayer)):
            raise AssertionError
        self.mSpeclib = speclib
        self.mSpeclib.willBeDeleted.connect(self.close)

        self.setWindowTitle(f'{self.mWidgetName} - {speclib.name()}')

    def updateGui(self):

        sl = self.speclib()
        if isinstance(sl, QgsVectorLayer):
            n = sl.selectedFeatureCount()
            self.cbSelectedFeaturesOnly.setEnabled(n > 0)
            self.cbSelectedFeaturesOnly.setText(f'Only process {n} selected features')

        self.tbAlgorithmName: QLineEdit

        alg: QgsProcessingAlgorithm = self.algorithm()
        hasAlg = isinstance(alg, QgsProcessingAlgorithm)
        if hasAlg:
            self.tbAlgorithmName.setStyleSheet('')
            css = ''
            # info = f'<b>{alg.displayName()}</b> "{alg.id()}"'
            info = f'{alg.displayName()} "{alg.id()}"'
            tooltip = f'Algorithm Name: {alg.name()}<br>Algorithm ID: {alg.id()}'
        else:
            css = 'color:"red";'
            info = tooltip = self.tbAlgorithmName.placeholderText()
        self.tbAlgorithmName.setStyleSheet(css)
        self.tbAlgorithmName.setText(info)
        self.tbAlgorithmName.setToolTip(tooltip)
        self.setWindowTitle(self.mWidgetName)

    def speclib(self) -> QgsVectorLayer:
        return self.mSpeclib
