#!/usr/bin/env python3

import sys
sys.path.append('./')
sys.path.append('../')
import os
import unittest

from lib.usersettings import UserSettings
from lib.ledsettings import LedSettings


class TestLedSettingsSequenceActive(unittest.TestCase):
    """Regression test: get_setting_value() always returns a string (XML text),
    and any non-empty string (including "False") is truthy in Python. KEY3's
    `if self.ledsettings.sequence_active:` check in gpio_handler.py relies on
    this being a real bool, or it stays permanently truthy after every restart
    for anyone who never touches the LED Sequences feature - silently blocking
    the port-setup-cycling button."""

    def setUp(self):
        self.settings_file = os.path.dirname(os.path.abspath(__file__)) + "/config-test/settings-test-ledsettings.xml"
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)

    def tearDown(self):
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)

    def test_sequence_active_loads_as_real_bool_not_truthy_string(self):
        usersettings = UserSettings(config=self.settings_file, default_config="config/default_settings.xml")
        ledsettings = LedSettings(usersettings)

        self.assertIs(ledsettings.sequence_active, False)
        self.assertFalse(ledsettings.sequence_active)


if __name__ == '__main__':
    unittest.main()
