#!/usr/bin/env python
# vim: set expandtab tabstop=4 shiftwidth=4:
#

import unittest

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QTextDocument
from qgis.PyQt.QtWidgets import QWidget

from qps.externals.htmlwidgets import HTMLCheckBox, HTMLComboBox, HTMLRadioButton, HTMLStyle, HTMLDelegate, \
    HTMLWidgetHelper
from qps.testing import start_app

app = start_app()


class TestHTMLWidgets(unittest.TestCase):

    def test_HTMLStyle_init(self):
        style = HTMLStyle()
        self.assertIsInstance(style, HTMLStyle)
        self.assertIsInstance(style.text_doc, QTextDocument)

    def test_HTMLStyle_drawItemText_empty_text(self):
        style = HTMLStyle()
        painter = None
        rect = None
        alignment = None
        pal = None
        enabled = None
        text = ''
        text_role = None
        self.assertIsNone(style.drawItemText(painter, rect, alignment, pal, enabled, text, text_role))

    def test_HTMLStyle_drawItemText_none_text(self):
        style = HTMLStyle()
        painter = None
        rect = None
        alignment = None
        pal = None
        enabled = None
        text = None
        text_role = None
        self.assertIsNone(style.drawItemText(painter, rect, alignment, pal, enabled, text, text_role))

    def test_HTMLDelegate_init(self):
        delegate = HTMLDelegate()
        self.assertIsInstance(delegate, HTMLDelegate)
        self.assertIsInstance(delegate.doc, QTextDocument)

    def test_HTMLDelegate_sizeHint(self):
        delegate = HTMLDelegate()
        option = None
        index = None
        result = delegate.sizeHint(option, index)
        self.assertIsInstance(result, QSize)

    def test_HTMLCheckBox_init(self):
        checkbox = HTMLCheckBox('Test', None)
        self.assertIsInstance(checkbox, HTMLCheckBox)
        self.assertIsInstance(checkbox, HTMLWidgetHelper)
        self.assertIsNotNone(checkbox.style())

    def test_HTMLRadioButton_init(self):
        radiobutton = HTMLRadioButton('Test', None)
        self.assertIsInstance(radiobutton, HTMLRadioButton)
        self.assertIsInstance(radiobutton, HTMLWidgetHelper)
        self.assertIsNotNone(radiobutton.style())

    def test_HTMLComboBox_init(self):
        parent = QWidget()
        combobox = HTMLComboBox(parent)
        self.assertIsInstance(combobox, HTMLComboBox)
        self.assertIsNotNone(combobox.style())
        self.assertIsNotNone(combobox.itemDelegate())

    def test_HTMLComboBox_sizeHint(self):
        parent = QWidget()
        combobox = HTMLComboBox(parent)
        combobox.addItem('Item 1')
        combobox.addItem('Item 2')
        size = combobox.sizeHint()
        self.assertIsInstance(size, QSize)
        self.assertGreater(size.width(), 0)
        self.assertGreater(size.height(), 0)

    def test_HTMLComboBox_minimumSizeHint(self):
        parent = QWidget()
        combobox = HTMLComboBox(parent)
        combobox.addItem('Item 1')
        size = combobox.minimumSizeHint()
        self.assertIsInstance(size, QSize)


if __name__ == '__main__':
    unittest.main()
