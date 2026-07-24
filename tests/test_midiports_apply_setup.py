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

    def render_message(self, title, message, delay=500, level="info"):
        self.messages.append((title, message, level))

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
            patch.object(connectall_module, 'apply_custom_connections'),
        ]
        (self.mock_open_input, self.mock_open_output,
         _, _, self.mock_connectall, self.mock_apply_custom_connections) = [p.start() for p in self.patchers]
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
        self.assertEqual(self.menu.messages[0][2], "success")

    def test_apply_setup_skips_connectall_when_auto_connect_false(self):
        setup = {"id": 3, "name": "Piano only", "input_port": "Roland",
                 "secondary_input_port": "default", "play_port": "Roland", "auto_connect": False}

        self.midiports.apply_setup(setup)

        self.mock_connectall.assert_not_called()
        self.mock_apply_custom_connections.assert_not_called()

    def test_apply_setup_restores_extra_connections_when_auto_connect_true(self):
        extra = [{"source_client": "Lenovo Tab P11", "source_port": "Lenovo Tab P11 MIDI 1",
                  "dest_client": "Roland Digital Piano", "dest_port": "Roland Digital Piano MIDI 1"}]
        setup = {"id": 7, "name": "Synthesia", "input_port": "Lenovo",
                 "secondary_input_port": "Roland", "play_port": "Lenovo", "auto_connect": True,
                 "extra_connections": extra}

        self.midiports.apply_setup(setup)

        # input_port/secondary_input_port resolve unchanged here (mido's port
        # list is mocked empty), so the connectall-managed pair is exactly
        # ("Lenovo", "Roland") - it must be passed through so the cleanup
        # pass in apply_custom_connections never undoes this bridge.
        self.mock_apply_custom_connections.assert_called_once_with(extra, managed_pair=("Lenovo", "Roland"))

    def test_apply_setup_shows_error_level_message_on_failure(self):
        setup = {"id": 4, "name": "Synthesia", "input_port": "Roland",
                 "secondary_input_port": "Lenovo", "play_port": "Roland", "auto_connect": True}
        self.mock_connectall.side_effect = Exception("aconnect failed")

        result = self.midiports.apply_setup(setup)

        self.assertFalse(result)
        self.assertEqual(len(self.menu.messages), 1)
        self.assertEqual(self.menu.messages[0][2], "error")

    def test_apply_setup_resolves_stale_client_port_id(self):
        # Setup was saved when the Roland's ALSA client:port ID was "20:0";
        # since then the device was replugged and now enumerates as "24:0".
        stale_input = "Roland Digital Piano:Roland Digital Piano MIDI 1 20:0"
        current_input = "Roland Digital Piano:Roland Digital Piano MIDI 1 24:0"
        stale_output = "Lenovo Tab:Lenovo Tab MIDI 1 18:0"
        current_output = "Lenovo Tab:Lenovo Tab MIDI 1 30:0"

        midiports_module.mido.get_input_names.return_value = [current_input]
        midiports_module.mido.get_output_names.return_value = [current_output]

        setup = {"id": 5, "name": "Synthesia", "input_port": stale_input,
                 "secondary_input_port": "default", "play_port": stale_output, "auto_connect": False}

        result = self.midiports.apply_setup(setup)

        self.assertTrue(result)
        self.mock_open_input.assert_called_with(current_input, callback=self.midiports.msg_callback)
        self.mock_open_output.assert_called_with(current_output)
        self.assertEqual(self.usersettings.get_setting_value("input_port"), current_input)
        self.assertEqual(self.usersettings.get_setting_value("play_port"), current_output)

    def test_apply_setup_keeps_stale_name_when_device_absent(self):
        # Device genuinely not connected: no available port matches by name,
        # so the saved name passes through unchanged and the normal
        # open-failure path in change_port handles it (no crash).
        midiports_module.mido.get_input_names.return_value = ["Some Other Device:Some Other Device MIDI 1 12:0"]
        midiports_module.mido.open_input.side_effect = Exception("port not found")

        setup = {"id": 6, "name": "Synthesia", "input_port": "Roland Digital Piano:Roland Digital Piano MIDI 1 20:0",
                 "secondary_input_port": "default", "play_port": "default", "auto_connect": False}

        result = self.midiports.apply_setup(setup)

        # apply_setup itself doesn't raise (change_port swallows the mido error internally)
        self.assertTrue(result)
        self.mock_open_input.assert_called_with(
            "Roland Digital Piano:Roland Digital Piano MIDI 1 20:0", callback=self.midiports.msg_callback)

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

    def test_connectall_reapplies_active_setup_extra_connections(self):
        # Simulates hotplug reconnection (auto_reconnect_loop -> MidiPorts.
        # connectall()): the active Setup's custom wiring must be re-asserted
        # too, not just the plain input/secondary bridge - otherwise whatever
        # else grabbed the port in the meantime (e.g. rtpmidid auto-wiring
        # itself to newly-appeared hardware) is left connected instead.
        extra = [{"source_client": "Roland Digital Piano", "source_port": "Roland Digital Piano MIDI 1",
                  "dest_client": "Lenovo Tab P11", "dest_port": "Lenovo Tab P11 MIDI 1"}]
        setup = self.psm.create_setup("Synthesia", 1, "Lenovo", "Roland", "Lenovo", True,
                                       extra_connections=extra)
        self.usersettings.change_setting_value("active_port_setup_id", setup["id"])
        self.usersettings.change_setting_value("input_port", "Lenovo")
        self.usersettings.change_setting_value("secondary_input_port", "Roland")
        self.midiports.port_setup_manager = self.psm

        self.midiports.connectall()

        self.mock_apply_custom_connections.assert_called_once_with(extra, managed_pair=("Lenovo", "Roland"))

    def test_connectall_noop_without_port_setup_manager(self):
        self.midiports.connectall()
        self.mock_apply_custom_connections.assert_not_called()

    def test_connectall_noop_when_active_setup_auto_connect_false(self):
        setup = self.psm.create_setup("Piano only", 1, "Roland", "default", "Roland", False)
        self.usersettings.change_setting_value("active_port_setup_id", setup["id"])
        self.midiports.port_setup_manager = self.psm

        self.midiports.connectall()

        self.mock_apply_custom_connections.assert_not_called()

    def test_connectall_noop_when_no_active_setup_id(self):
        self.midiports.port_setup_manager = self.psm

        self.midiports.connectall()

        self.mock_apply_custom_connections.assert_not_called()


if __name__ == '__main__':
    unittest.main()
