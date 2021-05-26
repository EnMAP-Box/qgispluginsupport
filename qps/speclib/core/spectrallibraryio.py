import typing

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QWidget, QMenu
from qgis.core import QgsField, QgsExpression, QgsExpressionContext

from qgis.core import QgsProcessingFeedback
from .spectrallibrary import SpectralLibrary
from .spectralprofile import SpectralProfile

class AbstractSpectralLibraryExportWidget(QWidget):
    """
    Abstract Interface of an Widget to export / write a spectral library
    """

    def __init__(self, *args, **kwds):
        super(AbstractSpectralLibraryExportWidget, self).__init__(*args, **kwds)

    def formatName(self) -> str:
        raise NotImplementedError()

    def icon(self) -> QIcon():
        return QIcon()

    def exportSpeclib(self, speclib: SpectralLibrary):
        raise NotImplementedError()


class AbstractSpectralLibraryImportWidget(QWidget):

    def __init__(self, *args, **kwds):
        super(AbstractSpectralLibraryImportWidget, self).__init__(*args, **kwds)

    def icon(self) -> QIcon:
        return QIcon()

    def formatName(self) -> str:
        raise NotImplementedError()


class AbstractSpectralLibraryIO(object):
    """
    Abstract class interface to define I/O operations for spectral libraries
    """
    _SUB_CLASSES = []

    def __init__(self):

        self.mProfileNameDefault: QgsExpression = QgsExpression('Profile $id')
        self.mProfileNameContext: QgsExpressionContext = QgsExpressionContext()

    @staticmethod
    def subClasses():

        from ..io.vectorsources import VectorSourceSpectralLibraryIO
        from ..io.artmo import ARTMOSpectralLibraryIO
        from ..io.asd import ASDSpectralLibraryIO
        from ..io.clipboard import ClipboardIO
        from ..io.csvdata import CSVSpectralLibraryIO
        from ..io.ecosis import EcoSISSpectralLibraryIO
        from ..io.envi import EnviSpectralLibraryIO
        from ..io.specchio import SPECCHIOSpectralLibraryIO

        subClasses = [
            VectorSourceSpectralLibraryIO,  # this is the preferred way to save/load speclibs
            EnviSpectralLibraryIO,
            ASDSpectralLibraryIO,
            CSVSpectralLibraryIO,
            ARTMOSpectralLibraryIO,
            EcoSISSpectralLibraryIO,
            SPECCHIOSpectralLibraryIO,
            ClipboardIO,
        ]

        # other sub-classes
        for c in AbstractSpectralLibraryIO.__subclasses__():
            if c not in subClasses:
                subClasses.append(c)

        return subClasses

    @classmethod
    def canRead(cls, path: str) -> bool:
        """
        Returns true if it can read the source defined by path.
        Well behaving implementations use a try-catch block and return False in case of errors.
        :param path: source uri
        :return: True, if source is readable.
        """
        return False

    @classmethod
    def readFrom(cls, path: str,
                 feedback: QgsProcessingFeedback = None) -> SpectralLibrary:
        """
        Returns the SpectralLibrary read from "path"
        :param path: source of Spectral Library
        :param feedback: QProgressDialog, which well-behave implementations can use to show the import progress.
        :return: SpectralLibrary
        """
        return None

    @classmethod
    def write(cls,
              speclib: SpectralLibrary,
              path: str,
              profile_field: typing.Union[int, str, QgsField] = None,
              profile_name: QgsExpression = None,
              feedback: QgsProcessingFeedback = None,
              **kwargs) -> \
            typing.List[str]:
        """
        Writes the SpectralLibrary.
        :param speclib: SpectralLibrary to write
        :param path: file path to write the SpectralLibrary to
        :param profile_field: the profile column with  which SpectralProfiles to write.
        :param profile_name: a QgsExpression to generate a profile name string, e.g. based on other field attributes.
        :param feedback:  QProgressDialog, which well-behave implementations can use to show the writing progress.
        :return: a list of paths that can be used to re-open all written profiles
        """
        assert isinstance(speclib, SpectralLibrary)
        return []

    @classmethod
    def supportedFileExtensions(cls) -> typing.Dict[str, str]:
        """
        Returns a dictionary of file extensions (key) and descriptions (values)
        that can be read/written by the AbstractSpectralLibraryIO implementation.
        :return: dict[str,str]
        """
        return dict()

    @classmethod
    def filterString(cls) -> str:
        """
        Returns a filter string to be used in QFileDialogs
        :return: str
        """
        return ';;'.join([f'{descr} (*{ext})' for ext, descr
                          in cls.supportedFileExtensions().items()])

    @classmethod
    def score(cls, uri: str) -> int:
        uri = str(uri)
        """
        Returns a score value for the give uri. E.g. 0 for unlikely/unknown, 20 for yes, probably thats the file format the reader can read.

        :param uri: str
        :return: int
        """
        for ext in cls.supportedFileExtensions().keys():
            if uri.endswith(ext):
                return 20
        return 0

    @classmethod
    def addImportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu):
        """
        Returns a list of QActions or QMenus that can be called to read/import SpectralProfiles from a certain file format into a SpectralLibrary
        :param spectralLibrary: SpectralLibrary to import SpectralProfiles to
        :return: [list-of-QAction-or-QMenus]
        """
        return []

    @classmethod
    def addExportActions(cls, spectralLibrary: SpectralLibrary, menu: QMenu):
        """
        Returns a list of QActions or QMenus that can be called to write/export SpectralProfiles into certain file format
        :param spectralLibrary: SpectralLibrary to export SpectralProfiles from
        :return: [list-of-QAction-or-QMenus]
        """
        return []

    @classmethod
    def createImportWidget(cls) -> AbstractSpectralLibraryImportWidget:
        """
        Creates a Widget to import data into a SpectralLibrary
        :return:
        """
        pass

    @classmethod
    def createExportWidget(cls) -> AbstractSpectralLibraryExportWidget:
        """
        Creates a widget to export a SpectralLibrary
        :return:
        """