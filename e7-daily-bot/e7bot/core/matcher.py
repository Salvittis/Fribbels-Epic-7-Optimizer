"""Template matching helpers.

Routines describe what they want to find on screen as PNG templates plus a
confidence threshold. The matcher loads them once, and exposes:
  - find(name)              -> Optional[MatchResult]      (single best match)
  - find_all(name)          -> list[MatchResult]
  - wait_for(name, timeout) -> MatchResult                 (polling until found)
  - tap_when_found(name)    -> bool                        (find + driver.tap)
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from .driver import Driver

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class MatchResult:
    name: str
    confidence: float
    x: int  # center x of the matched region
    y: int  # center y
    w: int
    h: int

    @property
    def center(self) -> tuple[int, int]:
        return self.x, self.y


class TemplateMatcher:
    """Loads PNG templates from a directory and matches them against screenshots.

    Templates are addressed by relative path without extension, e.g.
    `login/mail_button` for `<assets>/login/mail_button.png`.
    """

    def __init__(
        self,
        driver: Driver,
        assets_dir: str | Path,
        default_threshold: float = 0.85,
    ) -> None:
        self.driver = driver
        self.assets_dir = Path(assets_dir)
        self.default_threshold = default_threshold
        self._cache: dict[str, np.ndarray] = {}

    def _load(self, name: str) -> np.ndarray:
        if name in self._cache:
            return self._cache[name]
        path = self.assets_dir / f"{name}.png"
        if not path.exists():
            raise FileNotFoundError(f"Template not found: {path}")
        img = cv2.imread(str(path), cv2.IMREAD_COLOR)
        if img is None:
            raise RuntimeError(f"Failed to load template image: {path}")
        self._cache[name] = img
        return img

    def find(
        self,
        name: str,
        screenshot: Optional[np.ndarray] = None,
        threshold: Optional[float] = None,
    ) -> Optional[MatchResult]:
        """Return the single best match for `name` if confidence >= threshold."""
        screen = screenshot if screenshot is not None else self.driver.screenshot()
        template = self._load(name)
        thr = threshold if threshold is not None else self.default_threshold

        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, max_loc = cv2.minMaxLoc(result)

        if max_val < thr:
            log.debug("Match miss: %s confidence=%.3f < %.3f", name, max_val, thr)
            return None

        h, w = template.shape[:2]
        return MatchResult(
            name=name,
            confidence=float(max_val),
            x=max_loc[0] + w // 2,
            y=max_loc[1] + h // 2,
            w=w,
            h=h,
        )

    def find_all(
        self,
        name: str,
        screenshot: Optional[np.ndarray] = None,
        threshold: Optional[float] = None,
    ) -> list[MatchResult]:
        """Return all matches above threshold (deduplicated by spatial proximity)."""
        screen = screenshot if screenshot is not None else self.driver.screenshot()
        template = self._load(name)
        thr = threshold if threshold is not None else self.default_threshold

        result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)
        h, w = template.shape[:2]
        ys, xs = np.where(result >= thr)

        matches: list[MatchResult] = []
        for y, x in zip(ys, xs):
            cx, cy = int(x + w // 2), int(y + h // 2)
            # dedupe: skip if too close to an already-recorded match
            if any(abs(cx - m.x) < w * 0.5 and abs(cy - m.y) < h * 0.5 for m in matches):
                continue
            matches.append(
                MatchResult(name=name, confidence=float(result[y, x]),
                            x=cx, y=cy, w=w, h=h)
            )
        return matches

    def wait_for(
        self,
        name: str,
        timeout: float = 10.0,
        poll: float = 0.5,
        threshold: Optional[float] = None,
    ) -> MatchResult:
        """Poll until template appears, raise TimeoutError if it doesn't."""
        deadline = time.monotonic() + timeout
        last_conf = 0.0
        while time.monotonic() < deadline:
            m = self.find(name, threshold=threshold)
            if m is not None:
                return m
            self.driver.sleep(poll)
        raise TimeoutError(
            f"Template '{name}' not found within {timeout:.1f}s "
            f"(last best confidence: {last_conf:.2f})"
        )

    def is_visible(self, name: str, threshold: Optional[float] = None) -> bool:
        return self.find(name, threshold=threshold) is not None

    def tap_when_found(
        self,
        name: str,
        timeout: float = 10.0,
        threshold: Optional[float] = None,
    ) -> bool:
        """Wait for a template, then tap its center. Returns False on timeout."""
        try:
            m = self.wait_for(name, timeout=timeout, threshold=threshold)
        except TimeoutError:
            log.warning("tap_when_found timeout: %s", name)
            return False
        self.driver.tap(m.x, m.y)
        return True
