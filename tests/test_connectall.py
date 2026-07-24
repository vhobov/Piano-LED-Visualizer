#!/usr/bin/env python3

import sys
sys.path.append('./')
sys.path.append('../')
import unittest
from unittest.mock import patch, MagicMock

from lib import connectall


# Roland <-> Lenovo is a real, manually-drawn connection. Everything else here
# is the automatic plumbing ALSA/mido create on their own (System timer, the
# Midi Through virtual port, and the per-process RtMidiIn/RtMidiOut clients
# mido spins up whenever it opens a port) - none of it was drawn by the user.
ACONNECT_L_SAMPLE = """client 0: 'System' [type=kernel]
    0 'Timer           '
    1 'Announce        '
client 14: 'Midi Through' [type=kernel]
    0 'Midi Through Port-0'
\tConnecting To: 128:0
client 20: 'Roland Digital Piano' [type=kernel,card=1]
    0 'Roland Digital Piano MIDI 1'
\tConnecting To: 24:0, 130:0
client 24: 'Lenovo Tab P11' [type=kernel,card=2]
    0 'Lenovo Tab P11 MIDI 1'
\tConnecting To: 20:0
client 128: 'rtpmidid' [type=user]
    0 'Network Export  '
\tConnecting To: 14:0
client 129: 'RtMidiOut Client' [type=user]
    0 'RtMidi output   '
\tConnecting To: 20:0
client 130: 'RtMidiIn Client' [type=user]
    0 'RtMidi input    '
"""


class TestParseClientPortsAndLinks(unittest.TestCase):
    def test_parses_names_for_real_devices_only(self):
        id_to_name, _links = connectall._parse_client_ports_and_links(ACONNECT_L_SAMPLE)

        self.assertEqual(id_to_name["20:0"], ("Roland Digital Piano", "Roland Digital Piano MIDI 1"))
        self.assertEqual(id_to_name["24:0"], ("Lenovo Tab P11", "Lenovo Tab P11 MIDI 1"))
        self.assertEqual(id_to_name["128:0"], ("rtpmidid", "Network Export  "))

    def test_internal_clients_excluded_from_names(self):
        id_to_name, _links = connectall._parse_client_ports_and_links(ACONNECT_L_SAMPLE)

        self.assertNotIn("0:0", id_to_name)
        self.assertNotIn("14:0", id_to_name)
        self.assertNotIn("129:0", id_to_name)
        self.assertNotIn("130:0", id_to_name)

    def test_empty_output_yields_nothing(self):
        id_to_name, links = connectall._parse_client_ports_and_links("")
        self.assertEqual(id_to_name, {})
        self.assertEqual(links, [])


class TestCaptureCustomConnections(unittest.TestCase):
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_SAMPLE)
    def test_captures_only_the_real_manual_connection(self, _mock):
        conns = connectall.capture_custom_connections()
        # Roland<->Lenovo is bidirectional (two distinct one-way aconnect
        # links), everything touching an internal client is excluded.
        self.assertEqual(len(conns), 2)
        self.assertIn({
            "source_client": "Roland Digital Piano", "source_port": "Roland Digital Piano MIDI 1",
            "dest_client": "Lenovo Tab P11", "dest_port": "Lenovo Tab P11 MIDI 1",
        }, conns)
        self.assertIn({
            "source_client": "Lenovo Tab P11", "source_port": "Lenovo Tab P11 MIDI 1",
            "dest_client": "Roland Digital Piano", "dest_port": "Roland Digital Piano MIDI 1",
        }, conns)

    @patch.object(connectall.subprocess, "check_output", side_effect=Exception("no aconnect"))
    def test_returns_empty_list_when_aconnect_unavailable(self, _mock):
        self.assertEqual(connectall.capture_custom_connections(), [])


class TestApplyCustomConnections(unittest.TestCase):
    @patch.object(connectall.subprocess, "run")
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_SAMPLE)
    def test_resolves_stale_ids_and_reconnects_by_name(self, _mock_output, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        connections = [{"source_client": "Roland Digital Piano", "source_port": "Roland Digital Piano MIDI 1",
                        "dest_client": "Lenovo Tab P11", "dest_port": "Lenovo Tab P11 MIDI 1"}]

        connectall.apply_custom_connections(connections)

        mock_run.assert_any_call(["aconnect", "20:0", "24:0"], capture_output=True, text=True)

    @patch.object(connectall.subprocess, "run")
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_SAMPLE)
    def test_skips_connection_when_device_not_currently_present(self, _mock_output, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        connections = [{"source_client": "Missing Device", "source_port": "Missing Device MIDI 1",
                        "dest_client": "Lenovo Tab P11", "dest_port": "Lenovo Tab P11 MIDI 1"}]

        connectall.apply_custom_connections(connections)

        # An unresolvable endpoint never reaches the (re)connect loop - it's
        # simply left out of the wanted set, not passed to aconnect as-is.
        connect_calls = [c.args[0] for c in mock_run.call_args_list if "-d" not in c.args[0]]
        self.assertEqual(connect_calls, [])

    @patch.object(connectall.subprocess, "run")
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_SAMPLE)
    def test_disconnects_live_connections_not_in_the_wanted_list(self, _mock_output, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Applying an empty list means "this setup wants no custom wiring" -
        # the live Roland<->Lenovo connection must be torn down.
        connectall.apply_custom_connections([])

        mock_run.assert_any_call(["aconnect", "-d", "20:0", "24:0"], capture_output=True, text=True)
        mock_run.assert_any_call(["aconnect", "-d", "24:0", "20:0"], capture_output=True, text=True)

    @patch.object(connectall.subprocess, "run")
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_SAMPLE)
    def test_managed_pair_is_never_disconnected(self, _mock_output, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Same empty-list scenario, but 20:0<->24:0 is the connectall()
        # input/secondary bridge this call must not touch.
        connectall.apply_custom_connections([], managed_pair=("20:0", "24:0"))

        for call in mock_run.call_args_list:
            self.assertNotEqual(call.args[0], ["aconnect", "-d", "20:0", "24:0"])
            self.assertNotEqual(call.args[0], ["aconnect", "-d", "24:0", "20:0"])


if __name__ == '__main__':
    unittest.main()
