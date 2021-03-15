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
    QgsVectorLayer, QgsProcessingParameterVectorDestination, \
    QgsFeature, QgsProcessingOutputVectorLayer

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QWidget, QLabel, QHBoxLayout

from .core import SpectralSetting, SpectralProfileBlock, read_profiles, \
    groupBySpectralProperties, SpectralLibrary, FIELD_VALUES, encodeProfileValueDict, decodeProfileValueDict
from .processing import \
    SpectralProcessingProfiles, SpectralProcessingProfilesOutput, \
    SpectralProcessingProfilesSink, parameterAsSpectralProfileBlockList

from ..unitmodel import UnitConverterFunctionModel, BAND_INDEX, XUnitModel


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
                                        options=self.mUnitModel.mUnits,
                                        defaultValue=0,
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

        targetUnit = self.parameterAsEnum(parameters, self.TARGET_XUNIT, context)
        targetUnit = self.mUnitModel.mUnits[targetUnit]
        input_profiles = parameterAsSpectralProfileBlockList(parameters, self.INPUT, context)
        output_profiles: typing.List[SpectralProcessingProfilesOutput] = []
        n_blocks = len(input_profiles)
        for i, profileBlock in enumerate(input_profiles):
            # process block by block

            assert isinstance(profileBlock, SpectralProfileBlock)
            print(profileBlock)
            feedback.pushConsoleInfo(f'Process profile block {i + 1}/{n_blocks}')
            spectralSetting = profileBlock.spectralSetting()
            if spectralSetting.xUnit() == targetUnit:
                # output unit is already correct
                output_profiles.append(profileBlock)
            else:
                f = self.mUnitConverterFunctionModel.convertFunction(spectralSetting.xUnit(), targetUnit)
                if callable(f):
                    xValuesNew = f(profileBlock.xValues())
                    settingOut = SpectralSetting(xValuesNew,
                                                 xUnit=targetUnit,
                                                 yUnit=spectralSetting.yUnit(),
                                                 )
                    blockOut = SpectralProfileBlock(profileBlock.data(),
                                                    spectralSetting=settingOut,
                                                    profileKeys=profileBlock.profileKeys(),
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
    INPUT = 'input_speclib'
    INPUT_FIELD = 'input_field'
    OUTPUT = 'output_profiles'

    def __init__(self):
        super().__init__()
        self.mParameters = []

    def shortDescription(self) -> str:
        return 'Reads spectral profiles'

    def initAlgorithm(self, configuration: dict):
        from .core import FIELD_VALUES
        self.addParameter(QgsProcessingParameterVectorLayer(self.INPUT, 'Spectral Library'))

        self.addParameter(QgsProcessingParameterField(self.INPUT_FIELD, 'Profile column',
                                                      defaultValue=FIELD_VALUES,
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

        output_blocks: typing.List[SpectralProfileBlock] = list(
            SpectralProfileBlock.fromSpectralProfiles(read_profiles(speclib, value_fields=field),
                                                      feedback=feedback)
        )
        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = output_blocks
        return OUTPUTS


class SpectralProfileWriter(_AbstractSpectralAlgorithm):
    INPUT = 'input_profiles'
    OUTPUT = 'output_speclib'
    OUTPUT_FIELD = 'output_speclib_field'

    def __init__(self):
        super().__init__()
        self.mParameters = []

    def shortDescription(self) -> str:
        return 'Writes spectral profiles'

    def initAlgorithm(self, configuration: dict):
        p1 = SpectralProcessingProfiles(self.INPUT)
        p2 = QgsProcessingParameterVectorDestination(self.OUTPUT)
        p3 = QgsProcessingParameterField(self.OUTPUT_FIELD,
                                         defaultValue=FIELD_VALUES,
                                         optional=True,
                                         parentLayerParameterName=self.OUTPUT)

        self.addParameter(p1)
        self.addParameter(p2, createOutput=True)
        self.addParameter(p3)

        # self.addOutput(QgsProcessingOutputVectorLayer(self.OUTPUT, 'Spectral Library'))

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

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):
        return True

    def processAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        input_profiles: typing.List[SpectralProfileBlock] = parameterAsSpectralProfileBlockList(parameters, self.INPUT,
                                                                                                context)
        speclib: SpectralLibrary = self.parameterAsVectorLayer(parameters, self.OUTPUT, context)

        existing_fids = []
        if isinstance(speclib, SpectralLibrary):

            existing_fids = speclib.allFeatureIds()
        else:
            s = ""

        field = self.parameterAsFields(parameters, self.OUTPUT_FIELD, context)[0]
        assert field in speclib.fields().names()
        i_field = speclib.fields().lookupField(field)

        editable: bool = speclib.isEditable()
        assert speclib.startEditing()
        output_blocks: typing.List[SpectralProfileBlock] = []

        replace_fids = True

        for block in input_profiles:
            # process block by block
            assert isinstance(block, SpectralProfileBlock)
            # append new features
            new_features = []
            for ba in block.profileValueByteArrays():
                f = QgsFeature(speclib.fields())
                f.setAttribute(i_field, ba)
                new_features.append(f)
            # todo: allow to overwrite existing features
            assert speclib.addFeatures(new_features)
        s = ""

        assert speclib.commitChanges()
        if editable:
            speclib.startEditing()

        OUTPUTS = dict()
        OUTPUTS[self.OUTPUT] = speclib

        return OUTPUTS


def createSpectralAlgorithms() -> typing.List[QgsProcessingAlgorithm]:
    """
    Returns the spectral processing algorithms defined in this module
    """
    return [
        SpectralProfileReader(),
        SpectralProfileWriter(),
        SpectralXUnitConversion(),
    ]