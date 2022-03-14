from processing.gui.ProcessingToolbox import ProcessingToolbox


def executeWithGui(str, QWidget, a: bool, b: bool):
    s = ""


toolbox = ProcessingToolbox()
toolbox.executeWithGui.connect(executeWithGui)
