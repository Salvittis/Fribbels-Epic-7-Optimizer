"""Item scoring against a meta build.

The score is a heuristic that captures three things:
  1. Set match — does the item's set fit one of the build's priority sets?
  2. Main stat fit — for necklace/ring/boots, is the main stat acceptable?
  3. Substat quality — weighted sum of substats present, scaled by value rolls.

Score range: roughly [-100, +200]. Thresholds for 'junk' and 'good' are set in
the analyzer.
"""
from __future__ import annotations

from dataclasses import dataclass

from .fribbels_io import FIXED_MAIN_BY_GEAR, Item
from .meta import MetaBuild

# Per-substat ceiling roll (15+ gear, single roll, max). These are the values
# above which a substat is 'great'. Used to scale the substat contribution.
# Source: E7 game knowledge (15+15 max single rolls).
ROLL_CEILING = {
    "speed": 8.0,
    "crit_chance": 8.0,
    "crit_damage": 7.0,
    "attack_pct": 9.0,
    "defense_pct": 9.0,
    "health_pct": 9.0,
    "effectiveness": 9.0,
    "effect_resist": 9.0,
    "attack": 45.0,        # flat
    "defense": 30.0,       # flat
    "health": 175.0,       # flat
}

# How much a perfect priority-1 substat contributes.
SUBSTAT_TOP_WEIGHT = 30.0
# Decay factor down the priority list (priority i has weight TOP * decay^i).
SUBSTAT_DECAY = 0.65

SET_TOP_BONUS = 50.0
SET_TOP_DECAY = 0.6      # 2nd priority set = 30, 3rd = 18, etc

MAIN_FIT_BONUS = 40.0
MAIN_MISS_PENALTY = -50.0

# Bonus / malus for rank — we generally only care about Epic+
RANK_BONUS = {"Epic": 15, "Heroic": 5, "Rare": -10, "Good": -25, "Normal": -40}


@dataclass
class ItemScore:
    item: Item
    build: MetaBuild
    total: float
    set_component: float
    main_component: float
    substat_component: float
    rank_component: float
    notes: list[str]


class GearScorer:
    """Stateless scorer. One instance can score many (item, build) pairs."""

    def score(self, item: Item, build: MetaBuild) -> ItemScore:
        notes: list[str] = []

        # --- Set fit
        set_score = 0.0
        if build.sets_priority:
            try:
                idx = build.sets_priority.index(item.set)
                set_score = SET_TOP_BONUS * (SET_TOP_DECAY ** idx)
                notes.append(f"set_match({item.set} @ #{idx + 1})")
            except ValueError:
                set_score = 0.0  # not in priority list; not punished, just no bonus
                notes.append(f"set_off({item.set})")
        else:
            notes.append("set_no_pref")

        # --- Main stat fit (only meaningful for N/R/B)
        main_score = 0.0
        if item.gear in ("necklace", "ring", "boots"):
            acceptable = build.acceptable_main(item.gear)
            if not acceptable:
                main_score = 0.0
                notes.append(f"main_no_pref({item.main_stat})")
            elif item.main_stat in acceptable:
                # Earlier in list = stronger preference
                idx = acceptable.index(item.main_stat)
                main_score = MAIN_FIT_BONUS * (1.0 if idx == 0 else 0.7)
                notes.append(f"main_fit({item.main_stat} @ #{idx + 1})")
            else:
                main_score = MAIN_MISS_PENALTY if build.main_stat_strict else MAIN_MISS_PENALTY * 0.5
                notes.append(f"main_miss({item.main_stat} not in {acceptable})")
        else:
            # Weapon/Helmet/Armor: main is fixed by position, neutral score
            expected = FIXED_MAIN_BY_GEAR.get(item.gear)
            if expected and item.main_stat != expected:
                # Weird item — shouldn't happen, but flag it
                notes.append(f"unexpected_main({item.main_stat} on {item.gear})")

        # --- Substat quality
        sub_score = 0.0
        if build.substats_priority:
            for i, key in enumerate(build.substats_priority):
                weight = SUBSTAT_TOP_WEIGHT * (SUBSTAT_DECAY ** i)
                value = item.substat_value(key)
                if value <= 0:
                    continue
                ceiling = ROLL_CEILING.get(key, 1.0)
                # Cap roll quality at 1.5x (multi-roll into same line)
                quality = min(value / ceiling, 1.5)
                contribution = weight * quality
                sub_score += contribution
        # Bonus for having Speed at all (universally valuable)
        if item.has_substat("speed") and "speed" not in build.substats_priority[:3]:
            sub_score += 5.0
            notes.append("speed_bonus_offrole")

        # --- Rank
        rank_score = RANK_BONUS.get(item.rank, 0)

        # --- Enhance maturity factor — punish low-enhance items lightly so we
        #     don't junk a +0 epic with great potential. Apply only to rank score.
        if item.enhance < 9 and item.rank in ("Epic", "Heroic"):
            rank_score *= 0.3   # don't punish promising +0 gear

        total = set_score + main_score + sub_score + rank_score
        return ItemScore(
            item=item,
            build=build,
            total=total,
            set_component=set_score,
            main_component=main_score,
            substat_component=sub_score,
            rank_component=rank_score,
            notes=notes,
        )
