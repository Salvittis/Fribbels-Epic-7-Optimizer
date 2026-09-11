"""Shared helpers for routines that need to navigate to/from the lobby."""
from __future__ import annotations

from ..core.routine import Routine, RoutineError


class LobbyRoutine(Routine):
    """Base class for routines that start and end at the main lobby.

    Required common templates (capture once, reuse everywhere):
      - common/lobby_anchor   — anything UNIQUE to lobby (e.g. the energy icon)
      - common/back_arrow     — generic in-game back arrow
      - common/confirm        — generic OK/Confirm button
      - common/cancel         — generic Cancel/X
    """

    def ensure_lobby(self, max_back_presses: int = 6) -> None:
        """Press back / close popups until lobby is visible.

        Use this at the START of every routine and (optionally) at the end.
        """
        for i in range(max_back_presses):
            if self.is_visible("common/lobby_anchor"):
                return
            # Try generic close buttons first, then back arrow, then ESC
            for tpl in ("common/cancel", "common/back_arrow"):
                m = self.matcher.find(tpl)
                if m is not None:
                    self.driver.tap(m.x, m.y)
                    self.driver.sleep(0.8)
                    break
            else:
                self.driver.back()
                self.driver.sleep(0.8)
        if not self.is_visible("common/lobby_anchor"):
            raise RoutineError("Could not return to lobby")

    def confirm_dialog(self, timeout: float = 5.0) -> bool:
        """Tap a generic confirm/OK button if present. Returns True if found."""
        return self.matcher.tap_when_found("common/confirm", timeout=timeout)

    def cancel_dialog(self, timeout: float = 5.0) -> bool:
        return self.matcher.tap_when_found("common/cancel", timeout=timeout)
