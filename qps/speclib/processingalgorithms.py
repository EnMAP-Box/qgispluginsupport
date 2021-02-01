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

from qgis.core import \
    QgsProcessingAlgorithm, QgsProcessingParameterVectorLayer, \
    QgsProcessingContext, QgsProcessingFeedback, QgsProcessingFeatureSource, \
    QgsProcessingParameterField, QgsProcessingParameterEnum, \
    QgsVectorLayer

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QWidget, QLabel, QHBoxLayout

from .core import SpectralSetting, SpectralProfileBlock, read_profiles, groupBySpectralProperties
from .processing import \
    SpectralProcessingProfiles, SpectralProcessingProfilesOutput, \
    SpectralProcessingProfilesOutputDestination, parameterAsSpectralProfileBlockList


from ..unitmodel import UnitConverterFunctionModel, BAND_INDEX, XUnitModel


class SpectralXUnitConversion(QgsProcessingAlgorithm):
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


    def initAlgorithm(self, configuration):

        p1 = SpectralProcessingProfiles(self.INPUT)
        p2 = QgsProcessingParameterEnum(self.TARGET_XUNIT,
                                        description='Target x/wavelength unit',
                                        options=self.mUnitModel.mUnits,
                                        defaultValue='nm',
                                        )
        o1 = SpectralProcessingProfilesOutput(self.OUTPUT)
        self.addParameter(p1)
        self.addParameter(p2)
        self.addOutput(o1)
        self.mParameters.extend([p1, p2, o1])

        self.addOutput(SpectralProcessingProfilesOutput(self.OUTPUT, 'Spectral Profiles'))

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

        targetUnit = self.parameterAsString(parameters, self.TARGET_XUNIT, context)
        input_profiles = parameterAsSpectralProfileBlockList(parameters, self.INPUT, context)
        output_profiles: typing.List[SpectralProcessingProfilesOutput] = []
        n_blocks = len(input_profiles)
        for i, profileBlock in enumerate(input_profiles):
            # process block by block

            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)
            feedback.pushConsoleInfo(f'Process profile block {i + 1}/{n_blocks}')

            spectralSetting = profileBlock.spectralSetting()

            f = self.mUnitConverterFunctionModel.convertFunction(spectralSetting.xUnit(), targetUnit)
            if callable(f):
                xValuesNew = f(profileBlock.xValues())
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


class SpectralProfileReader(QgsProcessingAlgorithm):
    """
    Reads spectral profile block from SpectralLibraries / Vectorlayers with BLOB columns
    """
    INPUT = 'input_speclib'
    INPUT_FIELD = 'input_field'
    OUTPUT = 'output_profiles'

    def __init__(self):
        super().__init__()
        self.mParameters = []

    def description(self) -> str:
        return 'Reads spectral profiles'

    def initAlgorithm(self, configuration: dict):
        from .core import FIELD_VALUES
        self.addParameter(QgsProcessingParameterVectorLayer(self.INPUT, 'Spectral Library'))

        self.addParameter(QgsProcessingParameterField(self.INPUT_FIELD, 'Profile column',
                                                      defaultValue=FIELD_VALUES,
                                                      parentLayerParameterName=self.INPUT,
                                                      allowMultiple=False))

        self.addOutput(SpectralProcessingProfilesOutput(self.OUTPUT, 'Spectral Profiles'))

    def asPythonCommand(self) -> str:
        pass

    def canExecute(self, parameters: dict, context: QgsProcessingContext) -> bool:
        return True

    def checkParameterValues(self,
                             parameters: dict,
                             context: QgsProcessingContext,
                             ):
        result = True
        msg = ''
        # check parameters

        return result, msg

    def createInstance(self):
        alg = SpectralProfileReader()
        return alg

    def displayName(self) -> str:
        return 'Spectral Profile Reader'

    def flags(self):
        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading

    def group(self):
        return 'qps'

    def helpString(self) -> str:
        return 'Spectral Profile Reader Help String'

    def name(self):
        return 'spectral_profile_reader'

    def icon(self):
        return QIcon(':/qps/ui/icons/profile.svg')

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        for key in [self.INPUT, self.INPUT_FIELD]:
            if not key in parameters.keys():
                feedback.reportError(f'Missing parameter {self.INPUT}')
                return False
        return True

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        speclib: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.INPUT, context)
        field: typing.List[str] = self.parameterAsFields(parameters, self.INPUT_FIELD, context)

        output_blocks = list(
            SpectralProfileBlock.fromSpectralProfiles(read_profiles(speclib, value_fields=field),
                                                                 feedback=feedback)
        )
        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_blocks
        return OUTPUTS


class SpectralProfileWriter(QgsProcessingAlgorithm):
    INPUT = 'input_profiles'
    OUTPUT = 'output_speclib'

    def __init__(self):
        super().__init__()
        self.mParameters = []

    def description(self) -> str:
        return 'Writes spectral profiles'

    def initAlgorithm(self, configuration: dict):
        p1 = SpectralProcessingProfiles(self.INPUT)
        o1 = SpectralProcessingProfilesOutput(self.OUTPUT)
        self.addParameter(p1)
        self.addOutput(o1)
        self.mParameters.append([p1, o1])

    def asPythonCommand(self) -> str:
        pass

    def canExecute(self, parameters: dict, context: QgsProcessingContext) -> bool:
        return True

    def checkParameterValues(self,
                             parameters: dict,
                             context: QgsProcessingContext,
                             ):
        result = True
        msg = ''
        # check parameters

        return result, msg

    def createInstance(self):
        alg = SpectralProfileWriter()
        return alg

    def displayName(self) -> str:
        return 'Spectral Profile Writer'

    def flags(self):
        return QgsProcessingAlgorithm.FlagSupportsBatch | QgsProcessingAlgorithm.FlagNoThreading

    def group(self):
        return 'qps'

    def helpString(self) -> str:
        return 'Spectral Profile Writer Help String'

    def name(self):
        return 'spectral_profile_writer'

    def icon(self):
        return QIcon(':/qps/ui/icons/profile.svg')

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        return True

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        input_profiles: parameterAsSpectralProfileBlockList(parameters, self.INPUT, context)
        speclib = self.parameterAsOutputLayer(parameters, self.OUTPUT, context)

        output_blocks: typing.List[SpectralProfileBlock] = []
        for profileBlock in input_profiles:
            # process block by block
            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)
            output_blocks.append(profileBlock)
        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_blocks
        return OUTPUTS

