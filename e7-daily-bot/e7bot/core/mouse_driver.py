"""Mouse-based driver — for the Epic Seven PC Client (Stove launcher) or any
desktop window where ADB is not available.

Pattern is borrowed from the existing E7 Secret Shop Refresh tool's MOUSE mode:
  - find the game window by title
  - resize it to a known fixed size so coordinates are reproducible
  - use PIL.ImageGrab to capture, pyautogui to click
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from PIL import ImageGrab

from .driver import Driver

log = logging.getLogger(__name__)


@dataclass
class MouseDriver(Driver):
    """Drive a windowed game via mouse + screen capture.

    Defaults match the Shop Refresh tool (906x539 window). For Epic Seven PC
    Client you'll likely want a larger size — set via `width`, `height`.
    """

    window_title: str = "Epic Seven"
    auto_resize: bool = True
    auto_focus: bool = True
    move_to_origin: bool = True  # snap window to (0, 0) so coordinates are absolute-stable

    # Filled in __post_init__
    _window: Optional[object] = field(default=None, init=False)

    def __post_init__(self) -> None:
        self._connect_window()

    # ---------------------------------------------------------------------- setup

    def _connect_window(self) -> None:
        # Local imports so that the Linux/CI doesn't choke on the desktop deps.
        try:
            import pygetwindow as gw  # type: ignore
            import pyautogui  # noqa: F401  (imported for side-effects + fail fast)
        except ImportError as e:
            raise RuntimeError(
                "MouseDriver requires `pygetwindow` and `pyautogui`. "
                "Install with: pip install pygetwindow pyautogui"
            ) from e

        candidates = [w for w in gw.getWindowsWithTitle(self.window_title)
                      if w.title == self.window_title]
        if not candidates:
            all_titles = [t for t in gw.getAllTitles() if t.strip()]
            raise RuntimeError(
                f"Window with title '{self.window_title}' not found.\n"
                f"Tip: hover over the game's taskbar icon to see its exact title.\n"
                f"Currently visible windows containing 'epic' or 'stove':\n  - "
                + "\n  - ".join(t for t in all_titles
                                if "epic" in t.lower() or "stove" in t.lower()
                                or "blue" in t.lower())
            )
        self._window = candidates[0]
        self._prepare_window()
        log.info("Connected to window '%s' at (%d,%d) size %dx%d",
                 self._window.title, self._window.left, self._window.top,
                 self._window.width, self._window.height)

    def _prepare_window(self) -> None:
        w = self._window
        if w is None:
            return
        try:
            if w.isMinimized:
                w.restore()
            if self.auto_focus:
                try:
                    w.activate()
                except Exception as e:
                    # Windows sometimes blocks activate; not fatal.
                    log.debug("window.activate failed: %s", e)
            if self.move_to_origin:
                w.moveTo(0, 0)
            if self.auto_resize:
                w.resizeTo(self.width, self.height)
        except Exception as e:
            log.warning("Window preparation issue: %s", e)

    # ---------------------------------------------------------------------- API

    def screenshot(self) -> np.ndarray:
        w = self._window
        if w is None:
            raise RuntimeError("No window connected")
        # Re-focus to ensure the window is on top before capturing
        if self.auto_focus:
            try:
                w.activate()
            except Exception:
                pass
        # all_screens=True fixes pyautogui's multimonitor bug
        bbox = (w.left, w.top, w.left + w.width, w.top + w.height)
        img = ImageGrab.grab(bbox=bbox, all_screens=True)
        return np.array(img)[:, :, ::-1].copy()  # PIL RGB -> BGR

    def tap(self, x: int, y: int) -> None:
        import pyautogui
        x, y = self._jitter(x, y)
        # x,y are window-relative; convert to screen coords
        sx, sy = self._to_screen(x, y)
        pyautogui.moveTo(sx, sy, duration=0.05)
        pyautogui.click()
        self.sleep(self.tap_delay)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        import pyautogui
        sx1, sy1 = self._to_screen(x1, y1)
        sx2, sy2 = self._to_screen(x2, y2)
        pyautogui.moveTo(sx1, sy1, duration=0.05)
        pyautogui.mouseDown()
        time.sleep(0.05)
        pyautogui.moveTo(sx2, sy2, duration=duration_ms / 1000.0)
        time.sleep(0.05)
        pyautogui.mouseUp()
        self.sleep(0.4)

    def back(self) -> None:
        # Epic Seven PC client doesn't have an Android back button. Most flows use
        # an in-game back arrow that we'll target via templates instead. We'll
        # leave this as ESC (for menus etc.).
        import pyautogui
        pyautogui.press("escape")
        self.sleep(self.tap_delay)

    # ---------------------------------------------------------------------- internal

    def _to_screen(self, x: int, y: int) -> tuple[int, int]:
        w = self._window
        if w is None:
            return x, y
        return (w.left + x, w.top + y)
