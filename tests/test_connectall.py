#!/usr/bin/env python3

import sys
sys.path.append('./')
sys.path.append('../')
import unittest
from unittest.mock import patch, MagicMock

from lib import connectall


ACONNECT_L_SAMPLE = """client 0: 'System' [type=kernel]
    0 'Timer           '
    1 'Announce        '
client 14: 'Midi Through' [type=kernel]
    0 'Midi Through Port-0'
client 20: 'Roland Digital Piano' [type=kernel,card=1]
    0 'Roland Digital Piano MIDI 1'
\tConnecting To: 24:0
client 24: 'Lenovo Tab P11' [type=kernel,card=2]
    0 'Lenovo Tab P11 MIDI 1'
\tConnecting To: 20:0
"""


class TestParseClientPortsAndLinks(unittest.TestCase):
    def test_parses_names_and_links(self):
        id_to_name, links = connectall._parse_client_ports_and_links(ACONNECT_L_SAMPLE)

        self.assertEqual(id_to_name["20:0"], ("Roland Digital Piano", "Roland Digital Piano MIDI 1"))
        self.assertEqual(id_to_name["24:0"], ("Lenovo Tab P11", "Lenovo Tab P11 MIDI 1"))
        self.assertIn(("20:0", "24:0"), links)
        self.assertIn(("24:0", "20:0"), links)

    def test_empty_output_yields_nothing(self):
        id_to_name, links = connectall._parse_client_ports_and_links("")
        self.assertEqual(id_to_name, {})
        self.assertEqual(links, [])


class TestCaptureCustomConnections(unittest.TestCase):
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_SAMPLE)
    def test_captures_live_connection_by_descriptive_name(self, _mock):
        conns = connectall.capture_custom_connections()
        # The sample wires both directions (20:0->24:0 and 24:0->20:0), each a
        # distinct one-way aconnect link, so both are captured separately.
        self.assertEqual(len(conns), 2)
        self.assertIn({
            "source_client": "Roland Digital Piano", "source_port": "Roland Digital Piano MIDI 1",
            "dest_client": "Lenovo Tab P11", "dest_port": "Lenovo Tab P11 MIDI 1",
        }, conns)
        self.assertIn({
            "source_client": "Lenovo Tab P11", "source_port": "Lenovo Tab P11 MIDI 1",
            "dest_client": "Roland Digital Piano", "dest_port": "Roland Digital Piano MIDI 1",
        }, conns)

    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_SAMPLE)
    def test_exclude_pairs_filters_out_the_connectall_bridge(self, _mock):
        conns = connectall.capture_custom_connections(exclude_pairs=[("20:0", "24:0")])
        self.assertEqual(conns, [])

    @patch.object(connectall.subprocess, "check_output", side_effect=Exception("no aconnect"))
    def test_returns_empty_list_when_aconnect_unavailable(self, _mock):
        self.assertEqual(connectall.capture_custom_connections(), [])


class TestApplyCustomConnections(unittest.TestCase):
    def test_noop_on_empty_list(self):
        with patch.object(connectall.subprocess, "check_output") as mock_output:
            connectall.apply_custom_connections([])
            mock_output.assert_not_called()

    @patch.object(connectall.subprocess, "run")
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_SAMPLE)
    def test_resolves_stale_ids_and_reconnects_by_name(self, _mock_output, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stderr="")
        connections = [{"source_client": "Roland Digital Piano", "source_port": "Roland Digital Piano MIDI 1",
                        "dest_client": "Lenovo Tab P11", "dest_port": "Lenovo Tab P11 MIDI 1"}]

        connectall.apply_custom_connections(connections)

        mock_run.assert_called_once_with(["aconnect", "20:0", "24:0"], capture_output=True, text=True)

    @patch.object(connectall.subprocess, "run")
    @patch.object(connectall.subprocess, "check_output", return_value=ACONNECT_L_SAMPLE)
    def test_skips_connection_when_device_not_currently_present(self, _mock_output, mock_run):
        connections = [{"source_client": "Missing Device", "source_port": "Missing Device MIDI 1",
                        "dest_client": "Lenovo Tab P11", "dest_port": "Lenovo Tab P11 MIDI 1"}]

        connectall.apply_custom_connections(connections)

        mock_run.assert_not_called()


if __name__ == '__main__':
    unittest.main()
