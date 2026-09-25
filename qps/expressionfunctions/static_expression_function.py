from typing import Any, Callable, Set, Union

from qgis.core import QgsExpression, QgsExpressionContext, QgsExpressionFunction, \
    QgsExpressionNode, QgsExpressionNodeFunction


class StaticExpressionFunction(QgsExpressionFunction):
    """
    A Re-Implementation of QgsStaticExpressionFunction (not available in python API)
    """

    def __init__(self,
                 fnname: str,
                 params,
                 fcn,
                 group: str,
                 helpText: str = None,
                 usesGeometry: Union[bool, QgsExpressionNodeFunction] = None,
                 referencedColumns: Set[str] = None,
                 lazyEval: bool = False,
                 aliases: list = [],
                 handlesNull: bool = False):
        from .helpers import HelpStringMaker
        HM = HelpStringMaker()
        if helpText is None:
            helpText = HM.helpText(fnname, params)
        if helpText is None:
            helpText = ''
        super().__init__(fnname, params, group, helpText, lazyEval, handlesNull, False)

        self.mFnc = fcn
        self.mAliases = aliases
        self.mUsesGeometry = False
        self.mUsesGeometryFunc = None

        if usesGeometry is not None:
            if isinstance(usesGeometry, (bool, int)):
                self.mUsesGeometry = bool(usesGeometry)
            else:
                self.mUsesGeometryFunc = usesGeometry

        self.mReferencedColumnsFunc = referencedColumns
        self.mIsStatic = False
        self.mIsStaticFunc = None
        self.mPrepareFunc = None

    def aliases(self) -> list:
        return self.mAliases

    def usesGeometry(self, node: QgsExpressionNodeFunction) -> bool:
        if self.mUsesGeometryFunc:
            return self.mUsesGeometryFunc(node)
        else:
            return self.mUsesGeometry

    def referencedColumns(self, node: QgsExpressionNodeFunction) -> Set[str]:
        if self.mReferencedColumnsFunc:
            return self.mReferencedColumnsFunc(node)
        else:
            return super().referencedColumns(node)

    def isStatic(self,
                 node: QgsExpressionNodeFunction,
                 parent,
                 context: QgsExpressionContext) -> bool:
        if self.mIsStaticFunc:
            return self.mIsStaticFunc(node, parent, context)
        else:
            return super().isStatic(node, parent, context)

    def prepare(self, node: QgsExpressionNodeFunction, parent, context: QgsExpressionContext) -> bool:
        if self.mPrepareFunc:
            return self.mPrepareFunc(node, parent, context)
        else:
            return True

    def setIsStaticFunction(self,
                            isStatic: Callable[[QgsExpressionFunction, QgsExpression, QgsExpressionContext], bool]):
        self.mIsStaticFunc = isStatic

    def setIsStatic(self, isStatic: bool):
        self.mIsStaticFunc = None
        self.mIsStatic = isStatic

    def setPrepareFunction(self,
                           prepareFunc: Callable[[QgsExpressionFunction, QgsExpression, QgsExpressionContext], bool]):
        self.mPrepareFunc = prepareFunc

    @staticmethod
    def allParamsStatic(node: QgsExpressionNodeFunction, parent, context: QgsExpressionContext) -> bool:
        if node:
            for argNode in node.args():
                argNode: QgsExpressionNode
                if not argNode.isStatic(parent, context):
                    return False
        return True

    def func(self,
             values: list,
             context: QgsExpressionContext,
             parent,
             node: QgsExpressionNodeFunction) -> Any:
        if self.mFnc:
            r = self.mFnc(values, context, parent, node)
            return r
        else:
            from qgis.PyQt.QtCore import NULL
            return NULL
