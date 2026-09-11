"""Meta build library — curated 'what does each hero want' definitions.

A `MetaBuild` is a recipe for a hero: priority sets, acceptable main stats per
gear position, and substat priorities. Items get scored against the recipe.

Defaults ship in `data/meta_builds.yaml`. Users can override per-hero in their
own yaml without touching the package.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import yaml


# Canonical substat keys (mirrors fribbels_io.STAT_FRIBBELS_TO_CANONICAL values).
ALL_SUBSTATS = (
    "attack", "attack_pct", "defense", "defense_pct",
    "health", "health_pct", "speed",
    "crit_chance", "crit_damage",
    "effectiveness", "effect_resist",
)


@dataclass
class MetaBuild:
    """Build target for one hero (or one role variant)."""
    name: str                                   # canonical hero name (matches Fribbels)
    role_label: str = ""                        # human-readable role/comment
    sets_priority: list[str] = field(default_factory=list)   # e.g. ['SpeedSet', 'ImmunitySet']
    main_necklace: list[str] = field(default_factory=list)   # acceptable mains
    main_ring: list[str] = field(default_factory=list)
    main_boots: list[str] = field(default_factory=list)
    substats_priority: list[str] = field(default_factory=list)  # ordered priority

    # How important is the main stat constraint? Common attackers want CDmg
    # necklaces; if main is wrong, the gear is mostly useless. Heavily punish.
    main_stat_strict: bool = True

    # Tier hint for build priority sorting (1 = top tier, 5 = niche).
    tier: int = 3

    def acceptable_main(self, gear: str) -> list[str]:
        return {
            "necklace": self.main_necklace,
            "ring": self.main_ring,
            "boots": self.main_boots,
        }.get(gear, [])


@dataclass
class MetaLibrary:
    builds: dict[str, MetaBuild] = field(default_factory=dict)

    def get(self, name: str) -> Optional[MetaBuild]:
        target = name.strip().lower()
        return next(
            (b for k, b in self.builds.items() if k.lower() == target
             or b.name.strip().lower() == target),
            None,
        )

    def names(self) -> list[str]:
        return sorted(b.name for b in self.builds.values())


def default_meta_path() -> Path:
    """Bundled meta yaml path."""
    return Path(__file__).resolve().parents[2] / "data" / "meta_builds.yaml"


def load_meta(path: str | Path | None = None) -> MetaLibrary:
    p = Path(path) if path else default_meta_path()
    if not p.exists():
        raise FileNotFoundError(f"Meta builds file not found: {p}")
    with p.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    builds: dict[str, MetaBuild] = {}
    for key, raw in (data.get("builds", {}) or {}).items():
        raw = raw or {}
        builds[key] = MetaBuild(
            name=raw.get("name", key),
            role_label=raw.get("role_label", ""),
            sets_priority=list(raw.get("sets_priority", [])),
            main_necklace=list(raw.get("main_necklace", [])),
            main_ring=list(raw.get("main_ring", [])),
            main_boots=list(raw.get("main_boots", [])),
            substats_priority=list(raw.get("substats_priority", [])),
            main_stat_strict=bool(raw.get("main_stat_strict", True)),
            tier=int(raw.get("tier", 3)),
        )
    return MetaLibrary(builds=builds)
