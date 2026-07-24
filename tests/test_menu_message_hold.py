#!/usr/bin/env python3
"""Regression test for the render_message()/show() race: applying a Setup via
the web runs on a separate Flask/waitress request thread, which does NOT
block the main visualizer loop the way a GPIO-triggered call does. Without a
shared "hold" window, the main loop's own periodic show() could paint over an
"Applied setup" toast well before its intended display duration elapsed.

MenuLCD itself needs real LCD hardware/fonts to construct, so this calls the
real, unbound show() against a minimal duck-typed stand-in - the guard is an
early return before anything else is touched, so this doesn't need the full
font/DOM/LCD setup real construction would require.
"""

import sys
sys.path.append('./')
sys.path.append('../')
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from lib import menulcd as menulcd_module
from lib.menulcd import MenuLCD


class FakeMenu:
    show = MenuLCD.show

    def __init__(self, message_hold_until=0):
        self.screen_on = 1
        self._message_hold_until = message_hold_until


class FakeMenuForRenderMessage:
    render_message = MenuLCD.render_message
    scale = MenuLCD.scale
    rotate_image = MenuLCD.rotate_image

    def __init__(self):
        self.theme = SimpleNamespace(error_color=(220, 60, 60), success_color=(60, 180, 90))
        self.text_color = (255, 255, 255)
        self.background_color = (0, 0, 0)
        self.font = None
        self.args = SimpleNamespace(rotatescreen="false")
        self.LCD = SimpleNamespace(width=128, height=128, font_scale=1, LCD_ShowImage=lambda *a, **k: None)
        self._message_hold_until = 0


class TestRenderMessageSetsHoldWindow(unittest.TestCase):
    @patch.object(menulcd_module.LCD_Config, "Driver_Delay_ms")
    def test_hold_until_reflects_the_requested_delay(self, _mock_delay):
        menu = FakeMenuForRenderMessage()
        before = time.monotonic()

        menu.render_message("Applied setup:", "Synthesia", 2500, level="success")

        # hold window should extend ~2.5s past the call, not the old ~500ms
        # default and not some unrelated/zero value.
        self.assertGreater(menu._message_hold_until, before + 2.4)
        self.assertLess(menu._message_hold_until, before + 2.6)


class TestShowSkipsWhileMessageIsHeld(unittest.TestCase):
    def test_show_returns_false_while_a_message_is_being_held(self):
        menu = FakeMenu(message_hold_until=time.monotonic() + 5)
        self.assertFalse(menu.show())

    def test_show_proceeds_once_the_hold_window_has_elapsed(self):
        menu = FakeMenu(message_hold_until=time.monotonic() - 1)
        # Past the hold window, show() falls through to its normal drawing
        # logic - which needs real LCD/font/DOM state this fake doesn't have,
        # so it's expected to blow up past the guard rather than return False.
        with self.assertRaises(AttributeError):
            menu.show()


if __name__ == '__main__':
    unittest.main()
