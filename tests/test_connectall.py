#!/usr/bin/env python3

import sys
sys.path.append('./')
sys.path.append('../')
import unittest
from unittest.mock import patch, MagicMock

from lib import connectall


# Roland <-> Lenovo is a real, manually-drawn connection. Everything else here
# is automatic plumbing ALSA/mido/rtpmidid create on their own: the System
# timer, the Midi Through virtual port, the per-process RtMidiIn/RtMidiOut
# clients mido spins up whenever it opens a port, and rtpmidid auto-exporting
# Lenovo over the network on its own - none of it was drawn by the user.
ACONNECT_L_SAMPLE = """client 0: 'System' [type=kernel]
    0 'Timer           '
    1 'Announce        '
client 14: 'Midi Through' [type=kernel]
    0 'Midi Through Port-0'
\tConnecting To: 128:0
client 20: 'Roland Digital Piano' [type=kernel,card=1]
    0 'Roland Digital Piano MIDI 1'
\tConnecting To: 130:0
client 24: 'Lenovo Tab P11' [type=kernel,card=2]
    0 'Lenovo Tab P11 MIDI 1'
\tConnecting To: 128:0
\tConnected From: 128:0
client 128: 'rtpmidid' [type=user]
    0 'Network Export  '
\tConnecting To: 24:0, 14:0
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

    def test_internal_clients_excluded_from_names(self):
        id_to_name, _links = connectall._parse_client_ports_and_links(ACONNECT_L_SAMPLE)

        self.assertNotIn("0:0", id_to_name)
        self.assertNotIn("14:0", id_to_name)
        self.assertNotIn("128:0", id_to_name)  # rtpmidid - auto-manages its own connections
        self.assertNotIn("129:0", id_to_name)
        self.assertNotIn("130:0", id_to_name)

    def test_links_touching_an_internal_client_on_either_end_are_dropped(self):
        # Roland's only live link is to RtMidiIn (130:0) and Lenovo's only
        # live link is to rtpmidid (128:0) - both must vanish, even though
        # each source (Roland/Lenovo) is itself a perfectly real device.
        _id_to_name, links = connectall._parse_client_ports_and_links(ACONNECT_L_SAMPLE)

        self.assertEqual(links, [])

    def test_empty_output_yields_nothing(self):
        id_to_name, links = connectall._parse_client_ports_and_links("")
        self.assertEqual(id_to_name, {})
        self.assertEqual(links, [])


class TestCaptureCustomConnections(unittest.TestCase):
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_SAMPLE)
    def test_captures_nothing_when_only_automatic_plumbing_is_live(self, _mock):
        # In this fixture Roland and Lenovo aren't wired to each other at all
        # yet - only to internal clients - so there's nothing real to capture.
        self.assertEqual(connectall.capture_custom_connections(), [])

    @patch.object(connectall.subprocess, "check_output", side_effect=Exception("no aconnect"))
    def test_returns_empty_list_when_aconnect_unavailable(self, _mock):
        self.assertEqual(connectall.capture_custom_connections(), [])


ACONNECT_L_WITH_MANUAL_LINK = ACONNECT_L_SAMPLE.replace(
    "client 20: 'Roland Digital Piano' [type=kernel,card=1]\n"
    "    0 'Roland Digital Piano MIDI 1'\n"
    "\tConnecting To: 130:0\n",
    "client 20: 'Roland Digital Piano' [type=kernel,card=1]\n"
    "    0 'Roland Digital Piano MIDI 1'\n"
    "\tConnecting To: 24:0, 130:0\n",
).replace(
    "client 24: 'Lenovo Tab P11' [type=kernel,card=2]\n"
    "    0 'Lenovo Tab P11 MIDI 1'\n"
    "\tConnecting To: 128:0\n"
    "\tConnected From: 128:0\n",
    "client 24: 'Lenovo Tab P11' [type=kernel,card=2]\n"
    "    0 'Lenovo Tab P11 MIDI 1'\n"
    "\tConnecting To: 20:0, 128:0\n"
    "\tConnected From: 128:0\n",
)


class TestCaptureCustomConnectionsWithManualLink(unittest.TestCase):
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_WITH_MANUAL_LINK)
    def test_captures_only_the_real_manual_connection(self, _mock):
        conns = connectall.capture_custom_connections()
        # Roland<->Lenovo is bidirectional (two distinct one-way aconnect
        # links); the rtpmidid/RtMidi/Midi Through plumbing is excluded.
        self.assertEqual(len(conns), 2)
        self.assertIn({
            "source_client": "Roland Digital Piano", "source_port": "Roland Digital Piano MIDI 1",
            "dest_client": "Lenovo Tab P11", "dest_port": "Lenovo Tab P11 MIDI 1",
        }, conns)
        self.assertIn({
            "source_client": "Lenovo Tab P11", "source_port": "Lenovo Tab P11 MIDI 1",
            "dest_client": "Roland Digital Piano", "dest_port": "Roland Digital Piano MIDI 1",
        }, conns)


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
    def test_never_disconnects_rtpmidids_own_auto_export_link(self, _mock_output, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Regression for the reported bug: Lenovo is currently only wired to
        # rtpmidid (its automatic network-export peer). Applying an empty
        # wanted list must never touch that link - rtpmidid reacts to losing
        # it by tearing down and rebuilding its own listener, which can race
        # with (and clobber) whatever this call establishes.
        connectall.apply_custom_connections([])

        # rtpmidid's link to Lenovo is filtered out at parse time already, so
        # there's nothing real live and nothing wanted - no aconnect call at all.
        mock_run.assert_not_called()

    @patch.object(connectall.subprocess, "run")
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_WITH_MANUAL_LINK)
    def test_disconnects_live_connections_not_in_the_wanted_list(self, _mock_output, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")

        # Applying an empty list means "this setup wants no custom wiring" -
        # the live Roland<->Lenovo connection must be torn down (rtpmidid's
        # own link to Lenovo must still be left alone).
        connectall.apply_custom_connections([])

        mock_run.assert_any_call(["aconnect", "-d", "20:0", "24:0"], capture_output=True, text=True)
        mock_run.assert_any_call(["aconnect", "-d", "24:0", "20:0"], capture_output=True, text=True)
        for call in mock_run.call_args_list:
            self.assertNotIn("128:0", call.args[0])

    @patch.object(connectall.subprocess, "run")
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_WITH_MANUAL_LINK)
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
