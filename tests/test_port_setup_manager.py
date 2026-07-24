#!/usr/bin/env python3

import sys
sys.path.append('./')
sys.path.append('../')
import os
import tempfile
import unittest
from lib.port_setup_manager import PortSetupManager, get_next_setup


class TestPortSetupManager(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.db_path)  # let PortSetupManager create it fresh
        self.psm = PortSetupManager(db_path=self.db_path)

    def tearDown(self):
        for suffix in ("", "-wal", "-shm"):
            path = self.db_path + suffix
            if os.path.exists(path):
                os.remove(path)

    def test_connect_enables_wal_mode(self):
        # WAL avoids the fsync-heavy journal dance on every commit - important
        # for SD card longevity given how often setups get saved/applied.
        with self.psm._connect() as conn:
            mode = conn.execute("PRAGMA journal_mode;").fetchone()[0]
        self.assertEqual(mode.lower(), "wal")

    def test_01_create_and_list_ordered_by_priority(self):
        self.psm.create_setup("Synthesia", 9, "Lenovo", "Roland", "Lenovo", True)
        self.psm.create_setup("Piano only", 2, "Roland", "default", "Roland", False)
        self.psm.create_setup("PC recording", 4, "PC", "default", "PC", False)

        setups = self.psm.list_setups()
        self.assertEqual([s["priority"] for s in setups], [2, 4, 9])
        self.assertEqual([s["name"] for s in setups], ["Piano only", "PC recording", "Synthesia"])

    def test_02_get_setup(self):
        created = self.psm.create_setup("Synthesia", 1, "Lenovo", "Roland", "Lenovo", True)
        fetched = self.psm.get_setup(created["id"])
        self.assertEqual(fetched["name"], "Synthesia")
        self.assertTrue(fetched["auto_connect"])
        self.assertIsNone(self.psm.get_setup(9999))

    def test_03_duplicate_priority_rejected_on_create(self):
        self.psm.create_setup("Setup A", 5, "Roland", "default", "Roland", False)
        with self.assertRaises(ValueError):
            self.psm.create_setup("Setup B", 5, "Lenovo", "default", "Lenovo", False)

    def test_04_duplicate_priority_rejected_on_update(self):
        a = self.psm.create_setup("Setup A", 5, "Roland", "default", "Roland", False)
        b = self.psm.create_setup("Setup B", 6, "Lenovo", "default", "Lenovo", False)
        with self.assertRaises(ValueError):
            self.psm.update_setup(b["id"], "Setup B", 5, "Lenovo", "default", "Lenovo", False)
        # Updating a setup to keep its own priority must not raise
        updated = self.psm.update_setup(a["id"], "Setup A renamed", 5, "Roland", "default", "Roland", False)
        self.assertEqual(updated["name"], "Setup A renamed")

    def test_05_delete_setup(self):
        created = self.psm.create_setup("Setup A", 1, "Roland", "default", "Roland", False)
        self.assertTrue(self.psm.delete_setup(created["id"]))
        self.assertIsNone(self.psm.get_setup(created["id"]))
        self.assertFalse(self.psm.delete_setup(created["id"]))

    def test_06_validation_errors(self):
        with self.assertRaises(ValueError):
            self.psm.create_setup("", 1, "Roland", "default", "Roland", False)
        with self.assertRaises(ValueError):
            self.psm.create_setup("Setup", "not-an-int", "Roland", "default", "Roland", False)
        with self.assertRaises(ValueError):
            self.psm.create_setup("Setup", 1, "", "default", "Roland", False)
        with self.assertRaises(ValueError):
            self.psm.create_setup("Setup", 1, "Roland", "default", "", False)


class TestGetNextSetup(unittest.TestCase):
    def setUp(self):
        self.setups = [
            {"id": 2, "priority": 2},
            {"id": 4, "priority": 4},
            {"id": 9, "priority": 9},
        ]

    def test_empty_list_returns_none(self):
        self.assertIsNone(get_next_setup([], None))
        self.assertIsNone(get_next_setup([], 2))

    def test_none_current_returns_first(self):
        self.assertEqual(get_next_setup(self.setups, None)["id"], 2)

    def test_advances_to_next_by_priority(self):
        self.assertEqual(get_next_setup(self.setups, 2)["id"], 4)
        self.assertEqual(get_next_setup(self.setups, 4)["id"], 9)

    def test_wraps_around_from_last(self):
        self.assertEqual(get_next_setup(self.setups, 9)["id"], 2)

    def test_unknown_or_deleted_current_restarts_at_first(self):
        self.assertEqual(get_next_setup(self.setups, 999)["id"], 2)

    def test_single_element_list_cycles_to_itself(self):
        single = [{"id": 42, "priority": 1}]
        self.assertEqual(get_next_setup(single, None)["id"], 42)
        self.assertEqual(get_next_setup(single, 42)["id"], 42)


if __name__ == '__main__':
    unittest.main()
