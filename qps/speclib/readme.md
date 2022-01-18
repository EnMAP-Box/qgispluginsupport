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

## Background

Spectral profiles can be considered like pixels of a raster image: They have a number of band values and 
each band value can be related to a designated wavelength and a spectral response function, which might be 
described by (i) a center wavelength + full width at half maximum values, or (ii) a 
band specific spectral response function.

There are several use-cases where Spectral Library profile and 
Raster image profiles can be handled in the same fashion, for example:

- removing subsets of single bands
- scaling pixel values
- deriving convex hull profile
- classification of pixel to derive thematic categories


The Spectral Processing package allows processing Spectral Libraries, and more general each QgsVectorLayer,
with processing algorithms that are optimized for operating on raster images.

## General Approach

Image processing algorithms are defined as QgsProcessingAlgorithms or QgsProcessingModel,  
which inherit the QgsProcessingAlgorithm interface.

Each QgsProcessingAlgorithm defines (i) input parameters and (ii) output parameters. 
To apply QgsProcessingAlgorithms on SpectralLibraries / QgsVectorLayers
1. values in vector fields are translated into raster images
2. the raster images are used as input parameter values of the QgsProcessingAlgorithms
3. the output rasters are translated back into field values of the Spectral Library / QgsVectorLayer

## Type Mapping

This table shows how field values of a QgsVectorLayer are translated into raster image inputs.  

| Field                                             | Type       | Type Name | Raster image size <br>bands x height x width, type | Raster No-data |
|---------------------------------------------------|------------|-----------|----------------------------------------------------|----------------|
| Binary                                            | QByteArray | binary    | N/A                                                |                |
| Binary, SpectralProfile <br>nb bands float/double | QByteArray | binary    | nb x 1 x nf, float/double                          | NaN            |
| Whole number                                      | int        | integer   | 1 x 1 x nf, int                                    | -1 (1)         |
| Decimal number                                    | double     | double    | 1 x 1 x nf, double                                 | NaN            |
| Boolean                                           | bool       | boolean   | 1 x 1 x nf, int, NBITS=2                           | -1             |
| Date                                              | QDate      | date      | <not specified>                                    |                |
| Time                                              | QTime      | time      | <not specified>                                    |                |
| DateTime                                          | QDateTime  | datetime  | <not specified>                                    |                |
| Text                                              | QString    | string    | 1 x 1 x nf, int classified                         | (2)            |


(1) No-data value is found in order of:
 -1, -9999, lowest field values - 1 

(2) Unique Text values are assigned to numeric class labels by alphanumeric sorting

The number of spectral profiles x is the number of spectral library features with a
similar SpectralSetting:

A SpectralLibrary with two spectral profile fields A and B: 

| FID | ProfilesA | ProfilesB |
|-----|-----------|-----------|
| 1   | 50 bands  | 50 bands  |
| 2   | 50 bands  | 50 bands  |
| 3   | 30 bands  | 50 bands  |
| 4   | 30 bands  | 30 bands  |

can be translated into images of size = bands x height x width, 
where width = number of corresponding FIDs:

| FID List | ProfilesA.tif | ProfilesB.tif |
|----------|---------------|---------------|
| [1,2]    | 50x1x2        | 50x1x2        |
| [3]      | 30x1x1        | 50x1x1        |
| [4]      | 30x1x1        | 30x1x1        |

## Mapping QgsProcessingAlgorithm outputs to SpectralLibrary fields:

Requirement: output raster layers have a width x = number of input SpectralProfiles 

| QgsProcessingAlgorithm Output           | Field           | Type Name  |
|-----------------------------------------|-----------------|------------|
| QgsRasterLayer with n > 0 bands         | SpectralProfile | QByteArray |
| QgsRasterLayer with n = 1 band, float   | Decimal Number  | double     |
| QgsRasterLayer with n = 1 band, integer | Whole Number    | int        |
| QgsVectorLayer                          |                 |            |
| Other file                              |                 |            |

* Output image names define the new field names:

  `myoutput.tif --> "myoutput"`

* Values in existing fields can be overwritten:

    `"myprofiles" --> myprofiles.tif --> "myprofiles"`





