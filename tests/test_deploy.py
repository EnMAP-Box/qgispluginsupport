import unittest

from qgis.core import QgsUserProfileManager
from qps.make.deploy import userProfileManager


class QgsDeployTests(unittest.TestCase):

    def test_profileManager(self):
        manager = userProfileManager()
        self.assertIsInstance(manager, QgsUserProfileManager)
        name = manager.defaultProfileName()
        self.assertTrue(name not in [None, ''])
