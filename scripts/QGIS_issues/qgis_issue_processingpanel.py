from processing.gui.ProcessingToolbox import ProcessingToolbox


def executeWithGui(str, QWidget, bool, bool):
    s = ""


toolbox = ProcessingToolbox()
toolbox.executeWithGui.connect(executeWithGui)
