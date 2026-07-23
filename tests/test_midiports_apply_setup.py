#!/usr/bin/env python3

import sys
sys.path.append('./')
sys.path.append('../')
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from lib.usersettings import UserSettings
from lib import midiports as midiports_module
from lib import connectall as connectall_module
from lib.port_setup_manager import PortSetupManager


class FakeMenu:
    """No-op stand-in for MenuLCD, so tests don't touch a real LCD driver."""

    def __init__(self):
        self.messages = []

    def render_message(self, title, message, delay=500):
        self.messages.append((title, message))

    def show(self):
        pass


class TestMidiPortsApplySetup(unittest.TestCase):
    def setUp(self):
        # Module-level mido port-name cache must be reset so our mido patches take effect
        midiports_module._cached_input_names = None
        midiports_module._cached_output_names = None

        config_path = os.path.dirname(os.path.abspath(__file__)) + "/config-test/"
        self.settings_file = config_path + "settings-test-ports.xml"
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)

        self.patchers = [
            patch.object(midiports_module.mido, 'open_input'),
            patch.object(midiports_module.mido, 'open_output'),
            patch.object(midiports_module.mido, 'get_input_names', return_value=[]),
            patch.object(midiports_module.mido, 'get_output_names', return_value=[]),
            patch.object(connectall_module, 'connectall'),
        ]
        (self.mock_open_input, self.mock_open_output,
         _, _, self.mock_connectall) = [p.start() for p in self.patchers]
        self.mock_open_input.return_value = MagicMock()
        self.mock_open_output.return_value = MagicMock()

        # Real project default_settings.xml already has input_port/secondary_input_port/
        # play_port/active_port_setup_id, so it doubles as a realistic test fixture.
        self.usersettings = UserSettings(config=self.settings_file, default_config="config/default_settings.xml")

        self.midiports = midiports_module.MidiPorts(self.usersettings)
        self.menu = FakeMenu()
        self.midiports.menu = self.menu

        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.db_path)
        self.psm = PortSetupManager(db_path=self.db_path)

    def tearDown(self):
        for p in self.patchers:
            p.stop()
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_apply_setup_opens_ports_and_persists_active_id(self):
        setup = {"id": 7, "name": "Synthesia", "input_port": "Lenovo",
                 "secondary_input_port": "Roland", "play_port": "Lenovo", "auto_connect": True}

        result = self.midiports.apply_setup(setup)

        self.assertTrue(result)
        self.mock_open_input.assert_called_with("Lenovo", callback=self.midiports.msg_callback)
        self.mock_open_output.assert_called_with("Lenovo")
        self.assertEqual(self.usersettings.get_setting_value("secondary_input_port"), "Roland")
        self.assertEqual(self.usersettings.get_setting_value("active_port_setup_id"), "7")
        self.mock_connectall.assert_called_once()
        # One combined LCD message, not one per changed port
        self.assertEqual(len(self.menu.messages), 1)

    def test_apply_setup_skips_connectall_when_auto_connect_false(self):
        setup = {"id": 3, "name": "Piano only", "input_port": "Roland",
                 "secondary_input_port": "default", "play_port": "Roland", "auto_connect": False}

        self.midiports.apply_setup(setup)

        self.mock_connectall.assert_not_called()

    def test_cycle_port_setup_returns_none_with_zero_setups(self):
        self.assertIsNone(self.midiports.cycle_port_setup(self.psm))

    def test_cycle_port_setup_advances_and_persists_across_calls(self):
        self.psm.create_setup("A", 2, "Roland", "default", "Roland", False)
        self.psm.create_setup("B", 9, "Lenovo", "Roland", "Lenovo", True)

        first = self.midiports.cycle_port_setup(self.psm)
        self.assertEqual(first["name"], "A")

        # Each call re-reads active_port_setup_id from usersettings, simulating
        # cycling continuing correctly after a restart
        second = self.midiports.cycle_port_setup(self.psm)
        self.assertEqual(second["name"], "B")

        third = self.midiports.cycle_port_setup(self.psm)
        self.assertEqual(third["name"], "A")


if __name__ == '__main__':
    unittest.main()
