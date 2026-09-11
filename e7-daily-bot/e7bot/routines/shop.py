"""Shop routine — delegates to the existing E7 Secret Shop Refresh tool.

This routine doesn't reimplement the shop loop. Instead it imports the
SecretShopRefresh class from the sibling project and runs it inline.

If the user is on PC Client and the shop refresh tool's MOUSE mode works for
them, we just trigger it. If on emulator with ADB, the user should run the
ADB version of the tool directly.

Requires:
  - shoprefresh tool checked out at  ../shoprefresh/Epic-Seven-E7-Secret-Shop-Refresh/
  - Pre-purchased templates in that tool's assets/ (cov.png, mys.png, fb.png)
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from ..core.routine import RoutineError, RoutinePrecondition
from ..orchestrator import register
from ._base import LobbyRoutine

log = logging.getLogger(__name__)


SHOPREFRESH_DIR = (
    Path(__file__).resolve().parents[3]
    / "shoprefresh"
    / "Epic-Seven-E7-Secret-Shop-Refresh"
)


@register("shop")
class ShopRoutine(LobbyRoutine):
    def run(self) -> None:
        if not SHOPREFRESH_DIR.exists():
            raise RoutinePrecondition(
                f"Shop Refresh tool not found at {SHOPREFRESH_DIR}. "
                f"Skipping shop routine."
            )

        # Make the shop refresh tool importable
        sys.path.insert(0, str(SHOPREFRESH_DIR))
        cwd_before = Path.cwd()
        try:
            # The tool reads PNGs from CWD/assets — chdir for it to work.
            import os
            os.chdir(str(SHOPREFRESH_DIR))

            try:
                from E7SecretShopRefresh import SecretShopRefresh  # type: ignore
            except ImportError as e:
                raise RoutineError(f"Failed to import SecretShopRefresh: {e}") from e

            cfg = getattr(self, "config", {}) or {}
            items: list[str] = cfg.get("items") or ["covenant", "mystic"]
            budget = cfg.get("budget")  # None = unlimited

            # Map our friendly names to the tool's PNG filenames
            item_map = {
                "covenant": ("cov.png", "Covenant bookmark", 184_000),
                "mystic":   ("mys.png", "Mystic medal", 280_000),
                "friendship": ("fb.png", "Friendship bookmark", 18_000),
            }

            with self.step("prepare_shop_refresh"):
                # `tk_instance=None` runs headless without the GUI
                refresher = SecretShopRefresh(
                    title_name=self._resolve_window_title(),
                    callback=lambda: log.info("Shop refresh callback fired"),
                    tk_instance=None,
                    budget=budget,
                    allow_move=False,
                    debug=False,
                    join_thread=True,  # block until done
                )

                for friendly in items:
                    if friendly not in item_map:
                        log.warning("Unknown shop item '%s' — skipping", friendly)
                        continue
                    png, name, price = item_map[friendly]
                    refresher.addShopItem(png, name=name, price=price)

            with self.step("run_shop_refresh"):
                log.info("Starting shop refresh: items=%s budget=%s", items, budget)
                refresher.start()
                # join_thread=True means start() blocks until refresh ends
                log.info("Shop refresh finished")

        finally:
            os.chdir(str(cwd_before))
            sys.path.remove(str(SHOPREFRESH_DIR))

    def _resolve_window_title(self) -> str:
        """Pull the window title from driver config so both stay in sync."""
        # Walk back to the orchestrator's config via the driver instance
        from ..core.mouse_driver import MouseDriver
        if isinstance(self.driver, MouseDriver):
            return self.driver.window_title
        return "Epic Seven"
