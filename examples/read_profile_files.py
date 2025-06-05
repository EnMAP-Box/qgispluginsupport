from pathlib import Path

from qps import initAll
from qps.speclib.processing.importspectralprofiles import ImportSpectralProfiles
from qps.testing import start_app, TestCase

start_app()
initAll()

path_dir = r'F:\Temp\SVC_Backup\20250604_ZALF'
path_dir = r'F:\Temp\SVC_Backup\20250605_Lasse'
path_speclib = Path(path_dir) / 'speclib.gpkg'

alg = ImportSpectralProfiles()
alg.initAlgorithm({})

param = {
    alg.P_INPUT: path_dir,
    alg.P_OUTPUT: path_speclib.as_posix(),
    alg.P_USE_RELPATH: True,
}

context, feedback = TestCase.createProcessingContextFeedback()
alg.run(param, context, feedback)
