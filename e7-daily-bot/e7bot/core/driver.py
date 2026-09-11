"""Device drivers — abstract interface plus ADB and Mouse implementations.

The driver layer hides whether we're talking to an Android emulator over ADB
or to a desktop window via mouse events. Routines code against `Driver`.
"""
from __future__ import annotations

import logging
import random
import subprocess
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image

log = logging.getLogger(__name__)


@dataclass
class Driver(ABC):
    """Abstract input/output surface for a running Epic Seven instance."""

    width: int = 1920
    height: int = 1080
    tap_jitter_px: int = 6  # randomize tap location to look human
    tap_delay: float = 0.25  # seconds after each tap

    @abstractmethod
    def screenshot(self) -> np.ndarray:
        """Return current screen as BGR numpy array (cv2 convention)."""

    @abstractmethod
    def tap(self, x: int, y: int) -> None:
        """Tap at absolute pixel coordinates."""

    @abstractmethod
    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        """Swipe from (x1,y1) to (x2,y2)."""

    @abstractmethod
    def back(self) -> None:
        """Send a 'back' input (Android back button or ESC equivalent)."""

    def tap_norm(self, nx: float, ny: float) -> None:
        """Tap at normalized coordinates (0.0-1.0). Useful when screen size varies."""
        self.tap(int(nx * self.width), int(ny * self.height))

    def _jitter(self, x: int, y: int) -> tuple[int, int]:
        if self.tap_jitter_px <= 0:
            return x, y
        j = self.tap_jitter_px
        return (x + random.randint(-j, j), y + random.randint(-j, j))

    def sleep(self, seconds: float, jitter: float = 0.15) -> None:
        """Human-like variable sleep."""
        wait = seconds * (1.0 + random.uniform(-jitter, jitter))
        time.sleep(max(0.05, wait))


@dataclass
class AdbDriver(Driver):
    """ADB-based driver. Works with any Android emulator that exposes ADB."""

    adb_path: str = "adb"
    serial: Optional[str] = None  # e.g. "127.0.0.1:5555" for BlueStacks/LDPlayer
    _device_args: list[str] = field(default_factory=list, init=False)

    def __post_init__(self) -> None:
        self._device_args = ["-s", self.serial] if self.serial else []
        self._verify_connection()

    def _adb(self, *args: str, capture: bool = False) -> subprocess.CompletedProcess:
        cmd = [self.adb_path, *self._device_args, *args]
        log.debug("adb cmd: %s", " ".join(cmd))
        return subprocess.run(
            cmd,
            stdout=subprocess.PIPE if capture else None,
            stderr=subprocess.PIPE,
            check=False,
        )

    def _verify_connection(self) -> None:
        result = self._adb("devices", capture=True)
        out = result.stdout.decode("utf-8", errors="ignore")
        lines = [ln for ln in out.splitlines()[1:] if ln.strip()]
        if not lines:
            raise RuntimeError(
                "No ADB devices detected. Connect your emulator first "
                "(e.g. for BlueStacks: enable ADB in advanced settings)."
            )
        log.info("ADB devices:\n%s", out)

    def screenshot(self) -> np.ndarray:
        result = self._adb("exec-out", "screencap", "-p", capture=True)
        if not result.stdout:
            raise RuntimeError("ADB screencap returned empty data")
        # ADB returns PNG bytes; decode via PIL then convert to BGR for cv2
        img = Image.open(BytesIO(result.stdout)).convert("RGB")
        return np.array(img)[:, :, ::-1].copy()  # RGB -> BGR

    def tap(self, x: int, y: int) -> None:
        x, y = self._jitter(x, y)
        self._adb("shell", "input", "tap", str(x), str(y))
        self.sleep(self.tap_delay)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
        self._adb(
            "shell",
            "input",
            "swipe",
            str(x1), str(y1), str(x2), str(y2),
            str(duration_ms),
        )
        self.sleep(0.4)

    def back(self) -> None:
        self._adb("shell", "input", "keyevent", "KEYCODE_BACK")
        self.sleep(self.tap_delay)


def default_adb_path() -> str:
    """Locate the bundled ADB executable from the shoprefresh tool, with PATH fallback."""
    bundled = (
        Path(__file__).resolve().parents[3]
        / "shoprefresh"
        / "Epic-Seven-E7-Secret-Shop-Refresh"
        / "adb-assets"
        / "platform-tools"
        / "adb.exe"
    )
    return str(bundled) if bundled.exists() else "adb"
