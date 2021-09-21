# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/processingalgorithms.py
    This module contains QgsProcessingAlgorithms which allow for
    SpectralLibraries processing within the QGIS Processing Framework.
    ---------------------
    Date                 : Jan 2021
    Copyright            : (C) 2021 by Benjamin Jakimow
    Email                : benjamin.jakimow@geo.hu-berlin.de
***************************************************************************
    This program is free software; you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation; either version 3 of the License, or
    (at your option) any later version.
                                                                                                                                                 *
    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this software. If not, see <http://www.gnu.org/licenses/>.
***************************************************************************
"""
import typing

import numpy as np
from PyQt5.QtCore import QVariant
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout
from qgis.core import QgsField, QgsProcessingOutputVectorLayer, QgsFeatureRequest, QgsProcessingAlgorithm, \
    QgsProcessingParameterString, QgsProcessingContext, QgsProcessingFeedback

from qgis.core import \
    QgsProcessingAlgorithm, QgsProcessingParameterVectorLayer, \
    QgsProcessingContext, QgsProcessingFeedback, QgsProcessingParameterField, QgsProcessingParameterEnum, \
    QgsVectorLayer, QgsProcessingParameterVectorDestination, \
    QgsFeature

from qgis.PyQt.QtGui import QIcon
from .core import field_index, profile_field_list, create_profile_field

from .core.spectrallibrary import SpectralSetting, SpectralProfileBlock, read_profiles, \
    SpectralLibrary, FIELD_VALUES
from .core.spectralprofile import SpectralProfileBlock
from .processing import \
    SpectralProcessingProfiles, SpectralProcessingProfilesOutput, \
    SpectralProcessingProfilesSink, parameterAsSpectralProfileBlockList

from ..unitmodel import UnitConverterFunctionModel, XUnitModel


class _AbstractSpectralAlgorithm(QgsProcessingAlgorithm):

    def __init__(self):
        super(_AbstractSpectralAlgorithm, self).__init__()
        self.mGroup: str = 'qps'
        self.mIcon: QIcon = QIcon(':/qps/ui/icons/profile.svg')

    def group(self) -> str:
        return self.mGroup

    def icon(self) -> QIcon:
        return self.mIcon

    def createInstance(self):
        alg = self.__class__()
        return alg

    def canExecute(self) -> bool:
        result: bool = True
        msg = ''
        return result, msg

    def flags(self):
        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading


class SpectralXUnitConversion(_AbstractSpectralAlgorithm):
    INPUT = 'input_profiles'
    TARGET_XUNIT = 'target_unit'
    OUTPUT = 'output_profiles'

    def __init__(self):
        super().__init__()
        self.mUnitConverterFunctionModel = UnitConverterFunctionModel()
        self.mUnitModel = XUnitModel()
        self.mParameters = []

    def name(self):
        return 'spectral_xunit_converter'

    def displayName(self) -> str:
        return 'Convert wavelength units'

    def initAlgorithm(self, configuration):

        p1 = SpectralProcessingProfiles(self.INPUT)
        p2 = QgsProcessingParameterEnum(self.TARGET_XUNIT,
                                        description='Target x/wavelength unit',
                                        options=[u for u in self.mUnitModel.mUnits],
                                        defaultValue=1,
                                        )
        p3 = SpectralProcessingProfilesSink(self.OUTPUT)
        # o1 = SpectralProcessingProfilesOutput(self.OUTPUT)
        self.addParameter(p1)
        self.addParameter(p2)
        self.addParameter(p3, createOutput=True)
        # self.addOutput(o1)
        # self.mParameters.extend([p1, p2, o1])

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        for key in [self.INPUT, self.TARGET_XUNIT]:
            if not key in parameters.keys():
                feedback.reportError(f'Missing parameter {key}')
                return False

        return True

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        targetUnit = parameters.get(self.TARGET_XUNIT)
        if isinstance(targetUnit, int):
            targetUnit = self.mUnitModel.mUnits[targetUnit]

        assert targetUnit in self.mUnitModel.mUnits

        input_profiles = parameterAsSpectralProfileBlockList(parameters, self.INPUT, context)
        output_profiles: typing.List[SpectralProcessingProfilesOutput] = []
        n_blocks = len(input_profiles)
        for i, profileBlock in enumerate(input_profiles):
            # process block by block

            assert isinstance(profileBlock, SpectralProfileBlock)
            # print(profileBlock)
            feedback.pushConsoleInfo(f'Process profile block {i + 1}/{n_blocks}')
            spectralSetting = profileBlock.spectralSetting()
            if spectralSetting.xUnit() == targetUnit:
                # output unit is already correct
                output_profiles.append(profileBlock)
            else:
                f = self.mUnitConverterFunctionModel.convertFunction(spectralSetting.xUnit(), targetUnit)
                if callable(f):
                    xValuesNew = f(profileBlock.xValues())
                    if xValuesNew is None:
                        feedback.reportError(f'Unable to convert x-unit of {profileBlock.n_profiles()} profile(s) '
                                             f'from "{spectralSetting.xUnit()}" to "{targetUnit}"')
                    else:
                        settingOut = SpectralSetting(xValuesNew,
                                                     xUnit=targetUnit,
                                                     yUnit=spectralSetting.yUnit(),
                                                     )
                        blockOut = SpectralProfileBlock(profileBlock.data(),
                                                        spectralSetting=settingOut,
                                                        fids=profileBlock.fids(),
                                                        metadata=profileBlock.metadata())
                        output_profiles.append(blockOut)
                else:
                    feedback.pushConsoleInfo(f'Unable to convert {profileBlock.n_profiles()} profiles '
                                             f'with {spectralSetting} to {targetUnit}')

        OUTPUTS = {self.OUTPUT: output_profiles}
        return OUTPUTS


class SpectralProfileReader(_AbstractSpectralAlgorithm):
    """
    Reads spectral profile block from SpectralLibraries / Vectorlayers with BLOB columns
    """
    INPUT = 'INPUT'
    INPUT_FIELD = 'INPUT_FIELD'
    OUTPUT = 'OUTPUT'

    def __init__(self):
        super().__init__()
        self.mParameters = []

    def shortDescription(self) -> str:
        return 'Reads spectral profiles'

    def initAlgorithm(self, configuration: dict):
        from .core.spectrallibrary import FIELD_VALUES
        self.addParameter(QgsProcessingParameterVectorLayer(self.INPUT, 'Spectral Library'))

        self.addParameter(QgsProcessingParameterField(self.INPUT_FIELD, 'Profile column',
                                                      defaultValue=None,
                                                      optional=True,
                                                      parentLayerParameterName=self.INPUT,
                                                      allowMultiple=False))

        self.addParameter(SpectralProcessingProfilesSink(self.OUTPUT, 'Spectral Profiles'), createOutput=True)
        # self.addOutput(SpectralProcessingProfilesOutput(self.OUTPUT, 'Spectral Profiles'))

    def checkParameterValues(self,
                             parameters: dict,
                             context: QgsProcessingContext,
                             ):
        result = True
        msg = ''
        # check parameters

        return result, msg

    def displayName(self) -> str:
        return 'Spectral Profile Reader'

    def helpString(self) -> str:
        return 'Spectral Profile Reader Help String'

    def name(self):
        return 'spectral_profile_reader'

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        for key in [self.INPUT]:
            if key not in parameters.keys():
                feedback.reportError(f'Missing parameter {key}')
                return False
        speclib: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        field: typing.List[str] = self.parameterAsFields(parameters, self.INPUT_FIELD, context)
        field = None if len(field) == 0 else field[0]
        if field and field_index(speclib, field) == -1:
            feedback.reportError(f'{self.INPUT}:{speclib.source()} does not contain field "{field}"')
            return False
        return True

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        speclib: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        field: typing.List[str] = self.parameterAsFields(parameters, self.INPUT_FIELD, context)
        field = None if len(field) == 0 else field[0]

        output_blocks: typing.List[SpectralProfileBlock] = \
            SpectralProfileBlock.fromSpectralLibrary(speclib,
                                                     profile_field=field,
                                                     feedback=feedback)

        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = list(output_blocks)
        return OUTPUTS


class SpectralProfileWriter(_AbstractSpectralAlgorithm):
    INPUT = 'INPUT'
    MODE = 'MODE'
    _MODES = ['Append', 'Match']
    OUTPUT = 'SPECLIB'
    OUTPUT_FIELD = 'PROFILE_FIELD'

    def __init__(self):
        super().__init__()
        self.mParameters = []
        self.mProfileFieldIndex = None

    def shortDescription(self) -> str:
        return 'Writes spectral profiles'

    def initAlgorithm(self, configuration: dict):
        p1 = SpectralProcessingProfiles(self.INPUT)
        p2 = QgsProcessingParameterVectorLayer(self.OUTPUT)
        p3 = QgsProcessingParameterField(self.OUTPUT_FIELD,
                                         defaultValue=FIELD_VALUES,
                                         optional=True,
                                         parentLayerParameterName=self.OUTPUT)
        p4 = QgsProcessingParameterEnum(self.MODE, options=self._MODES, defaultValue=1)
        self.addParameter(p1)
        self.addParameter(p2, createOutput=True)
        self.addParameter(p3)
        self.addParameter(p4)
        self.addOutput(QgsProcessingOutputVectorLayer(self.OUTPUT))

    def checkParameterValues(self,
                             parameters: dict,
                             context: QgsProcessingContext,
                             ):

        result, msg = super().checkParameterValues(parameters, context)

        return result, msg

    def displayName(self) -> str:
        return 'Spectral Profile Writer'

    def helpString(self) -> str:
        return 'Spectral Profile Writer Help String'

    def name(self):
        return 'spectral_profile_writer'

    def parameterAsMode(self, parameters: dict, context: QgsProcessingContext):
        mode = self.parameterAsEnum(parameters, self.MODE, context)
        return self._MODES[mode].upper()

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        for key in [self.INPUT, self.OUTPUT]:
            if key not in parameters.keys():
                feedback.reportError(f'Missing parameter {key}')
                return False

        speclib: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.OUTPUT, context)
        if isinstance(speclib, QgsVectorLayer):

            existing_profile_fields = profile_field_list(speclib)
            field: typing.List[str] = self.parameterAsFields(parameters, self.OUTPUT_FIELD, context)
            field = None if len(field) == 0 else field[0]

            if field is None:
                if len(existing_profile_fields) == 0:
                    # create new profile field
                    field = 'profiles'
                    i = 0
                    while field in speclib.fields().names():
                        i += 1
                        field = f'profiles_{i}'
                else:
                    field = existing_profile_fields[0].name()

            if field not in speclib.fields().names():
                # create new field
                is_editable = speclib.isEditable()
                assert speclib.startEditing()
                speclib.addAttribute(create_profile_field(field))
                if not speclib.commitChanges(stopEditing=not is_editable):
                    feedback.reportError(f'Unable to create new profile field {field}')
                    return False
                existing_profile_fields = profile_field_list(speclib)

            self.mProfileFieldIndex = speclib.fields().lookupField(field)
            for f in existing_profile_fields:
                if f.name() == field and not f.type() == QVariant.ByteArray:
                    feedback.reportError(f'Field {field} is not of type QVariant.ByteArray')
                    return False

        else:
            path = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)
            if path in ['', None]:
                feedback.reportError(f'{self.OUTPUT} is undefined')
                return False
        return True

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):


        input_profiles: typing.List[SpectralProfileBlock] = parameterAsSpectralProfileBlockList(parameters, self.INPUT, context)

        mode = self.parameterAsMode(parameters, context)

        field = self.parameterAsFields(parameters, self.OUTPUT_FIELD, context)[0]

        speclib: SpectralLibrary = self.parameterAsVectorLayer(parameters, self.OUTPUT, context)
        if not isinstance(speclib, SpectralLibrary):
            # create new speclib
            speclib = SpectralLibrary(profile_fields=[field])
            context.temporaryLayerStore().addMapLayer(speclib)
            s = ""
        assert isinstance(speclib, QgsVectorLayer)
        assert field in speclib.fields().names()
        i_field = speclib.fields().lookupField(field)
        existing_fids = speclib.allFeatureIds()

        editable: bool = speclib.isEditable()
        assert speclib.startEditing()
        speclib.beginEditCommand(f'Write profiles to {field}')

        for block in input_profiles:
            # process block by block
            fids = block.fids()
            new_features = []
            if fids and mode != 'APPEND':
                # block profiles with FIDs -> handle mode
                FEATURE_DATA = {fid : (ba, g) for fid, ba, g in block.profileValueByteArrays()}
                request = QgsFeatureRequest()
                request.setFilterFids(fids)
                for f in speclib.getFeatures(request):
                    ba, g = FEATURE_DATA.pop(f.id())
                    speclib.changeGeometry(f.id(), g)
                    speclib.changeAttributeValue(f.id(), i_field, ba)

                # append remaining byte arrays as new features
                for (ba, g) in FEATURE_DATA.values():
                    f = QgsFeature(speclib.fields())
                    f.setGeometry(g)
                    f.setAttribute(i_field, ba)
                    new_features.append(f)

            else:
                # block profiles without FID -> just append new features
                for (fid, b, g) in block.profileValueByteArrays():
                    f = QgsFeature(speclib.fields())
                    f.setGeometry(g)
                    f.setAttribute(i_field, ba)
                    new_features.append(f)

            # append new features / features without fid
            if len(new_features) > 0:
                assert speclib.addFeatures(new_features)

        speclib.endEditCommand()

        assert speclib.commitChanges(stopEditing=not editable)

        return {self.OUTPUT: speclib}


def createSpectralAlgorithms() -> typing.List[QgsProcessingAlgorithm]:
    """
    Returns the spectral processing algorithms defined in this module
    """
    return [
        SpectralProfileReader(),
        SpectralProfileWriter(),
        SpectralXUnitConversion(),
    ]


class SpectralPythonCodeProcessingAlgorithm(QgsProcessingAlgorithm):
    NAME = 'spectral_python_code_processing'
    INPUT = 'INPUT'
    CODE = 'CODE'
    OUTPUT = 'OUTPUT'

    def __init__(self):
        super().__init__()
        self.mParameters = []
        self.mFunction: typing.Callable = None

        self.mInputProfileBlock: typing.List[SpectralProfileBlock] = None

    def shortDescription(self) -> str:
        return 'This is a spectral processing algorithm'

    def initAlgorithm(self, configuration: dict):

        p1 = SpectralProcessingProfiles(self.INPUT, description='Input Profiles')
        self.addParameter(p1, createOutput=False)
        self.addParameter(QgsProcessingParameterString(
            self.CODE,
            description='Python code',
            defaultValue="""profiledata=profiledata\nx_unit=x_unit\nbbl=bbl""",
            multiLine=True,
            optional=False
        ))
        p3 = SpectralProcessingProfilesSink(self.OUTPUT, description='Output Profiles', optional=True)
        self.addParameter(p3, createOutput=True)
        # p2 = SpectralProcessingProfilesOutput(self.OUTPUT, description='Output Profiles')
        # self.addOutput(p2)

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        input_profiles: typing.List[SpectralProfileBlock] = \
            parameterAsSpectralProfileBlockList(parameters, self.INPUT, context)

        output_profiles: typing.List[SpectralProfileBlock] = []
        user_code: str = self.parameterAsString(parameters, self.CODE, context)

        n_block = len(input_profiles)
        for i, profileBlock in enumerate(input_profiles):
            # process block by block
            assert isinstance(profileBlock, SpectralProfileBlock)
            feedback.pushConsoleInfo(f'Process profile block {i + 1}/{n_block}')

            resultBlock, msg = self.applyUserCode(user_code, profileBlock)

            if isinstance(resultBlock, SpectralProfileBlock):
                resultBlock.setFIDs(profileBlock.fids())
                output_profiles.append(resultBlock)
            else:
                feedback
            feedback.setProgress(100 * i / n_block)

        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_profiles
        return OUTPUTS

    def setProcessingFunction(self, function: typing.Callable):

        assert isinstance(function, typing.Callable)
        self.mFunction = function

    def canExecute(self) -> bool:
        result: bool = True
        msg = ''
        return result, msg

    def checkParameterValues(self,
                             parameters: dict,
                             context: QgsProcessingContext,
                             ):

        result, msg = super().checkParameterValues(parameters, context)
        if not self.parameterDefinition(self.INPUT).checkValueIsAcceptable(parameters[self.INPUT], context):
            msg += f'Unable to read {self.INPUT}'

        code = self.parameterAsString(parameters, self.CODE, context)
        # check if we can evaluate the python code
        if not self.parameterDefinition(self.CODE).checkValueIsAcceptable(code, context):
            msg += f'Unable to read {self.CODE}'

        dummyblock = SpectralProfileBlock.dummy()
        resultblock, msg2 = self.applyUserCode(code, dummyblock)
        msg += msg2
        return isinstance(resultblock, SpectralProfileBlock) and len(msg) == 0, msg

    def createCustomParametersWidget(self) -> QWidget:
        w = QWidget()
        label = QLabel('Placeholder for custom widget')
        l = QHBoxLayout()
        l.addWidget(label)
        w.setLayout(l)
        return w

    def createInstance(self):
        alg = SpectralPythonCodeProcessingAlgorithm()
        return alg

    def displayName(self) -> str:

        return 'Spectral Processing Algorithm Example'

    def flags(self):
        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading

    def group(self):
        return 'Test Group'

    def helpString(self) -> str:
        return 'Help String'

    def name(self):
        return self.NAME

    def icon(self):
        return QIcon(':/qps/ui/icons/profile.svg')

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        is_valid, msg = self.checkParameterValues(parameters, context)
        if not is_valid:
            feedback.reportError(msg)
        else:

            s = ""
        return is_valid

    def applyUserCode(self, code, profileBlock: SpectralProfileBlock) -> typing.Tuple[SpectralProfileBlock, str]:
        """
        Applies the python code to a SpectralProfile block
        :param code: str with python code
        :param profileBlock: SpectralProfile block
        :return: (SpectralProfileBlock, '') in case of success, or (None, 'error message') else.
        """
        kwds_global = profileBlock.toVariantMap()
        kwds_local = {}
        msg = ''
        result_block: SpectralProfileBlock = None
        try:
            exec(code, kwds_global, kwds_local)
        except Exception as ex:
            return None, str(ex)

        if not isinstance(kwds_local.get('profiledata', None), np.ndarray):
            msg = 'python code does not return "profiledata" of type numpy.array'
        else:
            try:
                result = {'profiledata': kwds_local['profiledata']}
                for k in ['x', 'x_unit', 'y_unit', 'bbl']:
                    result[k] = kwds_local.get(k, kwds_global.get(k, None))
                result_block = SpectralProfileBlock.fromVariantMap(result)
            except Exception as ex:
                msg = str(ex)
        return result_block, msg