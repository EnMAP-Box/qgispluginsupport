# Wavelength Info Example Datasets


Do not modify images manually, as they are created by create_testdata.py

| Dataset                           | Notes                                                             |
| --------------------------------- | ----------------------------------------------------------------- |
| enmapbox_envidomain_bandlevel.tif | tif with ENVI domain at band level                                |
| enmapbox_envidomain_dslevel.tif   | tif with ENVI domain at dataset level                             |
| envi_wl_fwhm.bsq                  | classic ENVI BSQ with wavelength, wavelength units, fwhm, and bbl |
| envi_wl_implicit_nm.bsq           | ENVI BSQ with missing wavelength units, expect nm                 |
| envi_wl_implicit_um.bsq           | ENVI BSQ with missing wavelength units, expect micrometers        |
| gdal_no_info.tif                  | no wavelength info                                                |
| gdal_wl_fwhm.tif                  | gdal 3.10+ with IMAGERY:CENTRAL_WAVELENGTH_UM and IMAGERY:FWHM_UM |
| gdal_wl_only.tif                  | gdal 3.10+ with IMAGERY:CENTRAL_WAVELENGTH_UM                     |
