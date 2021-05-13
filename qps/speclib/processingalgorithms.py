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

from PyQt5.QtCore import QVariant
from qgis._core import QgsField, QgsProcessingOutputVectorLayer, QgsFeatureRequest

from qgis.core import \
    QgsProcessingAlgorithm, QgsProcessingParameterVectorLayer, \
    QgsProcessingContext, QgsProcessingFeedback, QgsProcessingParameterField, QgsProcessingParameterEnum, \
    QgsVectorLayer, QgsProcessingParameterVectorDestination, \
    QgsFeature

from qgis.PyQt.QtGui import QIcon
from .core import field_index, profile_fields, create_profile_field

from .core.spectrallibrary import SpectralSetting, SpectralProfileBlock, read_profiles, \
    SpectralLibrary, FIELD_VALUES
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
    _MODES = ['Append', 'Overwrite', 'Match']
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
        p4 = QgsProcessingParameterEnum(self.MODE, options=self._MODES, defaultValue=2)
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

    def prepareAlgorithm(self,
                         parameters: dict,
                         context: QgsProcessingContext,
                         feedback: QgsProcessingFeedback):

        for key in [self.INPUT, self.OUTPUT]:
            if key not in parameters.keys():
                feedback.reportError(f'Missing parameter {key}')
                return False
        mode = self.parameterAsEnum(parameters, self.MODE, context)
        mode = self._MODES[mode]
        speclib: QgsVectorLayer = self.parameterAsVectorLayer(parameters, self.OUTPUT, context)
        if isinstance(speclib, QgsVectorLayer):

            existing_profile_fields = profile_fields(speclib)
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
                existing_profile_fields = profile_fields(speclib)

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


        input_profiles: typing.List[SpectralProfileBlock] = parameterAsSpectralProfileBlockList(parameters, self.INPUT,
                                                                                                context)
        mode = self.parameterAsEnum(parameters, self.MODE, context)
        mode = self._MODES[mode]
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
        if mode == 'Append':
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
        elif mode == 'Overwrite':
            gen = speclib.getFeatures()
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
        elif mode == 'Match':
            for block in input_profiles:
                # process block by block
                fids = block.fids()
                existing = [f for f in fids if f in speclib.allFeatureIds()]
                others = [f for f in fids if f not in existing]

                request = QgsFeatureRequest()
                request.setFids(fids)
                for f in speclib.getFeatures(request):
                    s = ""


                assert isinstance(block, SpectralProfileBlock)
                # append new features
                new_features = []
                for i, ba in enumerate(block.profileValueByteArrays()):
                    fid = fids[i]

                    f = QgsFeature(speclib.fields())
                    f.setAttribute(i_field, ba)
                    new_features.append(f)
                # todo: allow to overwrite existing features
                assert speclib.addFeatures(new_features)
        else:
            raise NotImplementedError()

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
