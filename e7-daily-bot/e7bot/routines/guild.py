"""Guild daily routine — check-in + donation.

Templates required:
  common/lobby_anchor, common/confirm, common/back_arrow

  guild/guild_icon          — entry button (geralmente no menu lateral/lobby)
  guild/checkin             — botão "Verificar presença" / check-in
  guild/donate              — botão "Doar" no painel da guilda
  guild/donate_max          — botão "Máximo" no popup de doação (opcional)
"""
from __future__ import annotations

import logging

from ..orchestrator import register
from ._base import LobbyRoutine

log = logging.getLogger(__name__)


@register("guild")
class GuildRoutine(LobbyRoutine):
    def run(self) -> None:
        with self.step("ensure_lobby"):
            self.ensure_lobby()

        with self.step("open_guild"):
            self.tap_template("guild/guild_icon", timeout=10)
            self.driver.sleep(2.0)

        with self.step("checkin"):
            if self.tap_template("guild/checkin", timeout=6, required=False):
                self.driver.sleep(1.0)
                self.confirm_dialog(timeout=3)
                self.driver.sleep(1.0)

        with self.step("donate"):
            if self.tap_template("guild/donate", timeout=6, required=False):
                self.driver.sleep(1.0)
                # Try to maximize donation; some clients auto-fill
                self.matcher.tap_when_found("guild/donate_max", timeout=2)
                self.driver.sleep(0.5)
                self.confirm_dialog(timeout=3)
                self.driver.sleep(1.5)

        with self.step("return_to_lobby"):
            self.ensure_lobby()
