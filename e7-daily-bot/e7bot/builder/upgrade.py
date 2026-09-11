"""Upgrade recommender — what to enhance/farm to close the build gap.

For each slot that's not 'ready', identify the cheapest path to upgrade:
  1. **Enhance an existing item** — same set, low enhance, good substats.
  2. **Promote an item** — Heroic could become Epic-tier with reforge (+90→Epic).
  3. **Farm gap** — no candidates exist; suggest where to farm (set drop sources).

Also rank every gear position by 'how much improvement is possible' so the
user can spend resources wisely.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from .fribbels_io import FribbelsSave, Item
from .meta import MetaBuild
from .readiness import HeroReadiness, ReadinessChecker, SlotPick
from .scorer import GearScorer, ItemScore

log = logging.getLogger(__name__)


# Where each set primarily drops. Used for "farm here" hints.
SET_FARM_SOURCES = {
    "SpeedSet":         "Wyvern Hunt 11+ / Spirit Altar",
    "HitSet":           "Wyvern Hunt 11+ / Banshee Hunt 11+",
    "RageSet":          "Banshee Hunt 11+",
    "DestructionSet":   "Wyvern Hunt 11+ / Abyss",
    "CounterSet":       "Banshee Hunt 11+",
    "LifestealSet":     "Wyvern Hunt 11+",
    "ResistSet":        "Banshee Hunt 11+",
    "ImmunitySet":      "Banshee Hunt 11+",
    "ProtectionSet":    "Golem Hunt 11+",
    "InjurySet":        "Golem Hunt 11+",
    "AttackSet":        "Banshee Hunt / events",
    "HealthSet":        "Golem Hunt / events",
    "DefenseSet":       "Golem Hunt / events",
    "CriticalSet":      "Wyvern Hunt / events",
    "EffectivenessSet": "Banshee Hunt / events",
    "RevengeSet":       "Wyvern Hunt 11+",
    "PursuitSet":       "Wyvern Hunt 11+",
    "PenetrationSet":   "Banshee Hunt 11+",
    "TorrentSet":       "Hunt drops (hunt 13)",
    "RevenantSet":      "Hunt drops (hunt 13)",
    "RiposteSet":       "Banshee Hunt 13",
    "ReversalSet":      "Wyvern Hunt 13",
    "WarfareSet":       "Wyvern Hunt 13 / events",
    "ReverseSet":       "Wyvern Hunt 13",
}


@dataclass
class UpgradeAction:
    kind: str               # 'enhance' | 'promote' | 'farm'
    gear: str
    description: str
    estimated_score_gain: float = 0.0
    item: Optional[Item] = None


@dataclass
class HeroUpgradePlan:
    hero_name: str
    current_readiness: HeroReadiness
    actions: list[UpgradeAction] = field(default_factory=list)


class UpgradeRecommender:
    """Per-hero, propose the cheapest improvement path."""

    def __init__(self, save: FribbelsSave, scorer: Optional[GearScorer] = None) -> None:
        self.save = save
        self.scorer = scorer or GearScorer()
        self.checker = ReadinessChecker(save=save, scorer=self.scorer)

    def plan(
        self,
        meta: MetaBuild,
        readiness: Optional[HeroReadiness] = None,
        builds=None,
    ) -> HeroUpgradePlan:
        rd = readiness or self.checker.check(meta, builds=builds)
        actions: list[UpgradeAction] = []

        for gear, pick in rd.slots.items():
            if pick.ready:
                continue
            actions.extend(self._actions_for_slot(meta, pick))

        # Sort by estimated gain descending (biggest impact first)
        actions.sort(key=lambda a: a.estimated_score_gain, reverse=True)
        return HeroUpgradePlan(hero_name=meta.name, current_readiness=rd, actions=actions)

    # -------------------------------------------------------------- internal

    def _actions_for_slot(
        self,
        meta: MetaBuild,
        pick: SlotPick,
    ) -> list[UpgradeAction]:
        out: list[UpgradeAction] = []
        gear = pick.gear

        # Action 1: enhance candidates of the right set, if any are <+15
        if pick.set_required:
            same_set = [
                it for it in self.save.items_by_gear(gear)
                if it.set == pick.set_required and it.enhance < 15
            ]
        else:
            # No set constraint: look at all items in slot under +15
            same_set = [it for it in self.save.items_by_gear(gear) if it.enhance < 15]

        # Score each as if it were +15 (rough projection)
        candidates_scored: list[tuple[Item, float, float]] = []
        for it in same_set:
            current = self.scorer.score(it, meta).total
            projected = self._project_max_enhance_score(it, meta)
            gain = projected - current
            if gain > 5:   # ignore trivial gains
                candidates_scored.append((it, current, projected))

        # Top 3 enhance picks
        candidates_scored.sort(key=lambda x: x[2] - x[1], reverse=True)
        for it, current, projected in candidates_scored[:3]:
            out.append(UpgradeAction(
                kind="enhance",
                gear=gear,
                description=(
                    f"Enhance {it.set} {gear} +{it.enhance} -> +15 "
                    f"(score {current:.0f} -> ~{projected:.0f}, gain {projected - current:+.0f})"
                ),
                estimated_score_gain=projected - current,
                item=it,
            ))

        # Action 2: if no good candidates, suggest farming
        if not candidates_scored:
            farm = SET_FARM_SOURCES.get(pick.set_required or "", "Wyvern/Banshee/Golem Hunt 13")
            out.append(UpgradeAction(
                kind="farm",
                gear=gear,
                description=(
                    f"Farm {gear} of {pick.set_required or 'any priority set'} "
                    f"at {farm}. Currently no upgrade-able item in inventory."
                ),
                estimated_score_gain=0.0,
                item=None,
            ))

        return out

    def _project_max_enhance_score(self, item: Item, meta: MetaBuild) -> float:
        """Optimistic projection: simulate the item at +15.

        Heuristic: assume each existing substat gains roughly one more roll
        worth of value when going from +<n> to +15. This is a back-of-envelope
        estimate; real values depend on which substats roll.
        """
        # Count how many enhances are remaining; each gives a substat roll
        remaining = max(0, 15 - item.enhance)
        # Count the substats that the build cares about. If the item has 4
        # substats and 3 are useful, ~75% of remaining rolls land on useful.
        useful_keys = set(meta.substats_priority[:5])
        useful_present = [s for s in item.substats if s.stat in useful_keys]

        # Build a fake item with bumped substat values
        bumped = Item(
            id=item.id, gear=item.gear, rank=item.rank, set=item.set,
            enhance=15, level=85, main_stat=item.main_stat, main_value=item.main_value,
            substats=list(item.substats), locked=item.locked,
            equipped_to_id=item.equipped_to_id, raw=item.raw,
        )
        # Bump useful substats proportional to expected rolls landing
        expected_useful_rolls = 0
        if useful_present:
            expected_useful_rolls = remaining * (len(useful_present) / max(1, len(item.substats)))
        from .scorer import ROLL_CEILING
        if expected_useful_rolls > 0 and useful_present:
            per_roll = expected_useful_rolls / len(useful_present)
            new_subs = []
            for s in bumped.substats:
                if s.stat in useful_keys:
                    ceil = ROLL_CEILING.get(s.stat, 1.0)
                    new_subs.append(type(s)(stat=s.stat, value=s.value + per_roll * ceil * 0.7))
                else:
                    new_subs.append(s)
            bumped.substats = new_subs

        return self.scorer.score(bumped, meta).total
