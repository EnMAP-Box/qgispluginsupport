from qgis._core import QgsVectorLayer, QgsFields, QgsRectangle, QgsDataProvider, QgsRasterDataProvider


class SpectralLibraryRasterDataProvider(QgsRasterDataProvider):
    """
    An
    """

    def __init__(self, spectrallibrary):
        pass
        uri = ''
        providerOptions = QgsDataProvider.ProviderOptions()
        flags = QgsDataProvider.ReadFlags()

        super().__init__(uri, providerOptions)

        self.mSpeclib: QgsVectorLayer = None

    def setSpeclib(self, speclib:QgsVectorLayer):

        s = ""

    def fields(self) -> QgsFields:
        return QgsFields()

    def extent(self) -> QgsRectangle:
        return QgsRe