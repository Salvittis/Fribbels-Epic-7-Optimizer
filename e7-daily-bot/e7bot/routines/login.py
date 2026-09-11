"""Login routine — collect mail, login bonus, free skystones from the lobby.

Templates required (capture in PT-BR client at the configured resolution):
  - common/lobby_anchor     — any pixel-stable UI unique to the lobby
  - common/confirm          — OK/Confirmar button used by most popups
  - common/back_arrow       — in-game back arrow
  - login/mail_icon         — envelope icon in the lobby (top right typically)
  - login/claim_all         — botão "Receber tudo" inside mail
  - login/login_bonus       — popup banner that opens automatically (optional)
"""
from __future__ import annotations

import logging

from ..orchestrator import register
from ._base import LobbyRoutine

log = logging.getLogger(__name__)


@register("login")
class LoginRoutine(LobbyRoutine):
    def run(self) -> None:
        with self.step("ensure_lobby"):
            self.ensure_lobby()

        # The login bonus popup typically auto-opens when you enter the lobby.
        # We try to dismiss it if present, but it's optional.
        with self.step("dismiss_login_bonus"):
            for _ in range(3):
                if not self.matcher.is_visible("login/login_bonus"):
                    break
                # Just click anywhere safe to dismiss; falls back to ESC.
                self.driver.back()
                self.driver.sleep(0.8)

        with self.step("open_mail"):
            # Mail icon should be in the lobby HUD. Tolerant timeout.
            if not self.tap_template("login/mail_icon", timeout=8, required=False):
                log.info("Mail icon not found; skipping (no mail or HUD changed)")
                return
            self.driver.sleep(1.0)

        with self.step("claim_all_mail"):
            # If there's nothing to claim the button is greyed out; try anyway.
            self.tap_template("login/claim_all", timeout=8, required=False)
            self.driver.sleep(1.5)
            # Some clients show a confirmation popup
            self.confirm_dialog(timeout=3.0)
            self.driver.sleep(1.0)

        with self.step("return_to_lobby"):
            self.ensure_lobby()
