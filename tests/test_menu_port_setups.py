#!/usr/bin/env python3
"""Regression tests for the on-device 'Port Setups' menu (config/menu.xml +
lib/menulcd.py's update_port_setups()/_get_active_setup_id()/
_get_active_setup_name()).

MenuLCD itself needs real LCD hardware/fonts to construct, so these tests
call the real, unbound production methods against a lightweight duck-typed
stand-in exposing only the attributes those methods touch - this exercises
the actual DOM-manipulation logic (not a hand-copied mirror of it), while
staying runnable off a real Pi.
"""

import sys
sys.path.append('./')
sys.path.append('../')
import os
import unittest
from xml.dom import minidom

from lib.menulcd import MenuLCD


class FakePortSetupManager:
    def __init__(self, setups):
        self._setups = setups

    def list_setups(self):
        return self._setups

    def get_setup(self, setup_id):
        for s in self._setups:
            if s["id"] == setup_id:
                return s
        return None


class FakeUserSettings:
    def __init__(self, active_id=None):
        self._active_id = active_id

    def get_setting_value(self, name):
        if name == "active_port_setup_id":
            return self._active_id
        return None


class FakeMenu:
    """Duck-typed stand-in for MenuLCD, bound to the real production methods
    under test so this isn't just a hand-copied reimplementation."""
    _get_active_setup_id = MenuLCD._get_active_setup_id
    _get_active_setup_name = MenuLCD._get_active_setup_name
    update_port_setups = MenuLCD.update_port_setups

    def __init__(self, port_setup_manager, active_id=None):
        menu_xml = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "menu.xml")
        self.DOMTree = minidom.parse(menu_xml)
        self.port_setup_manager = port_setup_manager
        self.usersettings = FakeUserSettings(active_id)
        self._port_setups_menu_cache = {}
        self._cached_active_setup_id = None
        self._cached_active_setup_name = None


class TestMenuPortSetups(unittest.TestCase):
    def test_no_setups_shows_placeholder(self):
        fake = FakeMenu(FakePortSetupManager([]))
        fake.update_port_setups()

        leaves = fake.DOMTree.getElementsByTagName("Port_Setups")
        self.assertEqual([l.getAttribute("text") for l in leaves], ["No setups saved"])
        self.assertEqual(fake._port_setups_menu_cache, {})

    def test_populates_leaves_ordered_with_active_marker(self):
        setups = [
            {"id": 1, "priority": 2, "name": "Only Roland"},
            {"id": 2, "priority": 4, "name": "PC recording"},
            {"id": 3, "priority": 9, "name": "Synthesia"},
        ]
        fake = FakeMenu(FakePortSetupManager(setups), active_id=3)
        fake.update_port_setups()

        leaves = fake.DOMTree.getElementsByTagName("Port_Setups")
        texts = [l.getAttribute("text") for l in leaves]
        self.assertEqual(texts, ["  Only Roland #2", "  PC recording #4", "* Synthesia #9"])
        self.assertEqual(fake._port_setups_menu_cache["* Synthesia #9"]["id"], 3)

    def test_refresh_does_not_duplicate_menu_entry_or_accumulate_leaves(self):
        setups = [
            {"id": 1, "priority": 2, "name": "Only Roland"},
            {"id": 2, "priority": 4, "name": "PC recording"},
        ]
        fake = FakeMenu(FakePortSetupManager(setups), active_id=2)
        fake.update_port_setups()
        fake.update_port_setups()  # simulate re-entering the menu

        top_menus = [m.getAttribute("text") for m in fake.DOMTree.getElementsByTagName("menu")]
        self.assertEqual(top_menus.count("Port Setups"), 1)

        leaves = fake.DOMTree.getElementsByTagName("Port_Setups")
        self.assertEqual(len(leaves), 2)

    def test_get_active_setup_name_caches_and_invalidates_on_change(self):
        fake = FakeMenu(FakePortSetupManager([{"id": 5, "priority": 1, "name": "Synthesia"}]), active_id=5)
        self.assertEqual(fake._get_active_setup_name(), "Synthesia")

        fake.usersettings._active_id = None
        self.assertIsNone(fake._get_active_setup_name())

    def test_get_active_setup_name_none_without_port_setup_manager(self):
        fake = FakeMenu(port_setup_manager=None, active_id=5)
        self.assertIsNone(fake._get_active_setup_name())


if __name__ == '__main__':
    unittest.main()
