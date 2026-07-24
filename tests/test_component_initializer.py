#!/usr/bin/env python3

import sys
sys.path.append('./')
sys.path.append('../')
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock

from lib.component_initializer import ComponentInitializer
from lib.port_setup_manager import PortSetupManager
from lib.usersettings import UserSettings


class TestApplyStartupPortSetup(unittest.TestCase):
    """ComponentInitializer.__init__ does a lot of heavy, hardware-adjacent
    construction, so these exercise the new startup-apply logic directly
    against a lightweight duck-typed stand-in bound to the real unbound
    method, instead of constructing a whole ComponentInitializer."""

    def setUp(self):
        config_path = os.path.dirname(os.path.abspath(__file__)) + "/config-test/"
        self.settings_file = config_path + "settings-test-startup-setup.xml"
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)
        self.usersettings = UserSettings(config=self.settings_file, default_config="config/default_settings.xml")

        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.db_path)
        self.psm = PortSetupManager(db_path=self.db_path)

        self.midiports = MagicMock()
        self.fake = SimpleNamespace(port_setup_manager=self.psm, usersettings=self.usersettings,
                                     midiports=self.midiports)

    def tearDown(self):
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.remove(path)

    def _apply_startup(self):
        ComponentInitializer._apply_startup_port_setup(self.fake)

    def test_noop_when_no_setups_exist(self):
        self._apply_startup()
        self.midiports.apply_setup.assert_not_called()

    def test_applies_last_active_setup(self):
        self.psm.create_setup("Piano only", 1, "Roland", "default", "Roland", False)
        synthesia = self.psm.create_setup("Synthesia", 2, "Lenovo", "Roland", "Lenovo", True)
        self.usersettings.change_setting_value("active_port_setup_id", synthesia["id"])

        self._apply_startup()

        self.midiports.apply_setup.assert_called_once_with(synthesia)

    def test_falls_back_to_first_by_priority_when_no_active_id_set(self):
        first = self.psm.create_setup("Piano only", 1, "Roland", "default", "Roland", False)
        self.psm.create_setup("Synthesia", 2, "Lenovo", "Roland", "Lenovo", True)

        self._apply_startup()

        self.midiports.apply_setup.assert_called_once_with(first)

    def test_falls_back_to_first_by_priority_when_active_id_was_deleted(self):
        first = self.psm.create_setup("Piano only", 1, "Roland", "default", "Roland", False)
        deleted = self.psm.create_setup("Synthesia", 2, "Lenovo", "Roland", "Lenovo", True)
        self.usersettings.change_setting_value("active_port_setup_id", deleted["id"])
        self.psm.delete_setup(deleted["id"])

        self._apply_startup()

        self.midiports.apply_setup.assert_called_once_with(first)


if __name__ == '__main__':
    unittest.main()
