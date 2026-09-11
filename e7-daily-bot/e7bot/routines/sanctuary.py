"""Sanctuary daily routine.

Visits the three sanctuary sub-features and collects their daily rewards:
  1. Gold Tree (Árvore Dourada) — colher
  2. Training Camp (Acampamento de Treinamento) — coletar exp + reativar
  3. Forest of Souls (Floresta das Almas) — coletar runas

Templates required (capture in PT-BR client):
  common/lobby_anchor
  common/back_arrow
  common/confirm

  sanctuary/sanctuary_icon       — atalho do santuário no lobby
  sanctuary/gold_tree            — botão da árvore dourada
  sanctuary/gold_tree_harvest    — botão "Colher" na árvore
  sanctuary/training_camp        — botão acampamento de treinamento
  sanctuary/training_collect     — botão "Receber" exp
  sanctuary/training_dispatch    — botão "Iniciar treinamento"
  sanctuary/forest               — botão floresta das almas
  sanctuary/forest_collect       — botão "Receber" runas
"""
from __future__ import annotations

import logging

from ..orchestrator import register
from ._base import LobbyRoutine

log = logging.getLogger(__name__)


@register("sanctuary")
class SanctuaryRoutine(LobbyRoutine):
    def run(self) -> None:
        with self.step("ensure_lobby"):
            self.ensure_lobby()

        with self.step("open_sanctuary"):
            self.tap_template("sanctuary/sanctuary_icon", timeout=10)
            self.driver.sleep(2.0)

        # ---- Gold Tree ----
        with self.step("gold_tree"):
            if self.tap_template("sanctuary/gold_tree", timeout=8, required=False):
                self.driver.sleep(1.5)
                self.tap_template("sanctuary/gold_tree_harvest", timeout=6, required=False)
                self.driver.sleep(1.5)
                self.confirm_dialog(timeout=3)
                self.driver.sleep(1.0)
                self.matcher.tap_when_found("common/back_arrow", timeout=4)
                self.driver.sleep(1.0)

        # ---- Training Camp ----
        with self.step("training_camp"):
            if self.tap_template("sanctuary/training_camp", timeout=8, required=False):
                self.driver.sleep(1.5)
                # First collect any finished training, then redispatch
                self.matcher.tap_when_found("sanctuary/training_collect", timeout=4)
                self.driver.sleep(1.0)
                self.confirm_dialog(timeout=3)
                self.driver.sleep(1.0)
                self.matcher.tap_when_found("sanctuary/training_dispatch", timeout=4)
                self.driver.sleep(1.0)
                self.confirm_dialog(timeout=3)
                self.driver.sleep(1.0)
                self.matcher.tap_when_found("common/back_arrow", timeout=4)
                self.driver.sleep(1.0)

        # ---- Forest of Souls ----
        with self.step("forest"):
            if self.tap_template("sanctuary/forest", timeout=8, required=False):
                self.driver.sleep(1.5)
                self.matcher.tap_when_found("sanctuary/forest_collect", timeout=4)
                self.driver.sleep(1.5)
                self.confirm_dialog(timeout=3)
                self.driver.sleep(1.0)

        with self.step("return_to_lobby"):
            self.ensure_lobby()
