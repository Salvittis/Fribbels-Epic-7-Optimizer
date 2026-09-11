"""Load gear + hero data from a Fribbels Optimizer save file.

Fribbels stores its full state at ~/Documents/FribbelsOptimizerSaves/ as JSON.
The format observed in `testgear.json` is::

    {
      "items":   [ {gear, rank, set, enhance, level, main, substats, ...}, ... ],
      "heroes":  [ {name, rarity, attribute, role, atk, hp, ..., equipment}, ... ]
    }

We expose typed wrappers and convenience accessors. We don't mutate the source.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Optional


# -- Stat key normalization ----------------------------------------------------
# Fribbels uses CamelCase keys. We use snake_case canonical keys throughout the
# builder so meta yaml stays readable.
STAT_FRIBBELS_TO_CANONICAL = {
    "Attack": "attack",
    "AttackPercent": "attack_pct",
    "Defense": "defense",
    "DefensePercent": "defense_pct",
    "Health": "health",
    "HealthPercent": "health_pct",
    "Speed": "speed",
    "CriticalHitChancePercent": "crit_chance",
    "CriticalHitDamagePercent": "crit_damage",
    "EffectivenessPercent": "effectiveness",
    "EffectResistancePercent": "effect_resist",
}
STAT_CANONICAL_TO_FRIBBELS = {v: k for k, v in STAT_FRIBBELS_TO_CANONICAL.items()}

GEAR_TYPES = ("Weapon", "Helmet", "Armor", "Necklace", "Ring", "Boots")
GEAR_TYPE_CANONICAL = {g: g.lower() for g in GEAR_TYPES}

# Mains that are FIXED by gear position (so they don't enter scoring as
# differentiators). Keeps weapon/helmet/armor scoring focused on substats+set.
FIXED_MAIN_BY_GEAR = {
    "weapon": "attack",
    "helmet": "health",
    "armor": "defense",
}


def to_canonical_stat(fribbels_key: str) -> str:
    return STAT_FRIBBELS_TO_CANONICAL.get(fribbels_key, fribbels_key.lower())


# -- Data classes --------------------------------------------------------------

@dataclass(frozen=True)
class Substat:
    stat: str       # canonical key
    value: float


@dataclass
class Item:
    id: str
    gear: str       # canonical: weapon/helmet/armor/necklace/ring/boots
    rank: str       # Epic/Heroic/Rare/Good/Normal
    set: str        # e.g. SpeedSet, ImmunitySet, ...
    enhance: int    # 0-15
    level: int
    main_stat: str        # canonical
    main_value: float
    substats: list[Substat] = field(default_factory=list)
    locked: bool = False
    equipped_to_id: Optional[str] = None
    raw: dict = field(default_factory=dict)  # full original dict, in case

    @property
    def is_high_quality(self) -> bool:
        return self.rank in ("Epic", "Heroic")

    def has_substat(self, key: str) -> bool:
        return any(s.stat == key for s in self.substats)

    def substat_value(self, key: str) -> float:
        return next((s.value for s in self.substats if s.stat == key), 0.0)


@dataclass
class Hero:
    id: str
    name: str
    rarity: int
    attribute: str  # fire/ice/earth/light/dark
    role: str       # warrior/manauser/etc (Fribbels' role taxonomy)
    equipment: dict[str, str] = field(default_factory=dict)  # gear -> item_id
    raw: dict = field(default_factory=dict)


@dataclass
class FribbelsSave:
    items: list[Item]
    heroes: list[Hero]
    source_path: Optional[Path] = None

    def hero_by_name(self, name: str) -> Optional[Hero]:
        target = name.strip().lower()
        return next((h for h in self.heroes if h.name.strip().lower() == target), None)

    def items_by_gear(self, gear: str) -> list[Item]:
        gear = gear.lower()
        return [i for i in self.items if i.gear == gear]

    def unlocked_items(self) -> list[Item]:
        return [i for i in self.items if not i.locked]


# -- IO ------------------------------------------------------------------------

def default_save_path() -> Path:
    """Default location of Fribbels saves on Windows.

    Fribbels writes to %USERPROFILE%/Documents/FribbelsOptimizerSaves/.
    We pick the most recently modified .txt or .json in there.
    """
    docs = Path(os.path.expanduser("~/Documents/FribbelsOptimizerSaves"))
    if not docs.exists():
        return docs  # caller will see FileNotFoundError later
    candidates = sorted(
        list(docs.glob("*.txt")) + list(docs.glob("*.json")),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    return candidates[0] if candidates else docs


def load_save(path: str | Path) -> FribbelsSave:
    p = Path(path)
    if p.is_dir():
        # Auto-pick most recent file in the directory
        candidates = sorted(
            list(p.glob("*.txt")) + list(p.glob("*.json")),
            key=lambda x: x.stat().st_mtime, reverse=True,
        )
        if not candidates:
            raise FileNotFoundError(f"No save files in {p}")
        p = candidates[0]
    with p.open("r", encoding="utf-8") as f:
        data = json.load(f)
    return FribbelsSave(
        items=[_parse_item(d) for d in data.get("items", [])],
        heroes=[_parse_hero(d) for d in data.get("heroes", [])],
        source_path=p,
    )


def _parse_item(d: dict) -> Item:
    main = d.get("main", {}) or {}
    substats_raw = d.get("substats", []) or []
    return Item(
        id=str(d.get("id", "")),
        gear=GEAR_TYPE_CANONICAL.get(d.get("gear", ""), d.get("gear", "").lower()),
        rank=d.get("rank", ""),
        set=d.get("set", ""),
        enhance=int(d.get("enhance", 0) or 0),
        level=int(d.get("level", 0) or 0),
        main_stat=to_canonical_stat(main.get("type", "")),
        main_value=float(main.get("value", 0) or 0),
        substats=[
            Substat(stat=to_canonical_stat(s.get("type", "")),
                    value=float(s.get("value", 0) or 0))
            for s in substats_raw
        ],
        locked=bool(d.get("locked", False)),
        equipped_to_id=d.get("equippedToId") or d.get("equippedById"),
        raw=d,
    )


def _parse_hero(d: dict) -> Hero:
    eq_in = d.get("equipment", {}) or {}
    eq_out: dict[str, str] = {}
    for k, v in eq_in.items():
        if isinstance(v, dict):
            eq_out[k.lower()] = str(v.get("id", ""))
        elif isinstance(v, str):
            eq_out[k.lower()] = v
    return Hero(
        id=str(d.get("id", "")),
        name=d.get("name", ""),
        rarity=int(d.get("rarity", 0) or 0),
        attribute=d.get("attribute", "") or "",
        role=d.get("role", "") or "",
        equipment=eq_out,
        raw=d,
    )
