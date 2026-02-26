from PyQt5.QtCore import QAbstractListModel


class SelectProjectLayersDialog(QDialog):

    def __init__(self, *args, project = None, **kwds):

        if project is None:
            project = QgsProject.instance()
        else:
            assert isinstance(project, QgsProject)
        self.mProject = None
        self.setProject(project)
        self.mModel = ProjectLayerListModel()

    def setProject(self, project: QgsProject):
        self.mModel.setProject(project)

    def selectedLayers(self) -> List[QgsMapLayer]:

        pass

    def

class ProjectLayerListModel(QAbstractListModel):

    def __init__(self, project: Optional[QgsProject]):
        self.mProject = QgsProject.instance()
        self.setProject(project)

    def setProject(self, project):

        if project is None:
            project = QgsProject.instance()
        else:
            assert isinstance(project, QgsProject)
        if self.mProject == project:
            return

        self.beginResetModel()
        self.mProject = project
        self.endResetModel()
