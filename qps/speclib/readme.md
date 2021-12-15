# Spectral Library Module

This file contains information on the Spectral Library Module

## Definitions

**SpectralLibrary** A QgsVectorLayer that contains with at least 1 QgsField of type binary and widget type Spectral Profile

*SpectralProfile* single representation of a spectral profile. 
    Contains at least a vector of y values 

## Packages

`speclib/core`  core classes

`speclib/gui` classes around the spectral library widget

`speclib/io` Input/Output routines to import or export spectral profiles from other file formats

`speclib/ui` *.ui classes



## Spectral Processing

See `speclib/ui/spectralprocessingwidget.py` 


This section describes how image processing chains can be applied on spectral profiles of a spectral libraries.

Background: spectral profiles are like pixels in a raster image. 
It should be possible to manipulate pixel profiles with the same methods which can be used to manipulate the 
pixel values in a raster image. for example to remove bad bands, to select feature subsets or to calculate spectral indices.

General Formulation:

A QgsProcessingAlgorithm / QgsProcessingModel consumes (i) input parameters and produces (ii) output parameters.


Input Parameters:

Type:

raster data:
vector data:

## Mapping SpectralLibrary fields to QgsProcessingAlgorithm input parameters:

The following Spectral library field can be available as raster image inputs 

Field | Type | Type Name | Mapped QgsProcessingAlgorithm Input 
--- | --- | --- | ---
SpectralProfile | QByteArray | binary | QgsRasterLayer with n bands and x pixel for x profiles with length n  
Binary | QByteArray | binary | <not specified>
Whole number | int | integer | QgsRasterLayer with 1 band of type integer 
Decimal number | double | double | QgsRasterLayer with 1 band of type double
Boolean | bool | boolean | QgsRasterLayer with 1 band of type bool 
Date | QDate | date | <not specified>
Time | QTime | time | <not specified>
DateTime | QDateTime | datetime | <not specified>


Dimensions of raster image inputs:
- width = x = number of spectral profiles 
- height = 1
- bands = number of spectral profile bands, or 1 in case of other numeric fields
- QgsCoordinateReferenceSystem = unspecified

The number of spectral profiles x is the number of spectral library features with a
similar SpectralSetting:

A SpectralLibrary with two spectral profile fields A and B: 


FID | ProfilesA | ProfilesB
--- | --- | ---
1 | 50 bands | 50 bands
2 | 50 bands | 50 bands
3 | 30 bands | 50 bands
4 | 30 bands | 30 bands

can be translated into images of size = bands x height x width, with width = number of corresponding FIDs:

FID List | ProfilesA.tif | ProfilesB.tif
--- | --- | ---
[1,2] | 50x1x2 | 50x1x2
[3] | 30x1x1 | 50x1x1
[4] | 30x1x1 | 30x1x1



## Mapping QgsProcessingAlgorithm outputs to SpectralLibrary fields:

Requirement: output raster layers have a width x = number of input SpectralProfiles 

QgsProcessingAlgorithm Output | Field | Type Name
--- | --- | ---
QgsRasterLayer with n > 0 bands | SpectralProfile | QByteArray
QgsRasterLayer with n = 1 band, float | Decimal Number | double
QgsRasterLayer with n = 1 band, integer | Whole Number | int
QgsVectorLayer | | 
Other file | |

* Output image names define the new field names:

  `myoutput.tif --> "myoutput"`

* Values in existing fields can be overwritten:

    `"myprofiles" --> myprofiles.tif --> "myprofiles"`





