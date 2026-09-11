"""OCR for reading dropped gear's substats from the post-battle popup.

After a hunt the game shows a "Loot" or "Equipamento adquirido" popup with the
new gear and its 4 substats (3 if the gear is white/blue/etc — purple+ have 4
guaranteed sub roll positions but can be empty until enhanced).

We tesseract two regions: substat names (left column) and substat numbers
(right column). Then we normalize the text and produce a structured
`DroppedGear`.

This module gracefully degrades: if pytesseract is not installed or the OCR
returns nothing, the hunt routine treats the drop as "unknown" and keeps farming.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

log = logging.getLogger(__name__)

# Map of normalized PT-BR labels -> canonical stat keys used in filters.
# Adjust these as you see what Tesseract actually outputs from your client.
STAT_ALIASES = {
    # PT-BR
    "atk": "attack",
    "ataque": "attack",
    "atq": "attack",
    "atq%": "attack_pct",
    "ataque%": "attack_pct",
    "def": "defense",
    "defesa": "defense",
    "def%": "defense_pct",
    "hp": "health",
    "vida": "health",
    "hp%": "health_pct",
    "vida%": "health_pct",
    "vel": "speed",
    "velocidade": "speed",
    "speed": "speed",
    "crit": "crit_chance",
    "chance crítica": "crit_chance",
    "chance critica": "crit_chance",
    "crit%": "crit_chance",
    "dano crítico": "crit_damage",
    "dano critico": "crit_damage",
    "dano crit": "crit_damage",
    "crit dmg": "crit_damage",
    "ef": "effectiveness",
    "efetividade": "effectiveness",
    "res": "resistance",
    "resistência": "resistance",
    "resistencia": "resistance",
}


@dataclass(frozen=True)
class Substat:
    stat: str   # canonical key, e.g. 'speed'
    value: float


@dataclass
class DroppedGear:
    main_stat: Optional[str] = None
    main_value: Optional[float] = None
    gear_type: Optional[str] = None  # boots, weapon, ring, ...
    substats: list[Substat] = field(default_factory=list)
    raw_ocr: str = ""

    def has_substat(self, key: str) -> bool:
        return any(s.stat == key for s in self.substats)

    def matches_filter(self, f: dict) -> bool:
        """Check if this gear matches a single filter dict from config.yaml."""
        if (g := f.get("gear")) and self.gear_type and g != self.gear_type:
            return False
        if (m := f.get("main_stat")) and self.main_stat and m != self.main_stat:
            return False
        any_keys = f.get("substats_any") or []
        if any_keys and not any(self.has_substat(k) for k in any_keys):
            return False
        all_keys = f.get("substats_all") or []
        if all_keys and not all(self.has_substat(k) for k in all_keys):
            return False
        return True


class StatReader:
    """Wraps Tesseract calls. Returns a partial DroppedGear best-effort."""

    def __init__(self, lang: str = "por") -> None:
        self.lang = lang
        try:
            import pytesseract  # noqa: F401
            self._available = True
        except ImportError:
            self._available = False
            log.warning("pytesseract not installed — gear OCR disabled")

    @property
    def available(self) -> bool:
        return self._available

    def read(self, region_image: np.ndarray) -> str:
        """Run Tesseract on a numpy image (BGR or grayscale)."""
        if not self._available:
            return ""
        import pytesseract
        try:
            return pytesseract.image_to_string(region_image, lang=self.lang)
        except Exception as e:
            log.warning("Tesseract failed: %s", e)
            return ""

    def parse_substats(self, text: str) -> list[Substat]:
        """Best-effort substat parser.

        Expected lines look like:
          'Velocidade  +12'
          'Chance Crítica  +5%'
          'Ataque  +35'
        """
        out: list[Substat] = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            # Split on the first digit/+/- to separate label from value
            m = re.search(r"([+\-]?\d+\.?\d*)", line)
            if not m:
                continue
            value = float(m.group(1).lstrip("+"))
            label = line[:m.start()].strip().lower()
            label = re.sub(r"\s+", " ", label)
            # If the value had a percent sign, prefer the *_pct alias
            has_pct = "%" in line
            canonical = self._canonicalize(label, has_pct=has_pct)
            if canonical:
                out.append(Substat(canonical, value))
        return out

    @staticmethod
    def _canonicalize(label: str, has_pct: bool) -> Optional[str]:
        # Try exact match first, then with % suffix for percent variants
        key = label.replace("+", "").strip()
        if has_pct:
            pct_key = key + "%"
            if pct_key in STAT_ALIASES:
                return STAT_ALIASES[pct_key]
        if key in STAT_ALIASES:
            return STAT_ALIASES[key]
        # Fuzzy: try with diacritic-stripped lookup
        for alias, canon in STAT_ALIASES.items():
            if alias in key or key in alias:
                return canon
        return None
