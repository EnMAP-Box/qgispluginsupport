# -*- coding: utf-8 -*-
# noinspection PyPep8Naming
"""
***************************************************************************
    speclib/qgsfunctions.py
    qgsfunctions to be used in QgsExpressions to access SpectralLibrary data
    ---------------------
    Date                 : Okt 2018
    Copyright            : (C) 2018 by Benjamin Jakimow
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
from qgis.core import QgsExpression, QgsFeature, qgsfunction

from .core import FIELD_VALUES, decodeProfileValueDict, SpectralProfile

QGS_FUNCTION_GROUP = "Spectral Libraries"


@qgsfunction(0, QGS_FUNCTION_GROUP, referenced_columns=FIELD_VALUES)
def spectralProfileDict(values, feature, parent) -> dict:
    """
    Returns the SpectralProfile dictionary will all profile internal properties
    :param values:
    :param feature:
    :param parent:
    :return: dict
    """
    if isinstance(feature, QgsFeature):
        i = feature.fieldNameIndex(FIELD_VALUES)
        if i >= 0:
            values = decodeProfileValueDict(feature.attribute(i))
            return values
    return None


@qgsfunction(0, QGS_FUNCTION_GROUP, referenced_columns=FIELD_VALUES)
def spectralValues(values, feature, parent) -> typing.List[float]:
    """
    Returns the spectral values, i.e. a list of numbers typically plotted on Y axis
    :param values:
    :param feature:
    :param parent:
    :return: dict
    """
    if isinstance(feature, QgsFeature):
        try:
            profile: SpectralProfile = SpectralProfile.fromSpecLibFeature(feature)
            return profile.yValues()
        except:
            return None
    return None


@qgsfunction(0, QGS_FUNCTION_GROUP, referenced_columns=FIELD_VALUES)
def wavelengthUnit(values, feature, parent) -> str:
    """
    Returns the SpectralProfiles wavelength unit, e.g. 'nm', or 'μm'
    :param values:
    :param feature:
    :param parent:
    :return: dict
    """
    if isinstance(feature, QgsFeature):
        try:
            profile: SpectralProfile = SpectralProfile.fromSpecLibFeature(feature)
            return profile.xUnit()
        except:
            return None
    return None


@qgsfunction(0, QGS_FUNCTION_GROUP, referenced_columns=FIELD_VALUES)
def wavelengths(values, feature, parent) -> typing.List[float]:
    """
    Returns the list of wavelength related to each spectral profile value.

    :param values:
    :param feature:
    :param parent:
    :return: dict
    """
    if isinstance(feature, QgsFeature):
        try:
            profile: SpectralProfile = SpectralProfile.fromSpecLibFeature(feature)
            return profile.xValues()
        except:
            return None
    return None


def registerQgsExpressionFunctions():
    """
    Registers functions to support SpectraLibrary handling with QgsExpressions
    """
    # QgsExpression.registerFunction(plotStyleSymbolFillColor)
    # QgsExpression.registerFunction(plotStyleSymbol)
    # QgsExpression.registerFunction(plotStyleSymbolSize)
    QgsExpression.registerFunction(spectralValues)
    QgsExpression.registerFunction(wavelengthUnit)
    QgsExpression.registerFunction(wavelengths)
    QgsExpression.registerFunction(spectralProfileDict)
