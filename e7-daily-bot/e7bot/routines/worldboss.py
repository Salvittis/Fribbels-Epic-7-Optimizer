"""World Boss routine — single attempt per day (or however many remain).

Assumes you have a saved World Boss team. The bot enters, taps Start,
auto-confirms team, runs the battle, and returns.

Templates required:
  common/lobby_anchor, common/confirm

  worldboss/worldboss_icon       — entry from adventure or lobby
  worldboss/start_button         — botão "Iniciar" / "Battle"
  worldboss/confirm_team         — botão para confirmar a formação
  worldboss/auto_repeat          — checkbox/toggle de auto/repeat (opcional)
  worldboss/result_screen        — tela de resultado pós-batalha (qualquer
                                   elemento estável dela; usado só pra esperar)
"""
from __future__ import annotations

import logging

from ..core.routine import RoutinePrecondition
from ..orchestrator import register
from ._base import LobbyRoutine

log = logging.getLogger(__name__)


@register("worldboss")
class WorldBossRoutine(LobbyRoutine):
    def run(self) -> None:
        with self.step("ensure_lobby"):
            self.ensure_lobby()

        with self.step("open_worldboss"):
            if not self.tap_template("worldboss/worldboss_icon", timeout=10, required=False):
                raise RoutinePrecondition("World Boss not available right now")
            self.driver.sleep(2.0)

        with self.step("start_battle"):
            if not self.tap_template("worldboss/start_button", timeout=6, required=False):
                raise RoutinePrecondition("World Boss start button not found — likely no entries left")
            self.driver.sleep(1.5)
            self.tap_template("worldboss/confirm_team", timeout=6, required=False)
            self.driver.sleep(2.0)
            # Some flows have an extra confirm popup
            self.confirm_dialog(timeout=3)

        with self.step("wait_for_result"):
            # World boss can take ~2 minutes
            self.matcher.wait_for("worldboss/result_screen", timeout=180)
            self.driver.sleep(1.5)

        with self.step("dismiss_results"):
            # Tap to dismiss until lobby is back
            for _ in range(8):
                if self.is_visible("common/lobby_anchor"):
                    break
                self.driver.tap_norm(0.5, 0.95)  # safe bottom-center tap
                self.driver.sleep(1.5)

        with self.step("return_to_lobby"):
            self.ensure_lobby()
