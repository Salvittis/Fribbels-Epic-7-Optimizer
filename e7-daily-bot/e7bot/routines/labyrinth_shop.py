"""Labyrinth shop routine — buy bookmarks at the Forest Blessing Shop.

The labyrinth lobby has a vendor that exchanges 'Forest Blessings' for
covenant/friendship bookmarks (and other items). The shop refreshes daily.

Templates required:
  common/lobby_anchor, common/confirm

  labyrinth_shop/labyrinth_icon     — entrada do labirinto pelo lobby/aventura
  labyrinth_shop/shop_npc           — NPC da loja na entrada do labirinto
  labyrinth_shop/covenant           — item invocação de aliança (cov)
  labyrinth_shop/friendship         — item invocação de amizade (fb)
  labyrinth_shop/buy_button         — botão "Comprar" do popup de compra
  labyrinth_shop/exit_labyrinth     — botão de saída do labirinto
"""
from __future__ import annotations

import logging

from ..orchestrator import register
from ._base import LobbyRoutine

log = logging.getLogger(__name__)


@register("labyrinth_shop")
class LabyrinthShopRoutine(LobbyRoutine):
    def run(self) -> None:
        cfg = getattr(self, "config", {}) or {}
        items: list[str] = cfg.get("items") or ["covenant", "friendship"]

        with self.step("ensure_lobby"):
            self.ensure_lobby()

        with self.step("enter_labyrinth"):
            self.tap_template("labyrinth_shop/labyrinth_icon", timeout=10)
            self.driver.sleep(3.0)

        with self.step("open_shop"):
            self.tap_template("labyrinth_shop/shop_npc", timeout=10)
            self.driver.sleep(2.0)

        for item in items:
            with self.step(f"buy_{item}"):
                template = f"labyrinth_shop/{item}"
                if not self.matcher.is_visible(template):
                    log.info("Item %s not available in labyrinth shop today", item)
                    continue
                self.tap_template(template, timeout=4)
                self.driver.sleep(0.8)
                # Buy max-stack via the shop dialog
                self.tap_template("labyrinth_shop/buy_button", timeout=6, required=False)
                self.driver.sleep(0.8)
                self.confirm_dialog(timeout=3)
                self.driver.sleep(1.5)
                # Most shop popups close themselves after purchase, but be safe
                self.cancel_dialog(timeout=2)

        with self.step("leave_labyrinth"):
            self.matcher.tap_when_found("labyrinth_shop/exit_labyrinth", timeout=4)
            self.driver.sleep(1.5)
            self.confirm_dialog(timeout=3)

        with self.step("return_to_lobby"):
            self.ensure_lobby()
