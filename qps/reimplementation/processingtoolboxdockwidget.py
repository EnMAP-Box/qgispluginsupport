"""
***************************************************************************
    processingtoolboxdockwidget.py
    ---------------------
    Date                 : November 2026
    Copyright            : (C) 2026 by QGIS Plugin Support
    Email                : info at qgis dot org
***************************************************************************
*                                                                         *
*   This program is free software; you can redistribute it and/or modify  *
*   it under the terms of the GNU General Public License as published by  *
*   the Free Software Foundation; either version 2 of the License, or     *
*   (at your option) any later version.                                   *
*                                                                         *
***************************************************************************
"""

__author__ = "Benjamin Jakimow"
__date__ = "November 2026"

import warnings
from typing import List

from qgis.PyQt.QtCore import QSize, pyqtSignal
from qgis.PyQt.QtCore import Qt, QCoreApplication
from qgis.PyQt.QtWidgets import QAction, QMenu, QToolButton, QWidget, QVBoxLayout
from qgis.PyQt.QtWidgets import QToolBar, QWidgetAction
from qgis.core import QgsApplication, QgsProcessingProvider, QgsSettings, Qgis
from qgis.core import QgsProcessingAlgorithm
from qgis.gui import QgisInterface
from qgis.gui import (
    QgsDockWidget,
    QgsFilterLineEdit,
    QgsGui,
    QgsProcessingToolboxProxyModel,
    QgsProcessingToolboxTreeView,
)

QGIS_VERSION_INT = Qgis.versionInt()


def _icon_size():
    """
    Get the icon size for the toolbar.
    QGIS 4.4+ has QgsGui.instance().iconSize(), earlier versions use default size.
    :return: QSize icon size
    """
    if QGIS_VERSION_INT >= 44000:  # QGIS 4.4.0
        return QgsGui.instance().iconSize()
    else:
        # Fallback to default icon size
        settings = QgsSettings()
        w = settings.value("/qgis/toolbarIconSize", 16, type=int)
        return QSize(w, w)
        # return QApplication.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon).actualSize()


def _processing_recent_algorithm_log():
    """
    Get the processing recent algorithm log.
    QGIS 4.4+ has QgsGui.instance().processingRecentAlgorithmLog().
    :return: QgsProcessingRecentAlgorithmLog or None
    """
    if QGIS_VERSION_INT >= 44000:
        return QgsGui.instance().processingRecentAlgorithmLog()
    return None


def _processing_favorite_algorithm_manager():
    """
    Get the processing favorite algorithm manager.
    QGIS 4.4+ has QgsGui.instance().processingFavoriteAlgorithmManager().
    :return: QgsProcessingFavoriteAlgorithmManager or None
    """
    if QGIS_VERSION_INT >= 44000:
        return QgsGui.instance().processingFavoriteAlgorithmManager()
    return None


def _processing_gui_registry():
    """
    Get the processing GUI registry.
    QGIS 4.4+ has QgsGui.instance().processingGuiRegistry().
    :return: QgsProcessingGuiRegistry or None
    """

    return QgsGui.instance().processingGuiRegistry()


class ProcessingToolboxDockWidget(QgsDockWidget):
    """
    A Python reimplementation of QgsProcessingToolboxDockWidget using PyQGIS API.

    This class provides a processing toolbox dock widget showing algorithms
    and providers in a tree structure with search and filtering capabilities.

    .. note::
        This reimplementation uses PyQGIS API only and adapts to different QGIS versions.
        Some features may be limited.

    """
    executeAlgorithm = pyqtSignal(str)

    def __init__(self, parent: QWidget = None):
        """
        Constructor for QgsProcessingToolboxDockWidget.

        :param parent: Parent widget
        """
        super().__init__(parent)

        self.setWindowTitle("Processing Toolbox")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )

        # Create central widget
        self.centralWidget = QWidget()
        self.setWidget(self.centralWidget)

        # Create main layout
        self.mainLayout = QVBoxLayout()
        self.mainLayout.setSpacing(0)
        self.mainLayout.setContentsMargins(0, 0, 0, 0)
        self.centralWidget.setLayout(self.mainLayout)

        # Create toolbar
        self.processingToolbar = QToolBar(self.centralWidget)
        self.processingToolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.processingToolbar.setIconSize(_icon_size())
        # Store actions for toolbar
        self._toolbarActions = dict()
        self._provider_buttons = dict()

        # Create search box
        self.searchBox = QgsFilterLineEdit(self.centralWidget)
        self.searchBox.setShowSearchIcon(True)
        self.searchBox.setPlaceholderText(QCoreApplication.translate("QgsProcessingToolboxDockWidget", "Search…"))

        # Create algorithm tree view
        self.algorithmTree = QgsProcessingToolboxTreeView(self.centralWidget)
        self.algorithmTree.setHeaderHidden(True)
        self.algorithmTree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)

        # Add widgets to layout
        self.mainLayout.addWidget(self.processingToolbar)
        self.mainLayout.addWidget(self.searchBox)
        self.mainLayout.addWidget(self.algorithmTree)

        # Initialize with registry
        registry = QgsApplication.processingRegistry()
        recent_log = _processing_recent_algorithm_log()
        favorite_manager = _processing_favorite_algorithm_manager()

        if recent_log is not None and favorite_manager is not None:
            self.algorithmTree.setRegistry(registry, recent_log, favorite_manager)
        else:
            # Fallback for QGIS < 4.4
            self.algorithmTree.setRegistry(registry)

        # Set filters
        filters = QgsProcessingToolboxProxyModel.Filters(
            QgsProcessingToolboxProxyModel.Filter.FilterToolbox
        )
        self.algorithmTree.setFilters(filters)

        # Set filter string (initially empty)
        self.setFilterString("")

        # Connect signals
        self.searchBox.textChanged.connect(self.setFilterString)
        self.searchBox.returnPressed.connect(self.executeCurrentAlgorithm)
        self.algorithmTree.customContextMenuRequested.connect(self.showPopupMenu)
        self.algorithmTree.doubleClicked.connect(self.executeCurrentAlgorithm)

        # Handle provider changes
        registry.providerAdded.connect(self.providerAdded)
        registry.providerRemoved.connect(self.providerRemoved)

        # Initialize actions and provider buttons
        self.initializeActions()
        self.syncProviderButtons()

    def initializeActions(self):
        """
        Initialize the toolbar actions.

        .. note::
            QGIS 4.4+ has specific actions like history, in-place editing, options.
            For earlier versions, this is a placeholder.
        """

        optionsAction = QAction(QgsApplication.getThemeIcon('mActionOptions.svg'), 'Options', self)
        optionsAction.setObjectName('optionsAction')

        def onShowOptionsDialog():
            from qgis.utils import iface as _iface
            if isinstance(_iface, QgisInterface):
                _iface.showOptionsDialog(self, 'processingOptions')

        optionsAction.triggered.connect(onShowOptionsDialog)

        self._toolbarActions['__options__'] = [optionsAction]
        self.processingToolbar.addAction(optionsAction)

        for provider in QgsApplication.processingRegistry().providers():
            if provider.isActive():
                self.addProviderActions(provider)

    def syncProviderButtons(self):
        """
        Sync provider action buttons.
        """
        # Remove buttons for providers
        for provider in QgsApplication.processingRegistry().providers():
            self.removeProviderActions(provider)

        # Add buttons for active providers
        for provider in QgsApplication.processingRegistry().providers():
            if provider.isActive():
                self.addProviderActions(provider)

    def _findProviderButtons(self) -> list:
        """
        Find all provider action buttons in the toolbar.

        :return: List of QToolButton widgets
        """
        buttons = []
        for action in self._toolbarActions:
            if hasattr(action, 'defaultWidget'):
                widget = action.defaultWidget()
                if isinstance(widget, QToolButton):
                    buttons.append(widget)
        return buttons

    def setFilterString(self, string: str):
        """
        Sets a filter string to filter algorithms in the tree view.

        :param string: Filter string to match against algorithm names
        """
        filters = self.algorithmTree.filters()
        self.algorithmTree.setFilters(filters)
        self.algorithmTree.setFilterString(string)

    def showPopupMenu(self, pos):
        """
        Show a context menu for the selected algorithm.

        :param pos: Position where the menu should be shown
        """
        index = self.algorithmTree.indexAt(pos)
        algorithm = self.algorithmTree.algorithmForIndex(index)
        if algorithm is None:
            return

        menu = QMenu(self)

        executeAction = QAction(
            QCoreApplication.translate("QgsProcessingToolboxDockWidget", "Execute…"), menu
        )
        executeAction.triggered.connect(self.executeCurrentAlgorithm)
        menu.addAction(executeAction)

        menu.exec(self.algorithmTree.mapToGlobal(pos))
        #
        # # Check if algorithm supports batch processing
        # # Use QGIS 4.4+ API if available, otherwise fallback
        # if QGIS_VERSION_INT >= 44000:
        #     flag_supports_batch = algorithm.flags() & QgsProcessingProvider.Flag.FlagSupportsBatch
        # else:
        #     # Fallback for older versions - check if algorithm has batch support
        #     flag_supports_batch = hasattr(algorithm, 'Flag') and \
        #                           algorithm.flags() & QgsProcessingProvider.Flag.FlagSupportsBatch
        #
        # if flag_supports_batch:
        #     executeBatchAction = QAction(
        #         QCoreApplication.translate(
        #             "QgsProcessingToolboxDockWidget", "Execute as Batch Process…"
        #         ),
        #         menu,
        #     )
        #     executeBatchAction.triggered.connect(self.executeCurrentAlgorithmAsBatchProcess)
        #     menu.addAction(executeBatchAction)
        #
        # menu.addSeparator()
        #
        # # Add toolbox context actions
        # registry = _processing_gui_registry()
        # contextActions = []
        # if registry is not None:
        #     contextActions = registry.toolboxContextActions()
        #
        # if contextActions:
        #     menu.addSeparator()
        #
        # for action in contextActions:
        #     action.setData(algorithm, self)
        #     if action.isSeparator():
        #         menu.addSeparator()
        #     elif action.isCompatibleWithAlgorithm(
        #         algorithm.provider().id() if algorithm.provider() else "", algorithm.name()
        #     ):
        #         contextMenuAction = QAction(action.actionName(), menu)
        #         contextMenuAction.setIcon(action.icon())
        #         contextMenuAction.triggered.connect(
        #             lambda checked=False, a=action, alg_name=algorithm.name(),
        #                    prov_id=algorithm.provider().id() if algorithm.provider() else "":
        #             self._executeContextAction(a, alg_name, prov_id)
        #         )
        #         menu.addAction(contextMenuAction)
        #
        # menu.exec(self.algorithmTree.mapToGlobal(pos))

    def _executeContextAction(self, action, algorithmName, providerId):
        """
        Execute a context action.

        :param action: Context action to execute
        :param algorithmName: Name of the algorithm
        :param providerId: ID of the provider
        """
        registry = _processing_gui_registry()
        if registry is None:
            return

        context = registry.createActionContext()
        context.setParentWidget(self)
        context.setAlgorithmName(algorithmName)
        context.setProviderId(providerId)
        action.trigger(context)

    def executeCurrentAlgorithm(self):
        """
        Emit the ID of the currently selected algorithm.
        """
        algorithm = self.algorithmTree.selectedAlgorithm()
        if isinstance(algorithm, QgsProcessingAlgorithm):
            self.executeAlgorithm.emit(algorithm.id())

    def executeCurrentAlgorithmAsBatchProcess(self):
        """
        Execute the currently selected algorithm as a batch process.
        """
        algorithm = self.algorithmTree.selectedAlgorithm()
        if algorithm is None:
            return

        # Create the algorithm instance
        alg_instance = QgsApplication.processingRegistry().createAlgorithmById(algorithm.id())
        if alg_instance:
            # In a full implementation, this would open the batch processing dialog
            # For now, we just create the instance
            pass

    def providerAdded(self, providerId: str):
        """
        Called when a new provider is added.

        :param providerId: ID of the added provider
        """
        provider = QgsApplication.processingRegistry().providerById(providerId)
        if isinstance(provider, QgsProcessingProvider):
            self.addProviderActions(provider)

    def providerRemoved(self, providerId: str):
        """
        Called when a provider is removed.

        :param providerId: ID of the removed provider
        """
        provider = QgsApplication.processingRegistry().providerById(providerId)
        if isinstance(provider, QgsProcessingProvider):
            self.removeProviderActions(provider)

    def removeProviderActions(self, provider: QgsProcessingProvider):

        pid = provider.id()

        if pid in self._toolbarActions:
            actions = self._toolbarActions.pop(pid)
            for a in actions:
                self.processingToolbar.removeAction(a)

        # remove buttons
        if pid in self._provider_buttons:
            self._provider_buttons.pop(pid)

    def addProviderActions(self, provider: QgsProcessingProvider):
        """
        Add actions for a provider to the toolbar.

        :param provider: Processing provider
        """
        registry = _processing_gui_registry()
        if registry is None:
            return

        if hasattr(registry, 'toolboxActionsForProvider'):
            actions = registry.toolboxActionsForProvider(provider.id())
        else:
            from processing.gui.ProviderActions import ProviderActions
            actions = ProviderActions.actions.get(provider.id(), [])

        if len(actions) == 0:
            return

        if provider.id() in self._toolbarActions:
            warnings.warn(f"Provider {provider.id()} already has actions in the toolbar", UserWarning)
            return

        bt = QToolButton()
        bt.setObjectName(f"provideraction_{provider.id()}")
        bt.setIcon(provider.icon())
        bt.setToolTip(provider.name())
        bt.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)

        menu = QMenu(provider.name(), self)
        menu.setObjectName(f"{provider.id()}_menu")

        new_actions = []
        for toolboxAction in actions:
            if isinstance(toolboxAction, QAction):
                action = QAction(toolboxAction.name, menu)
                action.setObjectName(toolboxAction.name)
                action.setData(self)
                action.triggered.connect(toolboxAction.execute)
                menu.addAction(action)
                new_actions.append(action)

        bt.setMenu(menu)
        self._provider_buttons[provider.id()] = bt

        existingActions: List[QAction] = self.processingToolbar.actions()
        insertBeforeAction = None
        foundProviderActions = False

        for a in existingActions:
            if a.isSeparator():
                if foundProviderActions:
                    insertBeforeAction = a
                    break
                else:
                    continue

            if isinstance(a, QWidgetAction):
                foundProviderActions = True
                if tb := a.defaultWidget():
                    if isinstance(tb, QToolButton) and tb.objectName().startswith('provideraction_'):
                        foundProviderActions = True
                        if tb.toolTip().lower() > provider.name().lower():
                            insertBeforeAction = a
                            break
                        else:
                            continue
            insertBeforeAction = a
            break

        if insertBeforeAction and foundProviderActions:
            wa = self.processingToolbar.insertWidget(insertBeforeAction, bt)
        elif insertBeforeAction:
            separatorAction = QAction()
            separatorAction.setSeparator(True)
            self.processingToolbar.insertAction(insertBeforeAction, separatorAction)
            wa = self.processingToolbar.insertWidget(separatorAction, bt)
        else:
            wa = self.processingToolbar.addWidget(bt)
        new_actions.append(wa)
        self._toolbarActions[provider.id()] = new_actions

    def _executeProviderAction(self, action):
        """
        Execute a provider toolbox action.

        :param action: Provider action to execute
        """
        registry = _processing_gui_registry()
        if registry is None:
            return

        context = registry.createActionContext()
        context.setParentWidget(self)
        action.trigger(context)

    def setInPlaceEditMode(self, enabled: bool):
        """
        Set whether to show in-place editing algorithms only.

        :param enabled: True to show in-place algorithms only
        """
        filters = QgsProcessingToolboxProxyModel.Filters(
            QgsProcessingToolboxProxyModel.Filter.FilterToolbox
        )

        settings = QgsSettings()
        if settings.value("Processing/Configuration/SHOW_ALGORITHMS_KNOWN_ISSUES", False, type=bool):
            if QGIS_VERSION_INT >= 44000:
                filters |= QgsProcessingToolboxProxyModel.Filter.FilterShowKnownIssues
            else:
                # Fallback for older versions
                pass

        if enabled:
            if QGIS_VERSION_INT >= 44000:
                filters |= QgsProcessingToolboxProxyModel.Filter.FilterInPlace
            else:
                # Fallback for older versions
                pass

        self.algorithmTree.setFilters(filters)

    def syncInPlaceEditState(self, layer=None):
        """
        Synchronize the in-place edit state with the active layer.

        :param layer: Optional layer to check (defaults to active layer)
        """
        if layer is None:
            # In a real implementation, we would get the active layer from QGIS
            # For now, this is a placeholder
            pass

    def activeLayerChanged(self, layer):
        """
        Handle active layer changes.

        :param layer: The new active layer
        """
        from qgis.core import QgsVectorLayer
        if not isinstance(layer, QgsVectorLayer):
            return
        self.algorithmTree.setInPlaceLayer(layer)
