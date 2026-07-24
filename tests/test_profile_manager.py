#!/usr/bin/env python3

import sys
sys.path.append('./')
sys.path.append('../')
import os
import sqlite3
import tempfile
import unittest

from lib.profile_manager import ProfileManager


class TestProfileManager(unittest.TestCase):
    def setUp(self):
        fd, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        os.remove(self.db_path)
        # Nonexistent songs dir: _list_song_files() hits FileNotFoundError and
        # returns [], so tests don't depend on the repo's real Songs/ folder.
        self.pm = ProfileManager(db_path=self.db_path, songs_dir="nonexistent_dir_xyz")

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_connect_closes_connection_after_use(self):
        with self.pm._connect() as conn:
            conn.execute("SELECT 1")
        # The connection must actually be closed, not just committed/rolled back
        with self.assertRaises(sqlite3.ProgrammingError):
            conn.execute("SELECT 1")

    def test_create_and_get_profile(self):
        profile_id = self.pm.create_profile("Bob")
        self.assertEqual(self.pm.get_profile_id("Bob"), profile_id)
        self.assertEqual(self.pm.get_profiles(), [{"id": profile_id, "name": "Bob"}])

    def test_get_learning_settings_missing_song_returns_defaults(self):
        # Regression test: get_learning_settings() used to read cur.fetchone()
        # after its `with self._connect() as conn:` block had already exited,
        # which only worked because _connect() leaked the connection instead
        # of closing it. Now that the leak is fixed, this must still work.
        profile_id = self.pm.create_profile("Bob")
        settings = self.pm.get_learning_settings(profile_id, "no_such_song.mid")
        self.assertEqual(settings["tempo"], 100)
        self.assertEqual(settings["loop"], 1)

    def test_get_highscores_empty_when_no_songs(self):
        profile_id = self.pm.create_profile("Bob")
        self.assertEqual(self.pm.get_highscores(profile_id), {})

    def test_update_highscore_only_increases(self):
        profile_id = self.pm.create_profile("Bob")
        self.assertTrue(self.pm.update_highscore(profile_id, "song.mid", 50))
        self.assertFalse(self.pm.update_highscore(profile_id, "song.mid", 30))
        self.assertTrue(self.pm.update_highscore(profile_id, "song.mid", 80))
        self.assertEqual(self.pm.get_highscores(profile_id)["song.mid"], 80)

    def test_delete_profile(self):
        profile_id = self.pm.create_profile("Bob")
        self.pm.delete_profile(profile_id)
        self.assertIsNone(self.pm.get_profile_id("Bob"))


if __name__ == '__main__':
    unittest.main()
