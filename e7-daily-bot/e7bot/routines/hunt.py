"""Hunt routine — auto-farm a hunt and STOP when a dropped gear matches a filter.

Loop shape (one battle):
  1. Confirm we're on the hunt selection / "Repeat" screen.
  2. Tap Start (or wait for auto-repeat to consume an entry).
  3. Wait for either the gear-drop popup or the no-loot result screen.
  4. If gear dropped: OCR substats from a fixed region of the popup,
     compare against `stop_on_drop` filters. Match → stop and notify.
     No match → close the popup and continue.
  5. If max_battles reached, stop.

Templates required:
  common/lobby_anchor, common/confirm

  hunt/hunt_icon              — atalho hunt no lobby/aventura
  hunt/wyvern  hunt/banshee  hunt/golem  hunt/azimanak
                              — botão de cada hunt (capture os que você usa)
  hunt/difficulty_13          — botão de dificuldade 13 (capture outras se usar)
  hunt/start_battle           — botão "Iniciar batalha"
  hunt/auto_repeat            — botão de auto-repetir (opcional)
  hunt/result_victory         — qualquer elemento da tela de vitória
  hunt/gear_drop_popup        — banner "Equipamento adquirido" / popup de drop
  hunt/no_drop_continue       — botão "Continuar" quando NÃO dropou gear
  hunt/drop_close             — botão fechar/avançar do popup de drop
  hunt/gear_kind_boots        — ícone/label de "Botas" no popup (capture os tipos
                                que você quer filtrar; armas, capacete, armadura,
                                colar, anel, botas)
  hunt/gear_kind_ring
  hunt/gear_kind_weapon
  hunt/gear_kind_helmet
  hunt/gear_kind_armor
  hunt/gear_kind_necklace

OCR region (substats) is calibrated separately — see SUBSTAT_REGION below.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from ..core.routine import RoutineError, RoutinePrecondition
from ..ocr.stat_reader import DroppedGear, StatReader, Substat
from ..orchestrator import register
from ._base import LobbyRoutine

log = logging.getLogger(__name__)


# Region of the drop popup where substats are shown, as fractions of window size.
# Calibrate by capturing a real drop screenshot, opening it, and measuring.
# These defaults assume the standard E7 1920x1080 drop popup.
SUBSTAT_REGION_NORM = (0.40, 0.55, 0.30, 0.20)  # (x_frac, y_frac, w_frac, h_frac)

GEAR_TYPES = ("boots", "ring", "weapon", "helmet", "armor", "necklace")


@dataclass
class HuntStats:
    battles: int = 0
    drops: int = 0
    matched: int = 0


@register("hunt")
class HuntRoutine(LobbyRoutine):
    def run(self) -> None:
        cfg = getattr(self, "config", {}) or {}
        target: str = cfg.get("target", "wyvern")
        difficulty: int = int(cfg.get("difficulty", 13))
        max_battles: int = int(cfg.get("max_battles", 60))
        filters: list[dict] = cfg.get("stop_on_drop", []) or []

        stats = HuntStats()
        reader = StatReader(lang="por")

        with self.step("ensure_lobby"):
            self.ensure_lobby()

        with self.step("navigate_to_hunt"):
            self.tap_template("hunt/hunt_icon", timeout=10)
            self.driver.sleep(2.0)
            self.tap_template(f"hunt/{target}", timeout=10)
            self.driver.sleep(2.0)
            self.tap_template(f"hunt/difficulty_{difficulty}", timeout=8, required=False)
            self.driver.sleep(1.5)

        with self.step("hunt_loop"):
            for i in range(max_battles):
                stats.battles += 1
                log.info("Hunt %d/%d", i + 1, max_battles)

                # Start the battle (idempotent — tap if Start button visible)
                if self.matcher.is_visible("hunt/start_battle"):
                    self.driver.tap(*self.matcher.find("hunt/start_battle").center)
                    self.driver.sleep(2.0)

                # Wait for the result. We poll for either the drop popup or the
                # no-drop continue button.
                drop = self._await_battle_end(reader, timeout=180)

                if drop is None:
                    # No drop or OCR failed — close popups and continue
                    self.matcher.tap_when_found("hunt/no_drop_continue", timeout=4)
                    self.matcher.tap_when_found("hunt/drop_close", timeout=2)
                    self.driver.sleep(1.5)
                    continue

                stats.drops += 1
                if any(drop.matches_filter(f) for f in filters):
                    stats.matched += 1
                    log.warning("MATCH! Stopping hunt. Drop: %s", drop)
                    raise RoutinePrecondition(
                        f"Stopped on filter match after {stats.battles} battles. "
                        f"Drop: {drop.gear_type} substats={drop.substats}"
                    )
                else:
                    log.info("Drop did not match filter: %s", drop)
                    self.matcher.tap_when_found("hunt/drop_close", timeout=4)
                    self.driver.sleep(1.5)

        log.info("Hunt finished. Battles=%d Drops=%d Matched=%d",
                 stats.battles, stats.drops, stats.matched)

    # ------------------------------------------------------------------ helpers

    def _await_battle_end(self, reader: StatReader, timeout: float) -> Optional[DroppedGear]:
        """Wait for the result screen and return a parsed DroppedGear if a gear
        dropped, else None."""
        import time
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.driver.sleep(1.0)
            if self.matcher.is_visible("hunt/gear_drop_popup"):
                return self._read_drop(reader)
            if self.matcher.is_visible("hunt/no_drop_continue"):
                return None
            if self.matcher.is_visible("hunt/result_victory"):
                # Victory screen but no drop popup yet — tap to advance
                self.driver.tap_norm(0.5, 0.95)
        raise RoutineError(f"Battle did not end within {timeout:.0f}s")

    def _read_drop(self, reader: StatReader) -> DroppedGear:
        """Snapshot the drop popup, identify gear type via templates, OCR substats."""
        screen = self.driver.screenshot()
        gear = DroppedGear()

        # Detect gear type by scanning per-type templates against the popup
        for kind in GEAR_TYPES:
            tpl = f"hunt/gear_kind_{kind}"
            try:
                m = self.matcher.find(tpl, screenshot=screen)
            except FileNotFoundError:
                continue  # template not captured yet
            if m is not None:
                gear.gear_type = kind
                break

        # OCR substats from the configured region
        if reader.available:
            x_f, y_f, w_f, h_f = SUBSTAT_REGION_NORM
            h, w = screen.shape[:2]
            x, y = int(x_f * w), int(y_f * h)
            rw, rh = int(w_f * w), int(h_f * h)
            crop = screen[y:y + rh, x:x + rw]
            gear.raw_ocr = reader.read(crop)
            gear.substats = reader.parse_substats(gear.raw_ocr)

        log.info("Drop parsed: type=%s subs=%s", gear.gear_type, gear.substats)
        return gear
