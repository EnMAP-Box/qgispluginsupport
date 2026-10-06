#!/usr/bin/env python
# vim: set expandtab tabstop=4 shiftwidth=4:
#

import unittest

from qgis.PyQt.QtCore import QRect, QSize, Qt
from qgis.PyQt.QtGui import QStandardItem, QStandardItemModel, QImage, QPalette, QPainter, QTextDocument
from qgis.PyQt.QtWidgets import QStyleOptionViewItem, QWidget

from qps.externals.htmlwidgets import HTMLCheckBox, HTMLComboBox, HTMLRadioButton, HTMLStyle, HTMLDelegate, \
    HTMLWidgetHelper
from qps.testing import start_app

app = start_app()


def image_is_empty(image: QImage) -> bool:
    """Returns True if all pixels are fully transparent"""
    for x in range(image.width()):
        for y in range(image.height()):
            if image.pixelColor(x, y).alpha() > 0:
                return False
    return True


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

    def test_HTMLStyle_drawItemText_renders_HTML(self):
        style = HTMLStyle()
        image = QImage(200, 40, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            result = style.drawItemText(painter,
                                        QRect(0, 0, 200, 40),
                                        Qt.AlignmentFlag.AlignLeft,
                                        QPalette(),
                                        True,
                                        '<b>Bold &amp; <i>Italic</i></b>',
                                        QPalette.ColorRole.Text)
        finally:
            painter.end()
        self.assertIsNone(result)
        self.assertFalse(image_is_empty(image), 'HTML text was not rendered')
        # the HTML must have been loaded into the internal QTextDocument
        # (QTextDocument.toHtml() normalizes to rich text, <b> becomes font-weight:700)
        html = style.text_doc.toHtml()
        self.assertIn('Bold', html)
        self.assertIn('font-weight:700', html)

    def test_HTMLStyle_drawItemText_plain_text_renders_too(self):
        style = HTMLStyle()
        image = QImage(200, 40, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            style.drawItemText(painter,
                               QRect(0, 0, 200, 40),
                               Qt.AlignmentFlag.AlignLeft,
                               QPalette(),
                               True,
                               'plain text',
                               QPalette.ColorRole.Text)
        finally:
            painter.end()
        self.assertFalse(image_is_empty(image), 'plain text was not rendered')

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

    def test_HTMLDelegate_sizeHint_reflects_HTML_content(self):
        delegate = HTMLDelegate()
        delegate.doc.setHtml('<b>Bold text widens the ideal width</b>')
        size = delegate.sizeHint(None, None)
        self.assertIsInstance(size, QSize)
        self.assertGreater(size.width(), 0, 'HTML content should widen the size hint')

        multiline = HTMLDelegate()
        multiline.doc.setHtml('<p>line 1</p><p>line 2</p><p>line 3</p>')
        size_multiline = multiline.sizeHint(None, None)
        empty = HTMLDelegate().sizeHint(None, None)
        self.assertGreater(size_multiline.height(), empty.height(),
                           'multi-line HTML content should increase the size hint height')

    def test_HTMLDelegate_paint_loads_HTML_from_index(self):
        model = QStandardItemModel()
        item = QStandardItem('<b>Bold</b> and <i>italic</i>')
        model.setItem(0, 0, item)
        index = model.index(0, 0)

        delegate = HTMLDelegate()
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 200, 40)

        image = QImage(200, 40, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            delegate.paint(painter, option, index)
        finally:
            painter.end()

        # paint() must have loaded the index text into the delegate's QTextDocument
        html = delegate.doc.toHtml()
        self.assertIn('bold', html.lower())
        self.assertIn('font-weight:700', html)
        self.assertFalse(image_is_empty(image), 'delegate painted nothing')

    def test_HTMLDelegate_paint_does_not_modify_option_text(self):
        model = QStandardItemModel()
        model.setItem(0, 0, QStandardItem('<b>Bold</b>'))
        index = model.index(0, 0)

        delegate = HTMLDelegate()
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 200, 40)
        option.text = 'caller text must survive'

        image = QImage(200, 40, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)
        painter = QPainter(image)
        try:
            delegate.paint(painter, option, index)
        finally:
            painter.end()
        # paint() clears options.text only on its private copy, never on the caller's option
        self.assertEqual(option.text, 'caller text must survive')

    def test_HTMLCheckBox_init(self):
        checkbox = HTMLCheckBox('Test', None)
        self.assertIsInstance(checkbox, HTMLCheckBox)
        self.assertIsInstance(checkbox, HTMLWidgetHelper)
        self.assertIsNotNone(checkbox.style())

    def test_HTMLCheckBox_uses_HTMLStyle(self):
        checkbox = HTMLCheckBox('<b>Test</b>', None)
        self.assertIsInstance(checkbox.style(), HTMLStyle,
                              'HTMLCheckBox must be styled with HTMLStyle')

    def test_HTMLCheckBox_sizeHint_with_HTML(self):
        plain = HTMLCheckBox('Test', None)
        html = HTMLCheckBox('<b>Test</b>', None)
        self.assertGreaterEqual(html.sizeHint().width(), plain.sizeHint().width())

    def test_HTMLRadioButton_init(self):
        radiobutton = HTMLRadioButton('Test', None)
        self.assertIsInstance(radiobutton, HTMLRadioButton)
        self.assertIsInstance(radiobutton, HTMLWidgetHelper)
        self.assertIsNotNone(radiobutton.style())

    def test_HTMLRadioButton_uses_HTMLStyle(self):
        radiobutton = HTMLRadioButton('<b>Test</b>', None)
        self.assertIsInstance(radiobutton.style(), HTMLStyle,
                              'HTMLRadioButton must be styled with HTMLStyle')

    def test_HTMLComboBox_init(self):
        parent = QWidget()
        combobox = HTMLComboBox(parent)
        self.assertIsInstance(combobox, HTMLComboBox)
        self.assertIsNotNone(combobox.style())
        self.assertIsNotNone(combobox.itemDelegate())

    def test_HTMLComboBox_uses_HTMLStyle_and_HTMLDelegate(self):
        parent = QWidget()
        combobox = HTMLComboBox(parent)
        self.assertIsInstance(combobox.style(), HTMLStyle,
                              'HTMLComboBox must be styled with HTMLStyle')
        delegate = combobox.itemDelegate()
        self.assertIsInstance(delegate, HTMLDelegate,
                              'HTMLComboBox must use an HTMLDelegate as item delegate')

    def test_HTMLComboBox_itemDelegate_paints_HTML(self):
        parent = QWidget()
        combobox = HTMLComboBox(parent)
        combobox.addItem('<b>Item 1</b>')
        delegate = combobox.itemDelegate()
        self.assertIsInstance(delegate, HTMLDelegate)

        index = combobox.model().index(0, 0)
        option = QStyleOptionViewItem()
        option.rect = QRect(0, 0, 200, 40)
        option.widget = combobox

        image = QImage(200, 40, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            delegate.paint(painter, option, index)
        finally:
            painter.end()
        self.assertIn('Item 1', delegate.doc.toHtml())
        self.assertFalse(image_is_empty(image))

    def test_HTMLComboBox_sizeHint(self):
        parent = QWidget()
        combobox = HTMLComboBox(parent)
        combobox.addItem('Item 1')
        combobox.addItem('Item 2')
        size = combobox.sizeHint()
        self.assertIsInstance(size, QSize)
        self.assertGreater(size.width(), 0)
        self.assertGreater(size.height(), 0)

    def test_HTMLComboBox_sizeHint_accounts_for_HTML(self):
        parent = QWidget()
        plain = HTMLComboBox(parent)
        plain.addItem('Item')

        rich = HTMLComboBox(parent)
        rich.addItem('<b>Item</b>')

        # rich text may not be wider, but must at least be a valid, non-shrinking size
        self.assertGreaterEqual(rich.sizeHint().width(), plain.sizeHint().width())
        self.assertGreater(rich.sizeHint().height(), 0)
        # sizeHint is cached after first computation
        self.assertEqual(rich.sizeHint(), rich.stored_size)

    def test_HTMLComboBox_minimumSizeHint(self):
        parent = QWidget()
        combobox = HTMLComboBox(parent)
        combobox.addItem('Item 1')
        size = combobox.minimumSizeHint()
        self.assertIsInstance(size, QSize)

    def test_HTMLComboBox_minimumSizeHint_matches_sizeHint(self):
        parent = QWidget()
        combobox = HTMLComboBox(parent)
        combobox.addItem('Item 1')
        self.assertEqual(combobox.minimumSizeHint(), combobox.sizeHint())


if __name__ == '__main__':
    unittest.main()
